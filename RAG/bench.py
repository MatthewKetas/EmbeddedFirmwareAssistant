"""Time the chat models on the Milestone 1 prompts, with and without retrieval.

Each answer is saved next to its timings so it can be scored x/5 by hand.
Stop rag.py first: both open the same on-disk Qdrant library.

    python RAG/bench.py --models lexical code
    python RAG/bench.py --models code --label n-cpu-moe-20 --llamacpp-args "--n-cpu-moe 20"
"""
import argparse
import json
import re
import statistics
import time
from pathlib import Path

import rag

PROMPTS = rag.SCRIPT_DIR.parent / "reading-and-background" / "milestone-data-collection" / "milestone-1.md"
RESULTS = rag.SCRIPT_DIR / "bench_results"


def load_prompts() -> dict[str, str]:
    # The milestone report is the record of the prompts; read them from it instead of copying.
    text = PROMPTS.read_text(encoding="utf-8")
    return dict(re.findall(r"^### (P\d+)\..*?```text\n(.*?)\n```", text, re.MULTILINE | re.DOTALL))


def ask(model: str, question: str, use_rag: bool, board_id: str | None) -> tuple[str, dict, int]:
    content, hits = question, []
    if use_rag:
        board_context = rag.board_map.context(board_id, question) if board_id else ""
        hits = rag.retrieve(question, None, board_id)
        if any("file" in h.payload for h in hits):
            hits = rag.fit_code_context(question, hits, [], board_context)
        if hits or board_context:
            content = rag.build_rag_prompt(question, hits, board_context)
    reply, stats = rag.stream_reply([{"role": "user", "content": content}], model)
    return reply, stats, len(hits)


def median(rows, key):
    values = [r[key] for r in rows if r[key] is not None]
    return f"{statistics.median(values):.2f}" if values else "-"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", default=["lexical", "code"],
                        help="'lexical', 'code' or a Lemonade model name")
    parser.add_argument("--mode", choices=["rag", "norag", "both"], default="both")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--prompts", nargs="+", help="e.g. P1 P3 (default: all)")
    parser.add_argument("--board", help="board id for knowledge-map context, e.g. esp-32")
    parser.add_argument("--label", default="", help="names this configuration, e.g. q4_k_m")
    parser.add_argument("--ctx", type=int, help="override ctx_size for every model")
    parser.add_argument("--llamacpp-args", help="override llamacpp_args for every model")
    parser.add_argument("--thinking", choices=["on", "off"], help="override thinking for every model")
    args = parser.parse_args()

    prompts = load_prompts()
    if args.prompts:
        prompts = {k: prompts[k] for k in args.prompts}
    models = [{"lexical": rag.LEXICAL_MODEL, "code": rag.CODE_MODEL}.get(m, m) for m in args.models]
    for model in models:
        options = rag.MODEL_OPTIONS.setdefault(model, dict(rag.MODEL_OPTIONS[rag.LEXICAL_MODEL]))
        if args.ctx:
            options["ctx_size"] = args.ctx
        if args.llamacpp_args is not None:
            options["llamacpp_args"] = args.llamacpp_args
        if args.thinking:
            options["thinking"] = args.thinking == "on"
    modes = {"rag": [True], "norag": [False], "both": [True, False]}[args.mode]

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{time.strftime('%Y%m%d-%H%M%S')}{'-' + args.label if args.label else ''}.jsonl"
    rows = []
    rag.client = rag.OpenAI(base_url=rag.BASE_URL, api_key=rag.API_KEY)
    rag.qdrant = rag.QdrantClient(path=rag.QDRANT_PATH)
    try:
        # Model outermost: Lemonade keeps one LLM loaded, so this reloads once per model.
        for model in models:
            for use_rag in modes:
                for pid, question in prompts.items():
                    for run in range(1, args.runs + 1):
                        print(f"\n=== {model} | {'RAG' if use_rag else 'no RAG'} | {pid} run {run} ===")
                        reply, stats, n_hits = ask(model, question, use_rag, args.board)
                        row = {"label": args.label, "prompt": pid, "run": run, "rag": use_rag,
                               "chunks": n_hits, **rag.MODEL_OPTIONS[model], **stats, "answer": reply}
                        rows.append(row)
                        with out.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(row) + "\n")
    finally:
        rag.teardown()

    print(f"\nSaved {len(rows)} answers to {out}\n")
    print("| model | RAG | runs | load s | prefill s | first answer s | decode tok/s | thinking tok | total s |")
    print("|---|---|---|---|---|---|---|---|---|")
    for model in models:
        for use_rag in modes:
            group = [r for r in rows if r["model"] == model and r["rag"] == use_rag]
            print(f"| {model} | {'yes' if use_rag else 'no'} | {len(group)} | {median(group, 'load_s')} | "
                  f"{median(group, 'ttft_s')} | {median(group, 'answer_s')} | {median(group, 'decode_tps')} | "
                  f"{median(group, 'thinking_tokens')} | {median(group, 'total_s')} |")
    print("\nMedians. The first load of each model includes moving it into memory.")


if __name__ == "__main__":
    main()
