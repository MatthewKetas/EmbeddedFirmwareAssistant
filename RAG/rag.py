import hashlib
import importlib.util
import os
import shlex
import signal
import sys
import time
import uuid
from functools import cache
from itertools import chain, islice
from pathlib import Path

import httpx
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchAny, MatchValue, PointStruct, VectorParams,
)

# Library, cache and history live next to this script, wherever you launch it from.
SCRIPT_DIR = Path(__file__).resolve().parent
_board_map_spec = importlib.util.spec_from_file_location(
    "board_map", SCRIPT_DIR.parent / "knowledge-map" / "board_map.py",
)
board_map = importlib.util.module_from_spec(_board_map_spec)
_board_map_spec.loader.exec_module(board_map)

# Folder that /add and /file look in for bare names like "ESP32.pdf".
# Uses a "datasheets" folder next to this script if there is one, otherwise the one beside
# the script's folder (e.g. script in RAG\old_test -> RAG\datasheets). Full paths still work.
DOCS_DIR = next(
    (d for d in (SCRIPT_DIR / "datasheets", SCRIPT_DIR.parent / "datasheets") if d.is_dir()),
    SCRIPT_DIR / "datasheets",
)

# --- Configuration -----------------------------------------------------
BASE_URL = "http://localhost:13305/api/v1"
API_KEY = "lemonade"                        # ignored by Lemonade
CHAT_MODEL = "Qwen3.6-35B-A3B-GGUF"
CHAT_CONTEXT_TOKENS = 16_384                # room for retrieved passages, history and the reply
CHAT_TOKENIZER = "Qwen/Qwen3.6-35B-A3B"
RAG_CONTEXT_TOKENS = 4_000                  # retrieved context on turns with code
RAG_REPLY_TOKENS = 2_048                    # space reserved for generation
# Must match the name Lemonade lists for your embedding model (check /api/v1/models)
EMBED_MODEL = "Qwen3-Embedding-8B-GGUF"
EMBED_DIM = 4096                            # Qwen3-Embedding-8B output size

TEMPERATURE = 1.0
TOP_P = 0.9
TOP_K = 40

QDRANT_PATH = str(SCRIPT_DIR / "qdrant_data")   # on-disk vector library, no server needed
COLLECTION = "docs"
TOP_N_CHUNKS = 10                                # chunks sent to the chat model per question
EMBED_BATCH = 16
MAX_CHARS = 100_000                         # only used by /file (whole-document paste)

# Chunking: measure chunk size with the SAME tokenizer as the embedding model.
CHUNK_TOKENIZER = "Qwen/Qwen3-Embedding-8B"  # only the small tokenizer files download, not the model
CHUNK_TOKENS = 768                          # 512-1024 works well; bigger = more context per hit

# Free the embedding model's memory once it has produced its vectors.
UNLOAD_AFTER_INGEST = True    # after /add finishes embedding a file (recommended)
UNLOAD_AFTER_QUERY = False    # after embedding each question (saves VRAM but reloads the 8B every turn)

# Docling speed settings
DO_OCR = False                           # set False to skip OCR entirely (see compare_ocr.py to test)
DOCLING_THREADS = os.cpu_count() or 8   # default is only 4; use all cores
OCR_BACKEND = "onnxruntime"             # usually much faster on CPU than "torch" (pip install onnxruntime)
OCR_MIN_IMAGE_AREA = 0.10               # only OCR images covering >=10% of the page (default 0.05); skips logos/icons
CACHE_DIR = SCRIPT_DIR / ".docling_cache"       # converted documents cached here

# Qwen3-Embedding wants an instruction on the QUERY side only (not on documents).
QUERY_TASK = "Given a question, retrieve passages from documents that answer it"

# Prompt: Tab completion + up-arrow history (needs: pip install prompt_toolkit)
HISTORY_FILE = SCRIPT_DIR / ".chat_history"
# -----------------------------------------------------------------------

client = None
qdrant = None

_converter = None
_chunker = None


