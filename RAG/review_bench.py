"""Time the code model's reviews of small C files with planted bugs, under different system prompts.

Each file in review_cases/ has known bugs, the most severe listed first. A bug counts as found when
the review matches its pattern; the snippets are printed for a person to confirm. "Severe first"
means the most severe bug is mentioned before the file's other planted bug. HELD_OUT files have
bugs the review checklist does not name, to show whether it helps beyond the bugs it lists.
Stop rag.py first if it is running: both talk to the same Lemonade server.

    python RAG/review_bench.py --prompts none checklist --runs 3 --label checklist
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
# The rules Qwen had before this bench: Gemma's answer rules plus a code-review rule.
REVIEW_RULE = ("\nFor code reviews: list findings most severe first, each with file, line and a one-line fix; "
               "put real bugs before style nits.")
SYSTEM_PROMPTS = {"none": "", "rules": rag.ANSWER_RULES + REVIEW_RULE, "checklist": rag.REVIEW_CHECKLIST}
HELD_OUT = {"cmd_parser.c", "status_poll.c"}
FLAGS = re.I | re.S
# file -> bugs, most severe first: (name, text on the bug's line, pattern a review that found it matches[,
# pattern that clears the match when found nearby, e.g. a review calling the planted bug correct]).
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
         # Comparing len with buf, not with what the sensor returns.
         r"\blen\b.{0,80}(greater|larger|more|exceeds?)( than)?.{0,40}(\b4\b|buf|sizeof)|\blen\W{0,3}\s*<=?\s*(4|sizeof)"
         r"|\blen\s*>\s*4|(stack|buffer) overflow.{0,120}\blen\b|\blen\b.{0,120}(stack|buffer) overflow"),
        ("i2c_write result is ignored", "i2c_write(SENSOR_ADDR, &reg, 1);",
         r"(return value|result|ignor|unchecked|not checked|error).{0,80}i2c_write|i2c_write.{0,80}(return value|result|ignor|unchecked|not checked)",
         r"(provide|no|lacks?) information"),
    ],
    "tick_timer.c": [
        ("tick_flag and tick_ms are not volatile: wait_for_tick can spin forever", "static bool tick_flag;",
         r"volatile"),
        ("elapsed_since returns 0 when the counter wraps", "if (now < start) {",
         r"(wrap|overflow|roll ?over).{0,120}(now|start|tick|millis|elapsed)|(now|start|tick_ms|elapsed_since).{0,120}(wrap|roll ?over)",
         r"(?<!not )(?<!n't )\bhandles?\b[^.]{0,40}(wrap|overflow)"),
    ],
    # Held out: the checklist names none of these, except that a uint8_t counter is a kind of truncation.
    "cmd_parser.c": [
        ("run_command returns a pointer to its local reply buffer", "return reply;",
         r"dangling|(return|pointer)\w*.{0,60}(local|stack|out of scope)|(local|stack).{0,60}(returned|pointer|out of scope)"
         r"|static char reply|goes out of scope|after (the function|it) returns"),
        ("CMD_LED_ON falls through into CMD_LED_OFF: no break", 'snprintf(reply, sizeof reply, "led on");',
         r"fall[- ]?through|falls through|missing\W{0,3}break|no\W{0,3}break|without (a )?\W{0,2}break"),
    ],
    "status_poll.c": [
        ("== binds tighter than &: tests bit 0, not STATUS_READY", "return (*PERIPH_STATUS & STATUS_READY == STATUS_READY);",
         r"precedence|binds (more )?tight|evaluated (first|before)|\(\s*\*?PERIPH_STATUS\s*&\s*STATUS_READY\s*\)\s*==|STATUS_READY == STATUS_READY\W{0,6}(evaluates|is|becomes|yields) (to )?\W{0,2}(1|true)\b"),
        ("uint8_t i wraps at 256, so a count above 255 loops forever", "for (uint8_t i = 0; i < count; i++) {",
         r"uint8_t\W{0,3}\s*(i\b|loop|counter|index).{0,160}(255|256|wrap|overflow|infinite|forever|never)"
         r"|(255|256).{0,120}uint8_t"),
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


# Where one finding ends and the next starts: a heading, "1.", "**2.", "Bug 3", "Finding 4".
FINDING_START = re.compile(r"\n\s*(?:#+\s|\*\*\s*\d+\.|\d+\.\s|\*\*Bug\s*\d|Bug\s*\d|Finding\s*\d)", re.I)
# "line 19", "Lines 13-16", "**Line:** 26", "uart_ring.c:19" or "uart_ring.c:22-26".
CITED_LINES = re.compile(r"\blines?\W{0,6}(\d+)(?:\s*(?:-|–|to)\s*(\d+))?|\.[ch]:(\d+)(?:\s*-\s*(\d+))?", re.I)


def cited_lines(answer: str, position: int) -> list[tuple[int, int]]:
    """Line ranges cited in the finding that contains this position."""
    starts = [0] + [m.start() for m in FINDING_START.finditer(answer)] + [len(answer)]
    begin = max(s for s in starts if s <= position)
    end = min(s for s in starts if s > position) if position < len(answer) else len(answer)
    ranges = []
    for m in CITED_LINES.finditer(answer[begin:end]):
        first = int(m.group(1) or m.group(3))
        last = int(m.group(2) or m.group(4) or first)
        ranges.append((first, last))
    return ranges


def located(ranges: list[tuple[int, int]], line: int) -> bool:
    """A range of at most 8 lines covering the bug line, give or take one; "1-35" (the file) does not count."""
    return any(last - first <= 8 and first - 1 <= line <= last + 1 for first, last in ranges)


def score(answer: str, name: str) -> dict:
    """Which planted bugs the review names, whether the most severe one comes first, and which
    found bugs it puts on the right line."""
    positions = {}
    for bug, _, pattern, *clears in BUGS[name]:
        for match in re.finditer(pattern, answer, FLAGS):
            nearby = answer[max(0, match.start() - 100):match.end() + 100]
            if not (clears and re.search(clears[0], nearby, FLAGS)):
                positions[bug] = match.start()
                break
    severe = BUGS[name][0][0]
    found = [bug for bug, *_ in BUGS[name] if bug in positions]
    lines = {bug: bug_line(name, anchor) for bug, anchor, *_ in BUGS[name]}
    return {"found": found, "of": len(BUGS[name]),
            "severe_first": severe in positions and positions[severe] == min(positions.values()),
            "located": [bug for bug in found if located(cited_lines(answer, positions[bug]), lines[bug])]}


def snippets(answer: str, name: str, found: list[str]) -> list[tuple[str, str]]:
    out = []
    for bug, _, pattern, *_ in BUGS[name]:
        if bug in found and (match := re.search(pattern, answer, FLAGS)):
            out.append((bug, " ".join(answer[max(0, match.start() - 80):match.end() + 60].split())))
    return out


def summarize(rows: list[dict]) -> list[tuple]:
    """(prompt, files, reviews, bugs found, bugs total, severe first, found bugs on the right line,
    median tokens, median total s) per system prompt, for the checked files and the held-out files apart."""
    out = []
    groups = dict.fromkeys((r["prompt"], r["case"] in HELD_OUT) for r in rows)
    for prompt, held in groups:   # first-seen order: checked files come before held-out ones
        group = [r for r in rows if r["prompt"] == prompt and (r["case"] in HELD_OUT) == held]
        out.append((prompt, "held out" if held else "checked", len(group), sum(len(r["found"]) for r in group),
                    sum(r["of"] for r in group), sum(r["severe_first"] for r in group),
                    sum(len(r.get("located", [])) for r in group),
                    statistics.median(r.get("completion_tokens") or 0 for r in group),
                    statistics.median(r.get("total_s") or 0 for r in group)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prompts", nargs="+", choices=list(SYSTEM_PROMPTS), default=["none", "checklist"],
                        help="system prompts to compare: none, the old rules, or the review checklist")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--cases", nargs="+", help="file names in review_cases/ (default: all)")
    parser.add_argument("--label", default="review")
    parser.add_argument("--show-answers", action="store_true")
    args = parser.parse_args()

    cases = args.cases or list(BUGS)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.label}.jsonl"
    print(f"Reviews go to {out}")
    rag.client = rag.OpenAI(base_url=rag.BASE_URL, api_key=rag.API_KEY)
    default_rules = rag.system_prompt
    rows = []
    try:
        for prompt_name in args.prompts:
            rag.system_prompt = lambda model, text=SYSTEM_PROMPTS[prompt_name]: text
            for name in cases:
                prompt = rag.build_rag_prompt(QUESTION, [case_hit(name)])
                for run in range(1, args.runs + 1):
                    print(f"=== {prompt_name} | {name} run {run} ===", flush=True)
                    reply, stats = rag.stream_reply([{"role": "user", "content": prompt}], rag.CODE_MODEL,
                                                    echo=args.show_answers)
                    row = {"label": args.label, "prompt": prompt_name, "case": name, "run": run,
                           **score(reply, name), **stats, "answer": reply}
                    rows.append(row)
                    with out.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(row) + "\n")
    finally:
        rag.system_prompt = default_rules
        rag.client.close()
        rag.unload_model(rag.CODE_MODEL)

    print(f"\nSaved {len(rows)} reviews to {out}\n")
    print("| system prompt | files | reviews | planted bugs found | found bugs on the right line | most severe bug first | median answer tokens | median total s |")
    print("|---|---|---|---|---|---|---|---|")
    for prompt_name, files, n, found, total, first, on_line, tokens, seconds in summarize(rows):
        print(f"| {prompt_name} | {files} | {n} | {found}/{total} ({100 * found / total:.0f}%) | "
              f"{on_line}/{found} | {first}/{n} | {tokens:.0f} | {seconds:.1f} |")
    print("\nTimes include prefill; runs 2-3 of a file reuse the cached prompt.")
    print("\nMatched bugs (pattern matches: confirm each one), and bugs missed:")
    for row in rows:
        tag = f"{row['prompt']} {row['case']} run {row['run']}"
        for bug, text in snippets(row["answer"], row["case"], row["found"]):
            line = bug_line(row["case"], next(a for b, a, *_ in BUGS[row["case"]] if b == bug))
            where = "right line" if bug in row.get("located", []) else "line not given or wrong"
            print(f"- {tag}: found '{bug}' (line {line}, {where})\n    ...{text}...")
        for bug, *_ in BUGS[row["case"]]:
            if bug not in row["found"]:
                print(f"- {tag}: MISSED '{bug}'")


if __name__ == "__main__":
    main()
