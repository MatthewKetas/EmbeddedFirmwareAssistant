"""Check saved bench answers against key facts located in ESP32.pdf.

A checklist, not a 1-5 score: it finds which key facts an answer states and which known
wrong claims it makes. Pattern matching can misfire, so every flagged error is printed
with its surrounding text for a person to confirm.

    python RAG/fact_check.py RAG/bench_results/20261126-105910-strict.jsonl
    python RAG/fact_check.py RAG/bench_results/*.jsonl --csv fact-check.csv
"""
import argparse
import csv
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

FLAGS = re.I | re.S
MICRO = r"(µs|us|μs|\\?mu)"
# Key facts per prompt: (name with ESP32.pdf page, pattern the answer must contain).
FACTS = {
    "P1": [("RSA+SHA accelerators p32", r"(?=.*\bRSA\b)(?=.*\bSHA)(?=.*accelerat)"),
           ("4096-bit limit p32", r"4,?096"),
           ("trust not established", r"(does not|doesn.t|cannot|not by itself|alone does not|\bno\b\W).{0,120}(trust|establish)")],
    "P2": [("I2C fast 400 Kbit/s supported p37", r"(fast[- ]mode|400 ?k?bit/s|400 ?kHz).{0,160}(support|provid|fast mode|documented)|support.{0,80}(fast[- ]mode|400 ?k)"),
           ("SPI0 reserved for memory p36", r"SPI0.{0,120}(memory|flash|psram)"),
           ("three UARTs p37", r"(three|3) UART"),
           ("5 strapping GPIOs p4", r"(five|5) strapping"),
           ("6 input-only GPIOs p4", r"(six|6) input[- ]only|GPIO ?(pins )?34\s*[-–~]\s*39")],
    "P3": [("download GPIO0=0 GPIO2=0 p23", r"GPIO2\W{0,6}(=|is|must be|:|\|)?\W{0,6}(0\b|low)"),
           ("flash boot GPIO0=1 p23", r"GPIO0\W{0,6}(=|is|must be|:|\|)?\W{0,6}(1\b|high)"),
           ("strapping hold 1 ms p23", r"\b1\W{0,12}ms\b"),
           ("power-up 50 us p19", r"50\W{0,3}(\\text\{\s*\}\W{0,3})?" + MICRO),
           ("uart_download_dis p24", r"uart\\?_download\\?_dis")],
    "P4": [("3.3 V / >=500 mA p19", r"500 ?mA|0\.5 ?A"),
           ("2.3-3.6 V range p19", r"2\.3 ?V?.{0,15}3\.6"),
           ("three domains p17", r"(?=.*VDD3P3\\?_RTC)(?=.*VDD3P3\\?_CPU)(?=.*VDD\\?_SDIO)"),
           ("MTDI selects VDD_SDIO p24", r"MTDI"),
           ("LDO 40 mA p51", r"40 ?mA"),
           ("3.0 V min with in-package memory p51", r"3\.0 ?V"),
           ("6 ohm resistor p18", r"6 ?(Ω|ohm|\$\\Omega|\\Omega)"),
           ("2 kohm resistor for 1.8 V p19", r"2 ?k ?(Ω|ohm|\$?\\?Omega|\\u2126|Ω)")],
    "P5": [("three watchdogs p31", r"(three|3) watchdog|two main watchdog|two MWDT|2 MWDT|MWDT.{0,80}RWDT"),
           ("four stages p31", r"(four|4)[- ](configurable )?stage"),
           ("RWDT full-chip reset p31", r"RWDT.{0,200}(entire chip|whole chip|system reset|including the RTC)"),
           ("4 general-purpose 64-bit timers p31", r"(four|4) (64-bit )?(general[- ]purpose|generic) timer|64-bit (general|generic|timer)"),
           ("no 1 ms guarantee", r"(cannot|can.t|does not|doesn.t|not).{0,40}guarantee|\*\*no\.?\*\*")],
}
# Claims the datasheet contradicts: (name, pattern[, pattern that clears it when found nearby]).
ERRORS = {
    "P1": [("says no RSA accelerator", r"(does not|doesn.t|no) (include |have )?(a )?(dedicated |hardware )?RSA (accelerat|hardware)"),
           ("says RSA limit is 3072", r"(up to|maximum of|max(imum)?|≤|<=) ?3,?072|3,?072[- ]bit (limit|maximum)", r"4,?096")],
    "P2": [("says 400 Kbit/s not documented", r"(not|n.t|no\b).{0,90}(400 ?k|fast[- ]mode|i2c (bus )?frequency|frequency limit)",
            r"pull-up|integrity|SPI clock|supported via|natively support|pF|drive strength"),
           ("says SPI0 usable for display", r"use \*{0,2}SPI0", r"do not|don.t|avoid"),
           ("I2C full-duplex", r"I2C.{0,60}full[- ]duplex")],
    "P3": [("download needs GPIO2 high", r"download.{0,120}GPIO2\W{0,6}(=|must be|:)?\W{0,6}(1\b|high)\b"),
           ("normal boot needs GPIO2 high", r"(normal|flash|spi) boot.{0,80}GPIO2\W{0,6}(=|must be|:)?\W{0,6}(1\b|high)"),
           ("invented eFuse name", r"SEC_BOOT_JTAG|(?<!uart_)\bDOWNLOAD_DIS\b|Download Mode Disable eFuse"),
           ("U0TXD given as GPIO3", r"U0TXD\W{1,6}(is\s+)?(also\s+)?(listed\s+as\s+|=\s*)?GPIO\s*3\b"),
           ("SPI boot labelled SDIO download", r"SDIO Download Boot\W{1,6}(requires\s+)?\W{0,6}GPIO0\W{0,6}=\W{0,6}1\b")],
    "P4": [("wrong LDO current", r"(200|300|1\.8) ?mA"),
           ("wrong supply range", r"2\.(7|8|95) ?V|2\.0 ?V to 3\.6"),
           ("MTDI=0 gives 1.8 V", r"MTDI\W{0,4}=\W{0,4}0\W.{0,60}1\.8 ?V"),
           ("UART TX on input-only pins", r"input[- ]only.{0,120}(UART TX|TX/RX|U.?_TXD)"),
           ("VDDA called a digital domain", r"digital power (supplies|domains)\W{0,4}(are|:)\W{0,4}VDDA")],
    "P5": [("says datasheet has no general timers", r"(not|n.t|no|only).{0,120}(general[- ]purpose|periodic|dedicated) (hardware )?timer",
            r"GPTIMER|General Purpose Timers|configuration|register"),
           ("invented WDT range", r"32,?768 ?ms|1 ms to 32")],
}