def unload_model(model: str) -> None:
    """Ask Lemonade to unload one model. Failure is non-fatal."""
    try:
        r = httpx.post(f"{BASE_URL}/unload", json={"model_name": model}, timeout=10)
        if r.status_code == 200:
            print(f"[unloaded {model}]")
        else:
            print(f"[unload returned {r.status_code}: {r.text[:200]}]")
    except Exception as e:
        print(f"[could not unload {model}: {e}]")


def teardown() -> None:
    """Attempt every cleanup step without hiding the original error."""
    for resource in (client, qdrant):
        if resource is not None:
            try:
                resource.close()
            except Exception as e:
                print(f"[could not close {type(resource).__name__}: {e}]")
    for model in (EMBED_MODEL, CHAT_MODEL):
        unload_model(model)


def ensure_collection() -> None:
    if not qdrant.collection_exists(COLLECTION):
        qdrant.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )


def resolve_path(path: str) -> Path:
    """Relative paths (bare names or subfolders like esp/x.pdf) resolve against DOCS_DIR; full paths also work."""
    p = Path(path.strip('"\'')).expanduser()
    if not p.is_absolute():
        p = DOCS_DIR / p
    if not p.exists():
        raise FileNotFoundError(f"Not found: {p}")
    return p


def _build_converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    try:
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    except ImportError:  # older Docling versions
        from docling.datamodel.pipeline_options import AcceleratorDevice, AcceleratorOptions

    backend = OCR_BACKEND
    if backend == "onnxruntime" and importlib.util.find_spec("onnxruntime") is None:
        print("[onnxruntime not installed, falling back to the slower torch OCR backend. "
              "Run: pip install onnxruntime]")
        backend = "torch"

    opts = PdfPipelineOptions()
    opts.do_ocr = DO_OCR
    opts.do_table_structure = True
    ocr_kwargs = {"backend": backend}
    if "bitmap_area_threshold" in RapidOcrOptions.model_fields:
        ocr_kwargs["bitmap_area_threshold"] = OCR_MIN_IMAGE_AREA
    opts.ocr_options = RapidOcrOptions(**ocr_kwargs)
    opts.accelerator_options = AcceleratorOptions(
        num_threads=DOCLING_THREADS,
        device=AcceleratorDevice.AUTO,   # uses a CUDA GPU if PyTorch can see one, else CPU
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


def convert(path: Path):
    """Run Docling once per file version; returns the DoclingDocument (cached on disk)."""
    global _converter
    from docling_core.types.doc import DoclingDocument

    st = path.stat()
    key = hashlib.sha1(f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}|ocr={DO_OCR}".encode()).hexdigest()[:16]
    cache_file = CACHE_DIR / f"{path.stem}.{key}.json"
    if cache_file.exists():
        print(f"[using cached conversion for {path.name}]")
        return DoclingDocument.load_from_json(cache_file)

    if _converter is None:
        print("Loading Docling (first run downloads models, can take a while)...")
        _converter = _build_converter()

    t = time.time()
    doc = _converter.convert(str(path)).document
    print(f"[docling conversion took {time.time() - t:.1f}s]")

    CACHE_DIR.mkdir(exist_ok=True)
    doc.save_as_json(cache_file)
    return doc


@cache
def get_tokenizer(name: str):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(name)


def get_chunker():
    global _chunker
    if _chunker is None:
        from docling.chunking import HybridChunker
        try:
            from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
            tok = HuggingFaceTokenizer(
                tokenizer=get_tokenizer(CHUNK_TOKENIZER),
                max_tokens=CHUNK_TOKENS,
            )
            _chunker = HybridChunker(tokenizer=tok, merge_peers=True)
        except ImportError:  # older docling-core versions
            _chunker = HybridChunker(tokenizer=CHUNK_TOKENIZER, max_tokens=CHUNK_TOKENS, merge_peers=True)
    return _chunker


def embed(texts: list[str]) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        out.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))
    return out


def embed_query(question: str) -> list[float]:
    return embed([f"Instruct: {QUERY_TASK}\nQuery: {question}"])[0]


