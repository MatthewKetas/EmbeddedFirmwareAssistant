import hashlib
import importlib.util
import math
import os
import re
import shlex
import signal
import sys
import time
import uuid
from collections import Counter
from functools import cache
from itertools import chain, islice
from pathlib import Path

import httpx
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchAny, MatchValue, PointStruct, VectorParams, IsEmptyCondition, PayloadField
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
# Two chat models: turns whose retrieved context contains code go to CODE_MODEL,
# everything else (datasheet questions, /file) goes to the smaller LEXICAL_MODEL.
# Must match the names Lemonade lists (check /api/v1/models).
CODE_MODEL = "Qwen3.6-35B-A3B-GGUF"
LEXICAL_MODEL = "Gemma-4-E4B-it-GGUF"
# Per-model load options. ctx_size sizes the KV cache, so a smaller value frees VRAM.
# llamacpp_args goes to llama-server on load (e.g. "--n-cpu-moe 20"); "" leaves the server's own.
# Thinking is off for both models. On the Milestone 1 RAG prompts the code model spent
# 2,400-4,800 tokens thinking per answer; with it off the answers kept the same key facts.
MODEL_OPTIONS = {
    CODE_MODEL: {"ctx_size": 16_384, "llamacpp_args": "", "thinking": False},
    LEXICAL_MODEL: {"ctx_size": 16_384, "llamacpp_args": "", "thinking": False},
}
CHAT_TOKENIZER = "Qwen/Qwen3.6-35B-A3B"      # CODE_MODEL's tokenizer, for fitting code context
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
# Also rank chunks by shared words (BM25) and merge that with the vector ranking. Embeddings
# missed passages that repeat the question's exact terms: on the Milestone 1 prompts this moved
# the I2C 400 Kbit/s passage from rank 23 to 8 and the power-up timing table from 14 to 6,
# dropped nothing from the top 10, and added about 0.1 s per question.
HYBRID_SEARCH = True
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
    for model in (EMBED_MODEL, CODE_MODEL, LEXICAL_MODEL):
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
    # Use the name as stored on disk. The library keys chunks by file name, and on Windows
    # "esp32.pdf" opens ESP32.pdf, which once left the datasheet indexed twice.
    if p.parent.is_dir():
        names = {entry.name: entry for entry in p.parent.iterdir()}
        if p.name not in names:
            p = next((e for n, e in names.items() if n.lower() == p.name.lower()), p)
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

# Pages that list section titles, links or the change log look similar to almost any question
# but answer none; in ESP32.pdf they filled up to 7 of the 10 retrieval slots.
FRONT_MATTER = {"contents", "list of tables", "list of figures", "revision history",
                "related documentation", "related documentation and resources", "developer zone",
                "products", "contact us", "disclaimer and copyright notice"}
CONTINUED = "cont'd from previous page"
NUMBERED_HEADING = re.compile(r"^([0-9]+(\.[0-9]+)*|[A-Z]\.[0-9]+)\.?\s+\S")


TABLE_CELL = re.compile(r"^[^=\n]{1,120} = ")


def collapse_table_cells(text: str) -> str:
    """Keep each "row, column = value." segment once per chunk.

    Docling repeats a merged table cell once per column it spans; in ESP32.pdf one pin row
    repeated its description nine times, which drowned the useful cells when embedded.
    """
    seen, lines = set(), []
    for line in text.split("\n"):
        parts = re.split(r"(?<=\.)\s+", line)
        kept = []
        for part in parts:
            key = " ".join(part.split())
            if TABLE_CELL.match(part):
                if key in seen:
                    continue
                seen.add(key)
            kept.append(part)
        lines.append(line if len(kept) == len(parts) else " ".join(kept))
    return "\n".join(lines)


