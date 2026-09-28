import time
from pathlib import Path

from openai import OpenAI

# --- Configuration -----------------------------------------------------
BASE_URL = "http://localhost:13305/api/v1"
API_KEY = "lemonade"  # required by the client lib, ignored by Lemonade
MODEL = "Qwen3.5-35B-A3B-GGUF"

TEMPERATURE = 1.0
TOP_P = 0.9
TOP_K = 40  # llama.cpp-specific, passed via extra_body

MAX_CHARS = 128_000  # ~15k tokens; raise/lower to match your server's context size
# -----------------------------------------------------------------------

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

# Docling is slow to import/initialise, so create the converter lazily, once.
_converter = None


def get_converter():
    global _converter
    if _converter is None:
        print("Loading Docling (first run downloads its models, can take a while)...")
        from docling.document_converter import DocumentConverter
        _converter = DocumentConverter()
    return _converter


def file_to_markdown(path: str) -> str:
    """Convert a file to Markdown with Docling.

    Bare filenames are looked up in the Downloads folder. Docling handles
    PDF, DOCX, PPTX, XLSX, HTML, images (OCR), and more.
    """
    p = Path(path.strip('"\'')).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p

    result = get_converter().convert(str(p))
    return result.document.export_to_markdown()  # forces markdown output


def print_usage(usage, elapsed: float) -> None:
    if not usage:
        print(f"[usage stats not returned by server | time: {elapsed:.2f}s]")
        return
    tps = usage.completion_tokens / elapsed if elapsed > 0 else 0
    print(
        f"[tokens: prompt={usage.prompt_tokens}, "
        f"completion={usage.completion_tokens}, "
        f"total={usage.total_tokens} | "
        f"time: {elapsed:.2f}s | ~{tps:.1f} tok/s]"
    )


def stream_reply(history: list) -> str:
    start = time.time()
    stream = client.chat.completions.create(
        model=MODEL,
        messages=history,
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


def interactive_loop():
    print(f"Connected to Lemonade Server at {BASE_URL}, model = {MODEL}")
    print("Commands:  /file <path-or-name> [question]   |   exit / quit")

    history = []
    while True:
        user_input = input("Prompt: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue

        if user_input.startswith("/file "):
            parts = user_input[6:].split(maxsplit=1)
            filename = parts[0]
            question = parts[1] if len(parts) > 1 else "Summarize this document."

            try:
                md = file_to_markdown(filename)
            except Exception as e:
                print(f"Could not convert file: {e}\n")
                continue

            if len(md) > MAX_CHARS:
                print(f"Warning: {len(md):,} chars, truncating to {MAX_CHARS:,}.")
                md = md[:MAX_CHARS]

            print(f"Loaded {filename} ({len(md):,} chars of markdown)")
            user_input = (
                f"{question}\n\n"
                f"--- BEGIN DOCUMENT: {filename} ---\n{md}\n--- END DOCUMENT ---"
            )

        history.append({"role": "user", "content": user_input})
        reply = stream_reply(history)
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    interactive_loop()