def chunk_page(chunk):
    try:
        return chunk.meta.doc_items[0].prov[0].page_no
    except Exception:
        return None


def ingest(path_str: str) -> None:
    path = resolve_path(path_str)
    doc = convert(path)

    chunker = get_chunker()
    chunks = list(chunker.chunk(dl_doc=doc))
    texts = [chunker.contextualize(chunk=c) for c in chunks]  # includes heading path
    if not texts:
        print("No text extracted.")
        return
    print(f"Embedding {len(texts)} chunks with {EMBED_MODEL}...")
    vectors = embed(texts)
    if UNLOAD_AFTER_INGEST:
        unload_model(EMBED_MODEL)

    ensure_collection()
    # Re-adding the same file replaces its old chunks
    qdrant.delete(
        COLLECTION,
        points_selector=Filter(must=[FieldCondition(key="source", match=MatchValue(value=path.name))]),
    )
    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{path.name}:{i}")),
            vector=vec,
            payload={"source": path.name, "chunk": i, "page": chunk_page(c), "text": text},
        )
        for i, (c, text, vec) in enumerate(zip(chunks, texts, vectors))
    ]
    qdrant.upsert(COLLECTION, points=points)
    print(f"Indexed {len(points)} chunks from {path.name}\n")


def code_chunks(repo: Path):
    try:
        import tree_sitter_c
        from tree_sitter import Language, Parser
    except ImportError as e:
        raise RuntimeError("Install C parsing with: pip install tree-sitter tree-sitter-c") from e

    parser = Parser(Language(tree_sitter_c.language()))
    tokenizer = get_tokenizer(CHUNK_TOKENIZER)

    def raise_walk_error(error):
        raise error

    for directory, dirs, files in os.walk(repo, onerror=raise_walk_error):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "build")
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix.lower() not in {".c", ".h"} or path.is_symlink() or not path.is_file():
                continue
            source = path.read_bytes()
            boundaries = [0]
            for node in parser.parse(source).root_node.named_children:
                if node.type in {"function_definition", "preproc_if", "preproc_ifdef"}:
                    boundaries.extend((node.start_byte, node.end_byte))
            boundaries.append(len(source))

            line = 1
            for start, end in zip(boundaries, boundaries[1:]):
                text = source[start:end].decode("utf-8", errors="replace")
                if not text.strip():
                    line += text.count("\n")
                    continue
                offsets = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True,
                                    verbose=False)["offset_mapping"]
                start = 0
                for end in chain((a for a, _ in offsets[CHUNK_TOKENS::CHUNK_TOKENS]), (len(text),)):
                    part = text[start:end]
                    snippet = part.strip("\r\n")
                    if snippet.strip():
                        leading = part[:len(part) - len(part.lstrip("\r\n"))].count("\n")
                        yield {
                            "file": path.relative_to(repo).as_posix(),
                            "start_line": line + leading,
                            "end_line": line + leading + snippet.count("\n"),
                            "text": snippet,
                        }
                    line += part.count("\n")
                    start = end


def ingest_code(path_str: str) -> str:
    repo = Path(path_str.strip("\"'")).expanduser().resolve(strict=True)
    if not repo.is_dir():
        raise NotADirectoryError(f"Expected a repository directory: {repo}")
    source = str(repo)
    revision = uuid.uuid4()
    repo_match = FieldCondition(key="source", match=MatchValue(value=source))
    revision_match = FieldCondition(key="revision", match=MatchValue(value=str(revision)))
    chunks = code_chunks(repo)
    count = 0
    ensure_collection()
    try:
        while batch := list(islice(chunks, EMBED_BATCH)):
            vectors = embed([f"{p['file']}\n{p['text']}" for p in batch])
            points = [
                PointStruct(
                    id=str(uuid.uuid5(revision, str(i))),
                    vector=vector,
                    payload={**payload, "source": source, "revision": str(revision)},
                )
                for i, (payload, vector) in enumerate(zip(batch, vectors, strict=True), count)
            ]
            qdrant.upsert(COLLECTION, points=points)
            count += len(points)
    except BaseException:
        # A failed refresh should leave the previous index usable.
        try:
            qdrant.delete(COLLECTION, points_selector=Filter(must=[repo_match, revision_match]))
        except Exception as e:
            print(f"[could not remove partial code index: {e}]")
        raise
    finally:
        if count and UNLOAD_AFTER_INGEST:
            unload_model(EMBED_MODEL)

    qdrant.delete(COLLECTION, points_selector=Filter(must=[repo_match], must_not=[revision_match]))
    print(f"Indexed {count} code chunks from {source}\n")
    return source