def prepare_chunks(texts: list[str]) -> list[tuple[int, str]]:
    """Drop front matter, collapse repeated table cells and give generic headings their section,
    keeping each chunk's index.

    Docling keeps only the nearest heading, so "Feature List" under "4.8.4 I2CInterface"
    never mentions I2C; prefixing the last numbered heading lets retrieval match it.
    """
    kept, section, skipping = [], None, False
    for i, text in enumerate(texts):
        heading, _, body = text.partition("\n")
        name = heading.strip().rstrip(":").lower()
        if name != CONTINUED:
            skipping = name in FRONT_MATTER or "latest version of this document" in body
        if skipping:
            continue
        if NUMBERED_HEADING.match(heading.strip()) and not heading.strip().endswith(":"):
            section = heading.strip()
        elif section:
            text = f"{section} > {text}"
        kept.append((i, collapse_table_cells(text)))
    return kept


def ingest(path_str: str, board_id: str | None = None) -> None:
    path = resolve_path(path_str)
    doc = convert(path)

    chunker = get_chunker()
    chunks = list(chunker.chunk(dl_doc=doc))
    prepared = prepare_chunks([chunker.contextualize(chunk=c) for c in chunks])
    chunks = [chunks[i] for i, _ in prepared]
    texts = [text for _, text in prepared]
    if not texts:
        print("No text extracted.")
        return
    print(f"Embedding {len(texts)} chunks with {EMBED_MODEL}...")
    vectors = embed(texts)
    if UNLOAD_AFTER_INGEST:
        unload_model(EMBED_MODEL)

    ensure_collection()
    # Re-adding the same file replaces its old chunks, including a copy indexed under other case.
    same_file = [s for s in list_sources() if s.lower() == path.name.lower()] or [path.name]
    qdrant.delete(
        COLLECTION,
        points_selector=Filter(must=[FieldCondition(key="source", match=MatchAny(any=same_file))]),
    )
    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{path.name}:{i}")),
            vector=vec,
            payload={"source": path.name, "chunk": i, "page": chunk_page(c), "text": text, "board_id": board_id},
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

def ingest_code(path_str: str, board_id: str | None = None) -> str:
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
                    payload={**payload, "source": source, "revision": str(revision), "board_id": board_id},
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

WORD = re.compile(r"[a-z0-9_]+")


def keyword_rank(question: str, points, k1: float = 1.5, b: float = 0.75) -> list:
    """Points sharing words with the question, best BM25 score first; points sharing none are left out."""
    docs = [WORD.findall(p.payload["text"].lower()) for p in points]
    if not docs:
        return []
    average = sum(map(len, docs)) / len(docs)
    df = Counter(word for doc in docs for word in set(doc))
    words = set(WORD.findall(question.lower()))
    scored = []
    for point, doc in zip(points, docs):
        tf = Counter(doc)
        score = sum(
            math.log(1 + (len(docs) - df[w] + 0.5) / (df[w] + 0.5))
            * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(doc) / average))
            for w in words if tf[w]
        )
        if score > 0:
            scored.append((score, point))
    return [point for _, point in sorted(scored, key=lambda pair: pair[0], reverse=True)]


