import argparse
import json
import re
import subprocess
import tempfile
import time
from math import comb
from pathlib import Path

import httpx
from openai import OpenAI, OpenAIError

# RUN WITH THE FOLLOWING: .venv/bin/python 'pass@k/run.py' --runs 5

ROOT = Path(__file__).resolve().parent
BASE_URL = "http://localhost:13305/api/v1"
DEFAULT_MODEL = "Qwen3.6-35B-A3B-GGUF"
GROUPS = ("io", "summary", "prediction", "pipeline")
SAMPLING = {"temperature": 1.0, "top_p": 0.9, "max_tokens": 4096}
CONTEXT_TOKENS = 16_384   # same as RAG/rag.py; room for the prompt plus a long thinking-on answer


def build_grader():
    print("Preparing the Critter evaluator in Docker...", flush=True)
    return subprocess.check_output(
        ["docker", "build", "--quiet", "--tag", "critter-passk",
         "--file", str(ROOT / "evaluator/Dockerfile"), str(ROOT)],
        text=True,
    ).strip()


def grade(image, submission):
    result = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "--read-only",
         "--tmpfs", "/tmp:rw,exec,size=32m", "--memory", "256m", "--cpus", "1",
         "--pids-limit", "32", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
         "--user", "65534:65534", "--mount", f"type=bind,src={submission},dst=/submission.c,readonly",
         image],
        capture_output=True, text=True, errors="replace", timeout=60,
    )
    if result.returncode == 2:
        return False, dict.fromkeys(GROUPS, False), result.stderr
    result.check_returncode()
    verdicts = dict(line.split("=", 1) for line in result.stdout.splitlines())
    if verdicts.keys() != set(GROUPS) or set(verdicts.values()) - {"pass", "fail"}:
        raise ValueError(f"Unexpected evaluator output: {result.stdout!r}")
    return True, {group: verdicts[group] == "pass" for group in GROUPS}, result.stderr


def summarize(attempts):
    n = len(attempts)
    c = sum(all(attempt["checks"].values()) for attempt in attempts)
    return {
        "samples": n,
        "compiled": sum(attempt["compiled"] for attempt in attempts),
        "passed_all": c,
        "passed_by_group": {group: sum(a["checks"][group] for a in attempts) for group in GROUPS},
        "pass_at_k": {str(k): 1 - comb(n - c, k) / comb(n, k) for k in range(1, n + 1)},
    }


def run(model, count, image, output, thinking, max_tokens):
    prompt = (ROOT / "critter.c").read_text(encoding="utf-8")
    attempts = []
    sampling = {**SAMPLING, "max_tokens": max_tokens}
    report = {"model": model, "sampling": sampling, "thinking": thinking, "requested_samples": count,
              "attempts": attempts}
    # Lemonade extension; "on" sends nothing, so the model keeps its own default.
    extra_body = {} if thinking == "on" else {"enable_thinking": False}
    # Load with a known context size instead of the server default, which may be smaller.
    response = httpx.post(f"{BASE_URL}/load", json={"model_name": model, "ctx_size": CONTEXT_TOKENS}, timeout=300)
    if response.status_code >= 400 or response.json().get("status") == "error":
        raise SystemExit(f"Could not load {model}: {response.status_code} {response.text[:300]}")
    # Thinking-on answers can run past 10,000 tokens at 15-50 tok/s, so allow an hour per sample.
    with OpenAI(base_url=BASE_URL, api_key="lemonade", timeout=3600, max_retries=0) as client:
        for i in range(1, count + 1):
            print(f"Generating sample {i}/{count}...", flush=True)
            start = time.monotonic()
            response = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], extra_body=extra_body, **sampling,
            )
            generation_seconds = round(time.monotonic() - start, 3)
            choice = response.choices[0]
            raw = choice.message.content or ""
            (output / f"{i:02d}.response.txt").write_text(raw, encoding="utf-8")
            fence = re.fullmatch(r"```(?:c)?[ \t]*\r?\n(.*?)\r?\n```", raw.strip(), re.DOTALL | re.IGNORECASE)
            submission = output / f"{i:02d}.c"
            submission.write_text((fence[1] if fence else raw).strip() + "\n", encoding="utf-8")
            compiled, checks, diagnostics = grade(image, submission)
            (output / f"{i:02d}.judge.txt").write_text(diagnostics, encoding="utf-8")
            attempts.append({
                "sample": i,
                "compiled": compiled,
                "checks": checks,
                "generation_seconds": generation_seconds,
                "finish_reason": choice.finish_reason,
                "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                "completion_tokens": response.usage.completion_tokens if response.usage else None,
            })
            report.update(summarize(attempts))
            (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            status = "pass" if all(checks.values()) else "fail" if compiled else "compile error"
            print(f"Sample {i}: {status}", flush=True)
    return summarize(attempts)


def main():
    parser = argparse.ArgumentParser(description="Generate and evaluate independent Critter implementations.")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--thinking", choices=["on", "off"], default="on")
    parser.add_argument("--max-tokens", type=int, default=SAMPLING["max_tokens"],
                        help="reply cap, thinking included; 4096 cut off every thinking-on sample")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if not 1 <= args.max_tokens <= CONTEXT_TOKENS - 2048:
        parser.error(f"--max-tokens must be 1 to {CONTEXT_TOKENS - 2048}")
    try:
        image = build_grader()
        results = ROOT / "results"
        results.mkdir(exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix=time.strftime("%Y%m%d-%H%M%S-"), dir=results))
        print(f"Results: {output}", flush=True)
        print(json.dumps(run(args.model, args.runs, image, output, args.thinking, args.max_tokens), indent=2))
    except FileNotFoundError as error:
        if error.filename == "docker":
            raise SystemExit("Docker is required to run the evaluator.") from error
        raise
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr or "Docker evaluator failed. Check that Docker Desktop is running.") from error
    except OpenAIError as error:
        raise SystemExit(f"Lemonade request failed: {error}") from error


if __name__ == "__main__":
    main()