def retrieve(question: str, only: list[str] | None = None):
    if not qdrant.collection_exists(COLLECTION) or qdrant.count(COLLECTION).count == 0:
        return []
    flt = None
    if only:
        flt = Filter(must=[FieldCondition(key="source", match=MatchAny(any=only))])
    qvec = embed_query(question)
    if UNLOAD_AFTER_QUERY:
        unload_model(EMBED_MODEL)
    res = qdrant.query_points(
        COLLECTION, query=qvec, limit=TOP_N_CHUNKS, query_filter=flt,
    )
    return res.points


def list_sources() -> list[str]:
    if not qdrant.collection_exists(COLLECTION):
        return []
    pts, _ = qdrant.scroll(COLLECTION, limit=100_000, with_payload=["source"], with_vectors=False)
    return sorted({p.payload["source"] for p in pts})


def source_label(payload) -> str:
    if "file" in payload:
        repo = Path(payload["source"]).name
        return f"{repo}/{payload['file']}:{payload['start_line']}-{payload['end_line']}"
    page = f", p.{payload['page']}" if payload.get("page") else ""
    return f"{payload['source']}{page}"


def build_rag_prompt(question: str, hits, board_context: str = "") -> str:
    parts = [f"[{source_label(h.payload)}]\n{h.payload['text']}" for h in hits]
    if board_context:
        parts.insert(0, board_context)
    context = "\n\n---\n\n".join(parts)
    citation = "[repo/file:start-end] for code or [file, p.N] for documents" if any(
        "file" in h.payload for h in hits
    ) else "[file, p.N]"
    if board_context:
        citation += ", [remember:key] for saved facts, or [file.svd] for device data"
    return (
        f"Answer the question using the context below. Cite sources like {citation}. "
        "If the answer isn't in the context, say so.\n\n"
        f"=== CONTEXT ===\n{context}\n=== END CONTEXT ===\n\n"
        f"Question: {question}"
    )


def fit_code_context(question: str, hits, history: list, board_context: str = ""):
    tokenizer = get_tokenizer(CHAT_TOKENIZER)

    def prompt_tokens(selected):
        messages = history + [{"role": "user", "content": build_rag_prompt(question, selected, board_context)}]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        return len(tokenizer.encode(text, add_special_tokens=False, verbose=False))

    limit = min(prompt_tokens([]) + RAG_CONTEXT_TOKENS, CHAT_CONTEXT_TOKENS - RAG_REPLY_TOKENS)
    selected = []
    for hit in hits:
        if prompt_tokens(selected + [hit]) <= limit:
            selected.append(hit)
    return selected


def print_usage(usage, elapsed: float) -> None:
    if not usage:
        print(f"[usage stats not returned by server | time: {elapsed:.2f}s]")
        return
    tps = usage.completion_tokens / elapsed if elapsed > 0 else 0
    print(
        f"[tokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, "
        f"total={usage.total_tokens} | time: {elapsed:.2f}s | ~{tps:.1f} tok/s]"
    )


