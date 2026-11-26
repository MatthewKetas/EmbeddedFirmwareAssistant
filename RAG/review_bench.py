"""Time the code model's reviews of small C files with planted bugs, with and without the answer rules.

Each file in review_cases/ has known bugs, the most severe listed first. A bug counts as found when
the review matches its pattern; the snippets are printed for a person to confirm. "Severe first"
means the most severe bug is mentioned before the file's other planted bug.
Stop rag.py first if it is running: both talk to the same Lemonade server.

    python RAG/review_bench.py --rules both --runs 3 --label review
"""
import argparse
import json
import re
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

import rag

CASES_DIR = rag.SCRIPT_DIR / "review_cases"
RESULTS = rag.SCRIPT_DIR / "bench_results"
QUESTION = "Review this code for bugs."
FLAGS = re.I | re.S
# file -> bugs, most severe first: (name, text on the bug's line, pattern a review that found it matches).
BUGS = {
    "uart_ring.c": [
        ("wrap check lets head reach RB_SIZE: writes past the buffer", "if (next > RB_SIZE)",
         r"off[- ]by[- ]one|out[- ]of[- ]bounds|past the end|beyond the end|buf\[RB_SIZE\]|>=\s*RB_SIZE|==\s*RB_SIZE"),
        ("no full check: ISR overwrites unread bytes", "rx.head = next;",
         r"\bfull\b|overwrit|overrun|next\s*==\s*(rx\.)?tail|tail\s*==\s*next"),
    ],
    "adc_average.c": [
        ("uint16_t sum overflows: 64 x 4095 > 65535", "uint16_t sum = 0;",
         r"\bsum\b.{0,120}(overflow|uint32|wrap)|(overflow|uint32_t).{0,120}\bsum\b"),
        ("divides by count without checking for zero", "return sum / count;",
         r"divi(de|sion) by zero|count\s*==\s*0|zero\s+(count|samples)|count\s+(is|of)\s+(0|zero)"),
    ],
    "sensor_i2c.c": [
        ("len is not checked against buf[4]: buffer overflow", "uint8_t buf[4];",
         r"\blen\b.{0,120}(overflow|exceed|bound|larger|greater|> ?4|sizeof)|(overflow|bounds).{0,120}\blen\b"),
        ("i2c_write result is ignored", "i2c_write(SENSOR_ADDR, &reg, 1);",
         r"(return value|result|ignor|unchecked|not checked|error).{0,80}i2c_write|i2c_write.{0,80}(return value|result|ignor|unchecked|not checked)"),
    ],
    "tick_timer.c": [
        ("tick_flag and tick_ms are not volatile: wait_for_tick can spin forever", "static bool tick_flag;",
         r"volatile"),
        ("elapsed_since returns 0 when the counter wraps", "if (now < start) {",
         r"(wrap|overflow|roll ?over).{0,120}(now|start|tick|millis|elapsed)|(now|start|tick_ms|elapsed_since).{0,120}(wrap|roll ?over)"),
    ],
}


def case_hit(name: str) -> SimpleNamespace:
    """The file as one retrieved code chunk, labelled the way /code labels repository snippets."""
    text = (CASES_DIR / name).read_text(encoding="utf-8")
    return SimpleNamespace(payload={"source": str(CASES_DIR), "file": name, "start_line": 1,
                                    "end_line": len(text.splitlines()), "text": text})


def bug_line(name: str, anchor: str) -> int:
    lines = (CASES_DIR / name).read_text(encoding="utf-8").splitlines()
    return next(i for i, line in enumerate(lines, 1) if anchor in line)


def score(answer: str, name: str) -> dict:
    """Which planted bugs the review names, and whether the most severe one comes first."""
    positions = {}
    for bug, _, pattern in BUGS[name]:
        if match := re.search(pattern, answer, FLAGS):
            positions[bug] = match.start()
    severe = BUGS[name][0][0]
    return {"found": [bug for bug, *_ in BUGS[name] if bug in positions], "of": len(BUGS[name]),
            "severe_first": severe in positions and positions[severe] == min(positions.values())}


def snippets(answer: str, name: str, found: list[str]) -> list[tuple[str, str]]:
    out = []
    for bug, _, pattern in BUGS[name]:
        if bug in found and (match := re.search(pattern, answer, FLAGS)):
            out.append((bug, " ".join(answer[max(0, match.start() - 80):match.end() + 60].split())))
    return out


def summarize(rows: list[dict]) -> list[tuple]:
    """(rules, reviews, bugs found, bugs total, severe first, median tokens, median total s) per rules setting."""
    out = []
    for rules in dict.fromkeys(r["rules"] for r in rows):
        group = [r for r in rows if r["rules"] == rules]
        out.append((rules, len(group), sum(len(r["found"]) for r in group), sum(r["of"] for r in group),
                    sum(r["severe_first"] for r in group),
                    statistics.median(r.get("completion_tokens") or 0 for r in group),
                    statistics.median(r.get("total_s") or 0 for r in group)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rules", choices=["on", "off", "both"], default="both")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--cases", nargs="+", help="file names in review_cases/ (default: all)")
    parser.add_argument("--label", default="review")
    parser.add_argument("--show-answers", action="store_true")
    args = parser.parse_args()

    cases = args.cases or list(BUGS)
    settings = {"on": [True], "off": [False], "both": [True, False]}[args.rules]
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.label}.jsonl"
    print(f"Reviews go to {out}")
    rag.client = rag.OpenAI(base_url=rag.BASE_URL, api_key=rag.API_KEY)
    with_rules = rag.system_prompt
    rows = []
    try:
        for rules in settings:
            rag.system_prompt = with_rules if rules else (lambda model: "")
            for name in cases:
                prompt = rag.build_rag_prompt(QUESTION, [case_hit(name)])
                for run in range(1, args.runs + 1):
                    print(f"=== rules {'on' if rules else 'off'} | {name} run {run} ===", flush=True)
                    reply, stats = rag.stream_reply([{"role": "user", "content": prompt}], rag.CODE_MODEL,
                                                    echo=args.show_answers)
                    row = {"label": args.label, "rules": rules, "case": name, "run": run,
                           **score(reply, name), **stats, "answer": reply}
                    rows.append(row)
                    with out.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(row) + "\n")
    finally:
        rag.system_prompt = with_rules
        rag.client.close()
        rag.unload_model(rag.CODE_MODEL)

    print(f"\nSaved {len(rows)} reviews to {out}\n")
    print("| rules | reviews | planted bugs found | most severe bug first | median answer tokens | median total s |")
    print("|---|---|---|---|---|---|")
    for rules, n, found, total, first, tokens, seconds in summarize(rows):
        print(f"| {'on' if rules else 'off'} | {n} | {found}/{total} ({100 * found / total:.0f}%) | "
              f"{first}/{n} | {tokens:.0f} | {seconds:.1f} |")
    print("\nTimes include prefill; runs 2-3 of a file reuse the cached prompt.")
    print("\nMatched bugs (pattern matches: confirm each one), and bugs missed:")
    for row in rows:
        tag = f"rules {'on' if row['rules'] else 'off'} {row['case']} run {row['run']}"
        for bug, text in snippets(row["answer"], row["case"], row["found"]):
            line = bug_line(row["case"], next(a for b, a, _ in BUGS[row["case"]] if b == bug))
            print(f"- {tag}: found '{bug}' (line {line})\n    ...{text}...")
        for bug, *_ in BUGS[row["case"]]:
            if bug not in row["found"]:
                print(f"- {tag}: MISSED '{bug}'")


if __name__ == "__main__":
    main()