def retrieve(question: str, only: list[str] | None = None, board_id: str | None = None):
    if not qdrant.collection_exists(COLLECTION) or qdrant.count(COLLECTION).count == 0:
        return []
    must = []
    if only:
        must.append(FieldCondition(key="source", match=MatchAny(any=only)))
    if board_id:
        # This board's chunks, plus untagged ones (indexed with no board selected).
        must.append(Filter(should=[
            FieldCondition(key="board_id", match=MatchValue(value=board_id)),
            IsEmptyCondition(is_empty=PayloadField(key="board_id")),
        ]))
    flt = Filter(must=must) if must else None
    qvec = embed_query(question)
    if UNLOAD_AFTER_QUERY:
        unload_model(EMBED_MODEL)
    # Fetch extra so identical chunks (a file indexed twice, repeated boilerplate) do not use up slots.
    depth = TOP_N_CHUNKS * 3
    candidates = qdrant.query_points(COLLECTION, query=qvec, limit=depth, query_filter=flt).points
    if HYBRID_SEARCH:
        # Reciprocal rank fusion: a chunk near the top of both rankings wins.
        everything, _ = qdrant.scroll(COLLECTION, scroll_filter=flt, limit=100_000,
                                      with_payload=True, with_vectors=False)
        fused, by_id = Counter(), {}
        for ranking in (candidates, keyword_rank(question, everything)[:depth]):
            for rank, point in enumerate(ranking, 1):
                fused[point.id] += 1 / (60 + rank)
                by_id.setdefault(point.id, point)
        candidates = sorted(by_id.values(), key=lambda point: fused[point.id], reverse=True)
    hits, seen = [], set()
    for point in candidates:
        text = " ".join(point.payload["text"].split())
        if text not in seen:
            seen.add(text)
            hits.append(point)
    return hits[:TOP_N_CHUNKS]


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
        f"Answer the question using only the context below. Cite sources like {citation}. "
        # Without this, models filled gaps from memory, e.g. "U0TXD is GPIO3 in typical pinouts".
        "Every value, pin number, register or name you state must appear in the context; "
        "do not fill gaps from general knowledge. If the context lacks something the question "
        "asks for, say that it is not in the context.\n\n"
        f"=== CONTEXT ===\n{context}\n=== END CONTEXT ===\n\n"
        f"Question: {question}"
    )


def fit_code_context(question: str, hits, history: list, board_context: str = ""):
    tokenizer = get_tokenizer(CHAT_TOKENIZER)

    def prompt_tokens(selected):
        messages = history + [{"role": "user", "content": build_rag_prompt(question, selected, board_context)}]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        return len(tokenizer.encode(text, add_special_tokens=False, verbose=False))

    limit = min(prompt_tokens([]) + RAG_CONTEXT_TOKENS, MODEL_OPTIONS[CODE_MODEL]["ctx_size"] - RAG_REPLY_TOKENS)
    selected = []
    for hit in hits:
        if prompt_tokens(selected + [hit]) <= limit:
            selected.append(hit)
    return selected


def pick_model(hits) -> str:
    return CODE_MODEL if any("file" in h.payload for h in hits) else LEXICAL_MODEL


def print_stats(stats: dict) -> None:
    # Load, prefill and decode are reported apart: one blended tok/s hides which one is slow.
    parts = [stats["model"], f"load {stats['load_s']:.2f}s"]
    if stats["ttft_s"] is not None:
        prefill = f"prefill {stats['ttft_s']:.2f}s"
        if stats["prompt_tokens"] is not None:
            prefill += f" ({stats['prompt_tokens']} tok"
            prefill += f", {stats['prefill_tps']:.0f} tok/s)" if stats["prefill_tps"] else ")"
        parts.append(prefill)
    if stats["completion_tokens"] is not None:
        decode = f"decode {stats['completion_tokens']} tok"
        parts.append(decode + (f" @ {stats['decode_tps']:.1f} tok/s" if stats["decode_tps"] else ""))
    if stats["thinking_tokens"]:
        parts.append(f"thinking ~{stats['thinking_tokens']} tok")
    parts.append(f"total {stats['total_s']:.2f}s")
    print(f"[{' | '.join(parts)}]")


# A short response agreement sent ahead of every conversation. Qwen wrote 1,500-3,000 tokens per
# datasheet answer, most of its ~58 s; small models follow a few rules better than a long list.
ANSWER_RULES = (
    "Answer rules:\n"
    "- Lead with the direct answer, then the supporting details.\n"
    # "Briefly", "skip background" and a 350-word cap cut answers 40-60% but dropped key facts
    # (supply range, strapping and input-only pins): 76% -> 67% for Gemma, 95% -> 86% for Qwen.
    "- Cover every part of the question in order, with the values, limits and pin cautions that bear on it; "
    "leave out unrelated background.\n"
    "- When context is provided, take facts only from it and say in one line what it lacks.\n"
    "- Label design inferences as inferences."
)
CODE_REVIEW_RULES = (
    "\nFor code reviews: list findings most severe first, each with file, line and a one-line fix; "
    "put real bugs before style nits."
)