def stream_reply(messages: list) -> str:
    start = time.time()
    # Context size is a model-load option, not a chat-completion option.
    response = httpx.post(
        f"{BASE_URL}/load",
        json={"model_name": CHAT_MODEL, "ctx_size": CHAT_CONTEXT_TOKENS},
        timeout=120,
    )
    response.raise_for_status()
    if response.json().get("status") == "error":
        raise RuntimeError(f"Could not load {CHAT_MODEL}: {response.json().get('message')}")
    stream = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=TEMPERATURE,
        top_p=TOP_P,
        extra_body={"top_k": TOP_K},
        stream=True,
        stream_options={"include_usage": True},
    )
    print("Response: ", end="", flush=True)
    reply, usage = "", None
    with stream:
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    print(delta, end="", flush=True)
                    reply += delta
            if chunk.usage:
                usage = chunk.usage
    print()
    print_usage(usage, time.time() - start)
    print()
    return reply


HELP = (
    "Commands:\n"
    "  /add <file>              index a file (from the datasheets folder) into the library\n"
    "  /file <file> [question]  paste a whole document into the chat (no library)\n"
    "  /list                    show indexed files\n"
    "  /only <f1> [f2 ...]|all  restrict retrieval to one or more files (quote names with spaces)\n"
    "  /clear                   reset the chat (library is kept)\n"
    "  /wipe                    delete the indexed documents and code\n"
    "  /code <directory>       index and select a C repository\n"
    "  /board [id|none]         list or select boards, or clear selection\n"
    "  /remember key=value     save or update a fact for the selected board\n"
    "  /quit                    exit\n"
)

COMMANDS = ["/add", "/file", "/list", "/only", "/clear", "/wipe", "/quit", "/code", "/board", "/remember"]


