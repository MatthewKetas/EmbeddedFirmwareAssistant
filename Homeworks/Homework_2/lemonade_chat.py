import time

from openai import OpenAI

# --- Configuration -----------------------------------------------------
BASE_URL = "http://localhost:13305/api/v1"
API_KEY = "lemonade"                        # required by the client lib, but unused/ignored by Lemonade
MODEL = "Qwen3.5-35B-A3B-GGUF"

# Sampling settings. temperature/top_p are standard OpenAI params.
# top_k is Qwen/llama.cpp-specific and isn't in the OpenAI schema, so it
# has to be passed through extra_body instead of as a normal kwarg.
TEMPERATURE = 1.0
TOP_P = 0.9
TOP_K = 40
# ------------------------------------------------------------------------

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
 

def print_usage(usage, elapsed: float) -> None:
    """Print token usage stats and elapsed time, if the server returned usage."""
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

def chat_stream(prompt: str, system: str | None = None) -> None:
    """Send a prompt and print the reply as it streams in."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    start = time.time()
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=TEMPERATURE,
        top_p=TOP_P,
        extra_body={"top_k": TOP_K},
        stream=True,
        stream_options={"include_usage": True},  # asks the server to send usage in the final chunk
    )

    usage = None
    for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta.content
            if delta:
                print(delta, end="", flush=True)
        if chunk.usage:  # only present on the final chunk, if the server supports it
            usage = chunk.usage
    elapsed = time.time() - start

    print()
    print_usage(usage, elapsed)


def interactive_loop():
    """Simple REPL for chatting with the model."""
    print(f"Connected to Lemonade Server at {BASE_URL}, model = {MODEL}")
    print("Type 'exit' or 'quit' to stop.\n")

    history = []
    while True:
        user_input = input("Prompt: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue

        history.append({"role": "user", "content": user_input})

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
        reply = ""
        usage = None
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    print(delta, end="", flush=True)
                    reply += delta
            if chunk.usage:
                usage = chunk.usage
        elapsed = time.time() - start

        print()
        print_usage(usage, elapsed)
        print()

        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    interactive_loop()
