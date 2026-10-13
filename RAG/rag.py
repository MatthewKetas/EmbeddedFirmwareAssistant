import hashlib
import importlib.util
import os
import shlex
import time
import uuid
from pathlib import Path

import httpx
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchAny, MatchValue, PointStruct, VectorParams,
)

# Library, cache and history live next to this script, wherever you launch it from.
SCRIPT_DIR = Path(__file__).resolve().parent

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
# Must match the name Lemonade lists for your embedding model (check /api/v1/models)
EMBED_MODEL = "Qwen3-Embedding-8B-GGUF"
EMBED_DIM = 4096                            # Qwen3-Embedding-8B output size

TEMPERATURE = 1.0
TOP_P = 0.9
TOP_K = 40

QDRANT_PATH = str(SCRIPT_DIR / "qdrant_data")   # on-disk vector library, no server needed
COLLECTION = "docs"
TOP_N_CHUNKS = 6                            # chunks sent to the chat model per question
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

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
qdrant = QdrantClient(path=QDRANT_PATH)

_converter = None
_chunker = None


def unload_embed_model() -> None:
    """Ask Lemonade to unload the embedding model. Failure is non-fatal."""
    try:
        r = httpx.post(f"{BASE_URL}/unload", json={"model_name": EMBED_MODEL}, timeout=30)
        if r.status_code == 200:
            print(f"[unloaded {EMBED_MODEL}]")
        else:
            print(f"[unload returned {r.status_code}: {r.text[:200]}]")
    except Exception as e:
        print(f"[could not unload embedding model: {e}]")


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


def get_chunker():
    global _chunker
    if _chunker is None:
        from docling.chunking import HybridChunker
        try:
            from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
            from transformers import AutoTokenizer
            tok = HuggingFaceTokenizer(
                tokenizer=AutoTokenizer.from_pretrained(CHUNK_TOKENIZER),
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
        unload_embed_model()

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


def retrieve(question: str, only: list[str] | None = None):
    if not qdrant.collection_exists(COLLECTION) or qdrant.count(COLLECTION).count == 0:
        return []
    flt = None
    if only:
        flt = Filter(must=[FieldCondition(key="source", match=MatchAny(any=only))])
    qvec = embed_query(question)
    if UNLOAD_AFTER_QUERY:
        unload_embed_model()
    res = qdrant.query_points(
        COLLECTION, query=qvec, limit=TOP_N_CHUNKS, query_filter=flt,
    )
    return res.points


def list_sources() -> list[str]:
    if not qdrant.collection_exists(COLLECTION):
        return []
    pts, _ = qdrant.scroll(COLLECTION, limit=100_000, with_payload=["source"], with_vectors=False)
    return sorted({p.payload["source"] for p in pts})


def build_rag_prompt(question: str, hits) -> str:
    parts = []
    for h in hits:
        page = f", p.{h.payload['page']}" if h.payload.get("page") else ""
        parts.append(f"[{h.payload['source']}{page}]\n{h.payload['text']}")
    context = "\n\n---\n\n".join(parts)
    return (
        "Answer the question using the context below. Cite sources like [file, p.N]. "
        "If the answer isn't in the context, say so.\n\n"
        f"=== CONTEXT ===\n{context}\n=== END CONTEXT ===\n\n"
        f"Question: {question}"
    )


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
    "  /wipe                    delete the whole library\n"
    "  /quit                    exit\n"
    "Press Tab to complete commands and file names; Up/Down for previous prompts.\n"
)

COMMANDS = ["/add", "/file", "/list", "/only", "/clear", "/wipe", "/quit"]


def make_prompt():
    """Return a prompt function with Tab completion, or plain input() if prompt_toolkit is missing."""
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
    return session.prompt


def interactive_loop():
    print(f"Chat: {CHAT_MODEL} | Embeddings: {EMBED_MODEL} | Qdrant: {QDRANT_PATH}")
    print(f"Script folder: {SCRIPT_DIR}")
    print(f"Datasheets:    {DOCS_DIR}{'' if DOCS_DIR.is_dir() else '  (NOT FOUND)'}")
    print(HELP)

    ask = make_prompt()
    history: list[dict] = []
    only: list[str] | None = None

    while True:
        try:
            user_input = ask("Prompt: ").strip()
        except KeyboardInterrupt:   # Ctrl+C clears the current line
            continue
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
            try:
                names = shlex.split(user_input[6:], posix=False)
            except ValueError as e:
                print(f"Could not parse file list: {e}\n")
                continue
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
            try:
                ingest(user_input[5:])
            except Exception as e:
                print(f"Could not add file: {e}\n")
            continue

        if low.startswith("/file "):
            parts = user_input[6:].split(maxsplit=1)
            question = parts[1] if len(parts) > 1 else "Summarize this document."
            try:
                md = convert(resolve_path(parts[0])).export_to_markdown()
            except Exception as e:
                print(f"Could not convert file: {e}\n")
                continue
            if len(md) > MAX_CHARS:
                print(f"Warning: {len(md):,} chars, truncating to {MAX_CHARS:,}.")
                md = md[:MAX_CHARS]
            content = f"{question}\n\n--- BEGIN DOCUMENT ---\n{md}\n--- END DOCUMENT ---"
            history.append({"role": "user", "content": content})
            history.append({"role": "assistant", "content": stream_reply(history)})
            continue

        # Normal question: retrieve from the library if there is one.
        try:
            hits = retrieve(user_input, only)
        except Exception as e:
            print(f"[retrieval failed: {e}] answering without documents\n")
            hits = []

        if hits:
            srcs = sorted({f"{h.payload['source']} p.{h.payload['page']}" if h.payload.get('page')
                           else h.payload['source'] for h in hits})
            print(f"[retrieved {len(hits)} chunks: {', '.join(srcs)}]")
            # Retrieved context goes to the model for this turn only; history keeps the
            # plain question so old chunks don't fill the context.
            messages = history + [{"role": "user", "content": build_rag_prompt(user_input, hits)}]
        else:
            messages = history + [{"role": "user", "content": user_input}]

        reply = stream_reply(messages)
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    interactive_loop()