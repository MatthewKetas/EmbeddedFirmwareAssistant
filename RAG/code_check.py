"""Check code retrieval on a sample repository whose answers are known.

Indexes code_cases/motor_fw into its own Qdrant collection (your library is not touched), then
for each question shows where the chunks holding the answer rank, and whether they are still
sent once the code context budget is applied, with and without line numbers. With --answer, the
code model also answers each question and is scored on the key facts and the lines it cites.
Stop rag.py first: both open the same on-disk Qdrant library.

    python RAG/code_check.py
    python RAG/code_check.py --answer --runs 2
"""
import argparse
import json
import re
import time
from pathlib import Path

import rag
from review_bench import CITED_LINES

REPO = rag.SCRIPT_DIR / "code_cases" / "motor_fw"
RESULTS = rag.SCRIPT_DIR / "bench_results"
COLLECTION = "code_check"
FLAGS = re.I | re.S
# Answers quote values as the code spells them ("2000u", "20,000 Hz", "10 milliseconds").
THOUSANDS = r"[,\s]?"
MS = r"\s*u?\W{0,4}\s*(ms|milliseconds?)\b"
# Between a macro name and its value: "`STALL_TIME_MS`: 500u", "STALL_TIME_MS (500u)", "STALL_TIME_MS is 500u".
MACRO = r"\W{0,6}(?:is|=|of|equals)?\W{0,6}"
# (id, question, anchors: (file, text on the line that holds the answer), facts: (name, pattern)).
QUESTIONS = [
    ("C1", "Which GPIO drives the motor PWM output, and at what frequency does it switch?",
     [("board_pins.h", "#define PIN_MOTOR_PWM"), ("pwm.c", "#define PWM_FREQUENCY_HZ")],
     [("GPIO 18", r"\b(GPIO|pin|IO)(\s*number)?\W{0,4}\s*_?18\b|PIN_MOTOR_PWM\W{1,20}18\b"), ("20 kHz", rf"20\s*kHz|\b20{THOUSANDS}000\s*u?\s*(Hz|hertz)?\b")]),
    ("C2", "What happens to incoming UART bytes when the receive buffer is full?",
     [("uart_rx.c", "void uart_rx_isr")],
     [("new byte dropped", r"drop|discard|ignor|lost|not stored"), ("overrun counted", r"rx_overruns|overrun")]),
    ("C3", "How many times does the firmware retry a failed sensor read, and how long does each I2C transfer wait?",
     [("env_sensor.c", "#define SENSOR_RETRIES"), ("env_sensor.c", "int env_sensor_read")],
     [("3 retries", r"\b(3|three)\b[^.]{0,40}(retr|more times|attempts? after)|retr[^.]{0,40}\b(3|three)\b|\b(4|four)\s*(total\s*)?attempts"),
      ("50 ms timeout", rf"\b50{MS}")]),
    ("C4", "When does the firmware decide that the motor has stalled?",
     [("motor.c", "static void motor_check_protection"), ("motor.c", "#define STALL_TIME_MS")],
     # Answers also give the value after the macro name: "`STALL_TIME_MS`: 500u".
     [("1500 mA", rf"\b1{THOUSANDS}500\s*u?\s*(mA|milliamps?)|1\.5\s*A\b|STALL_CURRENT_MA{MACRO}1{THOUSANDS}500u?\b"),
      ("500 ms", rf"\b500{MS}|STALL_TIME_MS{MACRO}500u?\b"),
      ("below 30 rpm", rf"\b30\s*rpm|STALL_MIN_SPEED_RPM{MACRO}30\b")]),
    ("C5", "What is the watchdog timeout, and what has to happen before the watchdog is fed?",
     [("watchdog.c", "#define WDT_TIMEOUT_MS"), ("watchdog.c", "void watchdog_service")],
     [("2000 ms", rf"\b2{THOUSANDS}000{MS}|\b2\s*(s|seconds?)\b"),
      ("every task checked in", r"(every|all|each)\s+(of the\s+)?(registered\s+)?tasks?[^.]{0,60}check|checked[_ ]in_mask")]),
    ("C6", "At what battery voltage does the board shut itself down, and how quickly?",
     [("power.c", "#define BATTERY_SHUTDOWN_MV"), ("power.c", "void power_check_battery")],
     [("3300 mV", rf"\b3{THOUSANDS}300\s*u?\W{{0,4}}\s*(mV|millivolts?)|3\.3\s*V\b"),
      ("5 readings in a row", r"\b(5|five)\b[^.]{0,40}(consecutive|in a row|readings|calls)|SHUTDOWN_READINGS"),
      ("checked once a second", rf"once (a|per) second|every (1 )?seconds?\b|\b1{THOUSANDS}000{MS}|\b(5|five)\s*seconds")]),
    ("C7", "What does the firmware do if the stored configuration fails its CRC check?",
     [("config.c", "void config_load")],
     [("uses defaults", r"default"), ("writes them back", r"writ\w* (them |the defaults )?back|config_save_now|saved? (at once|immediately)")]),
    ("C8", "How often does the main loop run the motor control step?",
     [("main.c", "#define CONTROL_PERIOD_MS")],
     [("every 10 ms", rf"\b10{MS}|100\s*Hz")]),
    # A file named in the question. motor.c has no planted bugs; similarity retrieval missed these two
    # functions and Qwen reported clamps missing from code it was never sent.
    ("C9", "Review motor.c for bugs.",
     [("motor.c", "void motor_control_step"), ("motor.c", "static void motor_fault")],
     [("does not claim the clamps are missing",
       r"^(?![\s\S]*(only handles positive|does not (limit|clamp)|not (limited|clamped) to|unclamped|negative windup))")]),
]