def check(answer: str, prompt: str) -> tuple[list[str], list[str]]:
    """Names of the key facts the answer states, and of the known errors it makes."""
    facts = [name for name, pattern in FACTS[prompt] if re.search(pattern, answer, FLAGS)]
    errors = []
    for name, pattern, *clears in ERRORS[prompt]:
        for match in re.finditer(pattern, answer, FLAGS):
            nearby = answer[max(0, match.start() - 100):match.end() + 100]
            if not (clears and re.search(clears[0], nearby, FLAGS)):
                errors.append(name)
                break
    return facts, errors


def error_snippets(answer: str, prompt: str, names: list[str]) -> list[tuple[str, str]]:
    snippets = []
    for name, pattern, *_ in ERRORS[prompt]:
        if name in names and (match := re.search(pattern, answer, FLAGS)):
            text = answer[max(0, match.start() - 90):match.end() + 60]
            snippets.append((name, " ".join(text.split())))
    return snippets


def summarize(rows: list[dict]) -> list[tuple]:
    """(label, model, rag, answers, facts stated, facts total, errors) per group, in first-seen order."""
    groups = defaultdict(list)
    for row in rows:
        groups[(row["label"], row["model"], row["rag"])].append(row)
    return [(*key, len(group), sum(r["facts"] for r in group), sum(r["of"] for r in group),
             sum(len(r["errors"]) for r in group)) for key, group in groups.items()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", help="bench .jsonl files (wildcards allowed)")
    parser.add_argument("--csv", help="also write one row per answer to this CSV file")
    args = parser.parse_args()

    paths = sorted({p for pattern in args.files for p in (glob.glob(pattern) or [pattern])})
    rows, flagged = [], []
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            facts, errors = check(record["answer"], record["prompt"])
            names = [name for name, _ in FACTS[record["prompt"]]]
            rows.append({"file": Path(path).name, "label": record.get("label", ""), "model": record["model"],
                         "rag": record["rag"], "prompt": record["prompt"], "run": record.get("run", 1),
                         "facts": len(facts), "of": len(names),
                         "missing": [n for n in names if n not in facts], "errors": errors})
            flagged += [(rows[-1], name, text) for name, text in error_snippets(record["answer"], record["prompt"], errors)]

    print("| label | model | RAG | answers | key facts stated | errors flagged |")
    print("|---|---|---|---|---|---|")
    for label, model, rag, answers, stated, total, errors in summarize(rows):
        print(f"| {label} | {model} | {'yes' if rag else 'no'} | {answers} | {stated}/{total} "
              f"({100 * stated / total:.0f}%) | {errors} |")
    print("\nFlagged errors (pattern matches: confirm each one before counting it):")
    for row, name, text in flagged:
        print(f"- {row['label']} {row['model']} {'RAG' if row['rag'] else 'no RAG'} {row['prompt']} "
              f"run {row['run']}: {name}\n    ...{text}...")
    if not flagged:
        print("  none")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["file", "label", "model", "rag", "prompt", "run", "key facts stated",
                             "key facts total", "missing facts", "errors flagged", "your 1-5 score"])
            for r in rows:
                writer.writerow([r["file"], r["label"], r["model"], r["rag"], r["prompt"], r["run"], r["facts"],
                                 r["of"], "; ".join(r["missing"]), "; ".join(r["errors"]), ""])
        print(f"\nWrote {len(rows)} rows to {args.csv}")


if __name__ == "__main__":
    main()
