# Local RAG Chat (Docling + Lemonade + Qdrant)

A command-line chat that answers questions about your own documents, fully on your machine.

- **Docling** converts PDFs and other files into clean, structured text.
- **Lemonade Server** runs the Qwen models locally: one to embed text, one to chat.
- **Qdrant** stores the embedded chunks on disk so you can search them later.

---

## Requirements at a glance

| What | Install | Role in the project |
|---|---|---|
| Python 3.10+ | python.org | Runs `rag_chat.py` (the code uses `list[str] \| None` syntax, which needs 3.10 or newer) |
| Lemonade Server | Separate app (see below) | Serves the chat and embedding models over a local OpenAI-style API |
| `docling` | `pip install docling` | Converts documents to text and splits them into chunks |
| `openai` | `pip install openai` | Client used to talk to Lemonade's API |
| `qdrant-client` | `pip install qdrant-client` | The vector library, stored in `qdrant_data/` |
| `httpx` | `pip install httpx` | Sends the "unload model" request to Lemonade |
| `prompt_toolkit` | `pip install prompt_toolkit` | Tab completion and Up/Down prompt history |

---

## Quick install

### 1. Create a virtual environment (optional)

This keeps the project's packages separate from the rest of your system.

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install the Python packages

```bash
pip install docling openai qdrant-client httpx prompt_toolkit
```

**Optional: GPU for Docling.** Docling installs PyTorch automatically, usually the CPU build. If you have an NVIDIA GPU and want Docling to use it, install the CUDA build of PyTorch first, using the command for your setup from https://pytorch.org/get-started/locally/, then install Docling. The script uses `AcceleratorDevice.AUTO`, so it picks up the GPU on its own.

### 3. Install and start Lemonade Server

Lemonade is a desktop app and server, not a pip package. Download it from https://lemonade-server.ai and start it. The script expects it at:

```
http://localhost:13305/api/v1
```

If yours runs on a different port, change `BASE_URL` at the top of `rag_chat.py`.

### 4. Download the two models in Lemonade

Use Lemonade's model manager to pull both models:

| Model name in Lemonade | Used for | Config setting |
|---|---|---|
| `Qwen3.6-35B-A3B-GGUF` | Answering your questions | `CHAT_MODEL` |
| `Qwen3-Embedding-8B-GGUF` | Turning text into vectors for search | `EMBED_MODEL` |

The names in the script must match exactly what Lemonade lists. To check, open `http://localhost:13305/api/v1/models` in a browser.

### 5. Run it

```bash
python rag_chat.py
```

---

## What each package does in the project

### docling
The document-processing engine. In `rag_chat.py` it:
- **Converts files** (`convert()`): reads PDFs with layout detection and table-structure recognition (TableFormer), then produces a structured `DoclingDocument`. Results are cached in `.docling_cache/`, so each file is only converted once.
- **Chunks text** (`get_chunker()`): `HybridChunker` splits the document into search-sized pieces that follow its headings. `contextualize()` adds the heading path to each chunk so the chunks make sense on their own.
- **Exports Markdown** for the `/file` command, which pastes a whole document into the chat.

Installing Docling also pulls in several packages you don't install yourself:
- **docling-core:** the document data model, plus saving and loading JSON for the cache.
- **torch:** runs Docling's layout and table models.
- **transformers:** provides the tokenizer that `HybridChunker` uses to measure chunk size.
- **huggingface_hub:** downloads Docling's models and the tokenizer on first use. This is where the "unauthenticated requests to the HF Hub" warning comes from.

### openai
The official OpenAI Python client, pointed at Lemonade instead of OpenAI (`base_url=BASE_URL`). Nothing is sent to OpenAI. It's used for:
- `client.embeddings.create(...)`: embedding document chunks and your questions with Qwen3-Embedding.
- `client.chat.completions.create(..., stream=True)`: streaming answers from the Qwen chat model.

The `api_key` value is required by the client, but Lemonade ignores it.

### qdrant-client
The vector database, running in local mode (`QdrantClient(path=...)`). No separate Qdrant server is needed; everything is stored in the `qdrant_data/` folder. It's used to:
- create the `docs` collection (4096-dimension vectors, cosine distance),
- store chunks along with their source file, page number and text,
- find the closest chunks to each question (`query_points`),
- filter search to specific files for `/only`, and power `/list` and `/wipe`.

### httpx
A small HTTP client. It's used only in `unload_embed_model()`, which calls Lemonade's `/unload` endpoint to free the 8B embedding model's memory after `/add` finishes. It's already installed as a dependency of `openai`, but it's listed here because the script imports it directly.

### prompt_toolkit
Replaces the plain `input()` prompt with:
- Tab completion for commands, file paths (`/add`, `/file`) and indexed file names (`/only`),
- Up/Down history saved in `.chat_history`,
- Ctrl+C to clear the current line instead of quitting.

If it isn't installed, the script falls back to a plain prompt.

---

## Folders the script creates

All of these are created next to `rag_chat.py`:

| Folder / file | Contents | Safe to delete? |
|---|---|---|
| `qdrant_data/` | Your indexed library | Yes, but you'll need to re-`/add` your files (same effect as `/wipe`) |
| `.docling_cache/` | Cached document conversions | Yes; files are reconverted on the next `/add` |
| `.chat_history` | Prompt history for the Up arrow | Yes |

Downloaded models are stored outside the project:
- **Docling models and tokenizer:** the Hugging Face cache, usually `~/.cache/huggingface`.
- **Qwen models:** managed by Lemonade.