# Questions asked straight after an earlier one, as in a rag.py session: (earlier question, check).
# C10 is the session where Qwen, asked to review motor.c, also answered the stall question again;
# C11 only makes sense with the earlier question, so it checks that follow-ups still work.
PRIOR = {
    "C10": "Is the stall check done before or after the PI controller updates the PWM target?",
    "C11": "When does the firmware decide that the motor has stalled?",
}
QUESTIONS += [
    ("C10", "Review motor.c for bugs.",
     [("motor.c", "void motor_control_step"), ("motor.c", "static void motor_fault")],
     [("does not answer the earlier question",
       r"^(?![\s\S]*(stall check is (done|performed|called) (before|after)|Final Answer|^\s*Answer:.{0,40}before))")]),
    ("C11", "And what happens to the motor when that fault trips?",
     [("motor.c", "static void motor_fault")],
     [("PWM target set to zero", r"pwm_set_target\(0\)|target\W{0,20}(to )?(0|zero)\b|duty\W{0,20}(to )?(0|zero)\b"),
      ("driver disabled", r"pwm_enable\(false\)|disabl"),
      ("state set to MOTOR_FAULT", r"MOTOR_FAULT"),
      ("event logged", r"log_event|\blog(s|ged)?\b")]),
]


def anchor_line(file: str, text: str) -> int:
    lines = (REPO / file).read_text(encoding="utf-8").splitlines()
    return next(i for i, line in enumerate(lines, 1) if text in line)


def holds(hit, file: str, line: int) -> bool:
    p = hit.payload
    return p.get("file") == file and p["start_line"] <= line <= p["end_line"]


def anchor_ranks(hits, anchors) -> dict[str, int | None]:
    """1-based rank of the chunk holding each anchor line, or None when it was not retrieved."""
    ranks = {}
    for file, text in anchors:
        line = anchor_line(file, text)
        ranks[f"{file}:{line}"] = next((i for i, h in enumerate(hits, 1) if holds(h, file, line)), None)
    return ranks


def sent_with(question: str, hits, numbered: bool, history: list | None = None) -> list:
    """The hits that fit the code context budget, with or without line numbers in the prompt."""
    original = rag.numbered
    if not numbered:
        rag.numbered = lambda payload: payload["text"]
    try:
        return rag.fit_code_context(question, hits, history or [])
    finally:
        rag.numbered = original