def make_prompt():
    """Use terminal editing when available, with plain input as a fallback."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return input

    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import Completer, Completion, PathCompleter
        from prompt_toolkit.document import Document
        from prompt_toolkit.history import FileHistory
    except ImportError:
        print("[Tab completion off. Enable it with: pip install prompt_toolkit]\n")
        return input

    class RagCompleter(Completer):
        def __init__(self):
            # Relative paths complete against the datasheets folder; absolute paths and ~ also work.
            self.paths = PathCompleter(get_paths=lambda: [str(DOCS_DIR)], expanduser=True)
            self.repos = PathCompleter(only_directories=True, expanduser=True)

        def _complete_path(self, text, event):
            yield from self.paths.get_completions(Document(text, len(text)), event)

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor

            # First word: complete the command name.
            if " " not in text:
                if text.startswith("/"):
                    for c in COMMANDS:
                        if c.startswith(text.lower()):
                            yield Completion(c + " ", start_position=-len(text), display=c)
                return

            cmd, _, rest = text.partition(" ")
            cmd = cmd.lower()

            if cmd == "/add":
                # The whole rest of the line is the path, so names with spaces are fine.
                yield from self._complete_path(rest, complete_event)

            elif cmd == "/code":
                yield from self.repos.get_completions(Document(rest, len(rest)), complete_event)

            elif cmd == "/file":
                # Only the first word is the path; after it comes the question.
                if " " not in rest:
                    yield from self._complete_path(rest, complete_event)

            elif cmd == "/only":
                # Complete the current word from the files already in the library.
                if rest.count('"') % 2 == 1:      # inside an open quote
                    start = rest.rfind('"')
                else:
                    start = rest.rfind(" ") + 1
                word = rest[start:]
                needle = word.lstrip('"').lower()
                for name in ["all"] + list_sources():
                    if name.lower().startswith(needle):
                        insert = f'"{name}"' if " " in name else name
                        yield Completion(insert, start_position=-len(word), display=name)

    session = PromptSession(
        completer=RagCompleter(),
        complete_while_typing=False,   # menu only appears when you press Tab
        history=FileHistory(str(HISTORY_FILE)),
    )
    print("Press Tab to complete commands and file names. Use Up/Down for previous prompts.\n")
    return session.prompt


def interactive_loop():
    print(f"Chat: {CHAT_MODEL} | Embeddings: {EMBED_MODEL} | Qdrant: {QDRANT_PATH}")
    print(f"Script folder: {SCRIPT_DIR}")
    print(f"Datasheets:    {DOCS_DIR}{'' if DOCS_DIR.is_dir() else '  (NOT FOUND)'}")
    print(HELP)

    ask = make_prompt()
    history: list[dict] = []
    only: list[str] | None = None
    board_id = None

    while True:
        try:
            user_input = ask("Prompt: ").strip()
        except KeyboardInterrupt:   # Ctrl+C (including an IDE stop) exits
            break
        except EOFError:            # Ctrl+D / Ctrl+Z exits
            break
        low = user_input.lower()
        if low in ("exit", "quit", "/exit", "/quit"):
            break
        if not user_input:
            continue

        if low in ("/clear", "/new", "/reset"):
            history = []
            print("Chat cleared.\n")
            continue

        command, _, arg = user_input.partition(" ")
        if command.lower() == "/board":
            selected = board_map.select_board(arg.strip().lower(), board_id)
            if selected != board_id:
                history = []
                board_id = selected
            continue
        if command.lower() == "/remember":
            board_map.remember(board_id, arg)
            continue

        if low == "/list":
            srcs = list_sources()
            print("\n".join(f"  {s}" for s in srcs) if srcs else "  (library is empty)")
            print()
            continue

        if low == "/wipe":
            if qdrant.collection_exists(COLLECTION):
                qdrant.delete_collection(COLLECTION)
            print("Library deleted.\n")
            continue

        if low.startswith("/only "):
            names = shlex.split(user_input[6:], posix=False)
            names = [n.strip('"\'') for n in names]
            if not names or (len(names) == 1 and names[0].lower() == "all"):
                only = None
            else:
                only = names
                known = set(list_sources())
                missing = [n for n in only if n not in known]
                if missing:
                    print(f"Warning: not in library: {', '.join(missing)} (use /list to see indexed files)")
            print(f"Retrieval scope: {', '.join(only) if only else 'all files'}\n")
            continue

        if low.startswith("/add "):
            ingest(user_input[5:])
            continue

        if low == "/code":
            print("Usage: /code <directory>\n")
            continue

        if low.startswith("/code "):
            only = [ingest_code(user_input[6:])]
            print(f"Retrieval scope: {only[0]}\n")
            continue

        if low.startswith("/file "):
            parts = user_input[6:].split(maxsplit=1)
            question = parts[1] if len(parts) > 1 else "Summarize this document."
            md = convert(resolve_path(parts[0])).export_to_markdown()
            if len(md) > MAX_CHARS:
                print(f"Warning: {len(md):,} chars, truncating to {MAX_CHARS:,}.")
                md = md[:MAX_CHARS]
            content = f"{question}\n\n--- BEGIN DOCUMENT ---\n{md}\n--- END DOCUMENT ---"
            history.append({"role": "user", "content": content})
            history.append({"role": "assistant", "content": stream_reply(history)})
            continue

        # Normal question: retrieve from the library if there is one.
        board_context = board_map.context(board_id, user_input) if board_id else ""
        hits = retrieve(user_input, only)
        if any("file" in h.payload for h in hits):
            hits = fit_code_context(user_input, hits, history, board_context)
            if not hits:
                print("[No retrieved snippets fit the context budget.]")

        if hits:
            srcs = sorted({source_label(h.payload) for h in hits})
            print(f"[retrieved {len(hits)} chunks: {', '.join(srcs)}]")
        if hits or board_context:
            # Retrieved context goes to the model for this turn only; history keeps the
            # plain question so old chunks don't fill the context.
            content = build_rag_prompt(user_input, hits, board_context)
        else:
            content = user_input

        reply = stream_reply(history + [{"role": "user", "content": content}])
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": reply})


def stop(signum, frame) -> None:
    raise SystemExit(128 + signum)


def main() -> None:
    global client, qdrant
    previous_handlers = {}
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[sig] = signal.signal(sig, stop)
        client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
        qdrant = QdrantClient(path=QDRANT_PATH)
        interactive_loop()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        # Let teardown finish if another soft stop arrives; forced kills cannot be caught.
        for sig in previous_handlers:
            signal.signal(sig, signal.SIG_IGN)
        try:
            teardown()
        finally:
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)


if __name__ == "__main__":
    main()