def system_prompt(model: str) -> str:
    return ANSWER_RULES + (CODE_REVIEW_RULES if model == CODE_MODEL else "")


def stream_reply(messages: list, model: str, echo: bool = True) -> tuple[str, dict]:
    options = MODEL_OPTIONS[model]
    start = time.monotonic()
    # Context size is a model-load option, not a chat-completion option. Lemonade keeps one
    # LLM loaded by default, so switching between the two chat models reloads; load_s shows it.
    load = {"model_name": model, "ctx_size": options["ctx_size"]}
    if options["llamacpp_args"]:
        load["llamacpp_args"] = options["llamacpp_args"]
    response = httpx.post(f"{BASE_URL}/load", json=load, timeout=120)
    # Lemonade's own message names the problem (e.g. an unknown model); the HTTP status alone does not.
    if response.status_code >= 400:
        raise RuntimeError(f"Could not load {model}: {response.status_code} {response.text[:300]}")
    if response.json().get("status") == "error":
        raise RuntimeError(f"Could not load {model}: {response.json().get('message')}")
    loaded = time.monotonic()
    extra = {"top_k": TOP_K}
    if not options["thinking"]:
        extra["enable_thinking"] = False   # Lemonade extension
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt(model)}] + messages,
        temperature=TEMPERATURE,
        top_p=TOP_P,
        extra_body=extra,
        stream=True,
        stream_options={"include_usage": True},
    )
    if echo:
        print("Response: ", end="", flush=True)
    reply, usage, timings = "", None, None
    first = answer = last = None
    thinking = 0
    with stream:
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                # Thinking arrives as reasoning_content; it is counted, not shown or kept.
                if getattr(delta, "reasoning_content", None):
                    thinking += 1
                    first = first or time.monotonic()
                    last = time.monotonic()
                if delta.content:
                    first = first or time.monotonic()
                    answer = answer or time.monotonic()
                    last = time.monotonic()
                    if echo:
                        print(delta.content, end="", flush=True)
                    reply += delta.content
            if chunk.usage:
                usage = chunk.usage
            timings = getattr(chunk, "timings", None) or timings
    end = time.monotonic()
    if echo:
        print()
    completion = usage.completion_tokens if usage else None
    decode_tps = (timings or {}).get("predicted_per_second")
    if decode_tps is None and completion and first and last > first:
        decode_tps = (completion - 1) / (last - first)  # tokens after the first, over their time
    stats = {
        "model": model,
        "load_s": loaded - start,
        "ttft_s": first - loaded if first else None,
        "answer_s": answer - loaded if answer else None,
        "prompt_tokens": usage.prompt_tokens if usage else None,
        "completion_tokens": completion,
        "thinking_tokens": thinking,
        "prefill_tps": (timings or {}).get("prompt_per_second"),
        "decode_tps": decode_tps,
        "total_s": end - start,
    }
    print_stats(stats)
    if echo:
        print()
    return reply, stats


HELP = (
    "Commands:\n"
    "  /add <file>              index a file (from the datasheets folder) into the library (not case sensitive)\n"
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
    print(f"Code: {CODE_MODEL} | Lexical: {LEXICAL_MODEL} | Embeddings: {EMBED_MODEL} | Qdrant: {QDRANT_PATH}")
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
            ingest(user_input[5:], board_id)
            continue

        if low == "/code":
            print("Usage: /code <directory>\n")
            continue

        if low.startswith("/code "):
            only = [ingest_code(user_input[6:], board_id)]
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
            history.append({"role": "assistant", "content": stream_reply(history, LEXICAL_MODEL)[0]})
            continue

        # Normal question: retrieve from the library if there is one.
        board_context = board_map.context(board_id, user_input) if board_id else ""
        hits = retrieve(user_input, only, board_id)
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

        reply, _ = stream_reply(history + [{"role": "user", "content": content}], pick_model(hits))
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