def score_answer(answer: str, anchors, facts, chunk_ranges) -> dict:
    """Key facts stated, and whether any cited line or short range falls in a chunk that holds an anchor."""
    stated = [name for name, pattern in facts if re.search(pattern, answer, FLAGS)]
    cited = [(int(m.group(1) or m.group(3)), int(m.group(2) or m.group(4) or m.group(1) or m.group(3)))
             for m in CITED_LINES.finditer(answer)]
    located = any(last - first <= 30 and first <= end and last >= start
                  for first, last in cited for start, end in chunk_ranges)
    return {"facts": stated, "of": len(facts), "located": located}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--depth", type=int, default=30, help="how many chunks to rank (default 30)")
    parser.add_argument("--answer", action="store_true", help="also have the code model answer each question")
    parser.add_argument("--runs", type=int, default=1, help="answers per question with --answer")
    parser.add_argument("--label", default="code-check")
    args = parser.parse_args()

    rag.client = rag.OpenAI(base_url=rag.BASE_URL, api_key=rag.API_KEY)
    rag.qdrant = rag.QdrantClient(path=rag.QDRANT_PATH)
    saved = {name: getattr(rag, name) for name in ("COLLECTION", "TOP_N_CHUNKS", "UNLOAD_AFTER_INGEST")}
    top_n = rag.TOP_N_CHUNKS
    rag.COLLECTION, rag.UNLOAD_AFTER_INGEST = COLLECTION, False
    rows = []
    try:
        if rag.qdrant.collection_exists(COLLECTION):
            rag.qdrant.delete_collection(COLLECTION)
        source = rag.ingest_code(str(REPO))
        print(f"Context budget: {rag.RAG_CONTEXT_TOKENS} tokens of retrieved code; top {top_n} chunks retrieved\n")
        for qid, question, anchors, facts in QUESTIONS:
            print(f"=== {qid}: {question}")
            history = []
            if qid in PRIOR:
                print(f"  asked first: {PRIOR[qid]}")
                reply = "(not asked without --answer)"
                if args.answer:
                    # As rag.py keeps it: the plain earlier question, and the answer it got.
                    earlier = rag.fit_code_context(PRIOR[qid], rag.retrieve(PRIOR[qid], [source]), [])
                    reply, _ = rag.stream_reply([{"role": "user", "content": rag.build_rag_prompt(PRIOR[qid], earlier)}],
                                                rag.CODE_MODEL, echo=False)
                history = [{"role": "user", "content": PRIOR[qid]}, {"role": "assistant", "content": reply}]
            query = rag.retrieval_query(question, history)
            rag.TOP_N_CHUNKS = args.depth
            start = time.monotonic()
            ranked = rag.retrieve(query, [source])
            seconds = time.monotonic() - start
            rag.TOP_N_CHUNKS = top_n
            # What rag.py sends: a named file comes in addition to the top N, so retrieve again
            # at the normal depth rather than cutting the deep ranking.
            hits = rag.retrieve(query, [source])
            print(f"  retrieval {seconds:.1f}s{'' if query == question else ', searched with the earlier question too'}")
            sent = {numbered: sent_with(question, hits, numbered, history) for numbered in (False, True)}
            print(f"  chunks sent: {len(sent[False])} without line numbers, {len(sent[True])} with")
            for name, rank in anchor_ranks(ranked, anchors).items():
                file, line = name.rsplit(":", 1)
                flags = ["sent" if any(holds(h, file, int(line)) for h in sent[n]) else "not sent" for n in (False, True)]
                note = "" if flags[0] == flags[1] else "   <- line numbers push it out" if flags[0] == "sent" else ""
                print(f"  {name:22} rank {rank or f'>{args.depth}':>4}   {flags[0]:>8} / {flags[1]:<8}{note}")
            if args.answer:
                ranges = [(h.payload["start_line"], h.payload["end_line"]) for h in sent[True]
                          if any(holds(h, f, anchor_line(f, t)) for f, t in anchors)]
                prompt = rag.build_rag_prompt(question, sent[True])
                for run in range(1, args.runs + 1):
                    reply, stats = rag.stream_reply(history + [{"role": "user", "content": prompt}], rag.CODE_MODEL,
                                                    echo=False)
                    result = score_answer(reply, anchors, facts, ranges)
                    rows.append({"label": args.label, "question": qid, "run": run, **result, **stats, "answer": reply})
                    missing = [n for n, _ in facts if n not in result["facts"]]
                    print(f"  answer {run}{' (stopped at the length limit)' if stats.get('cut') else ''}: "
                          f"facts {len(result['facts'])}/{result['of']}"
                          f"{' (missing: ' + ', '.join(missing) + ')' if missing else ''}, "
                          f"{'cites an answer line' if result['located'] else 'no answer line cited'}, "
                          f"{stats['completion_tokens']} tokens, {stats['total_s']:.1f}s")
            print()
    finally:
        if rag.qdrant.collection_exists(COLLECTION):
            rag.qdrant.delete_collection(COLLECTION)
        for name, value in saved.items():
            setattr(rag, name, value)
        rag.teardown()

    if rows:
        RESULTS.mkdir(exist_ok=True)
        out = RESULTS / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.label}.jsonl"
        out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        facts = sum(len(r["facts"]) for r in rows)
        total = sum(r["of"] for r in rows)
        print(f"Answers: {facts}/{total} key facts, {sum(r['located'] for r in rows)}/{len(rows)} cite an answer line. "
              f"Saved to {out}")


if __name__ == "__main__":
    main()
