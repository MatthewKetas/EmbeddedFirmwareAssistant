"""Show where the passages that answer each Milestone 1 prompt rank in retrieval,
under two retrieval settings (default: the current one, then with the question split into sentences).

Needs only the embedding model and the Qdrant library, no chat model.
Stop rag.py first: both open the same on-disk Qdrant library.

    python RAG/retrieval_check.py --board esp-32
    python RAG/retrieval_check.py --compare vectors keywords --depth 100
"""
import argparse
import re
import time

import rag
from bench import load_prompts

# Settings to compare: vectors alone, merged with keyword ranking, and also per question sentence.
SETTINGS = {
    "vectors": {"HYBRID_SEARCH": False, "SPLIT_QUESTION": False},
    "keywords": {"HYBRID_SEARCH": True, "SPLIT_QUESTION": False},
    "split": {"HYBRID_SEARCH": True, "SPLIT_QUESTION": True},
}
# A passage counts as found when a retrieved chunk's text matches its pattern.
# Patterns follow the datasheet's wording (ESP32.pdf page in the name).
TARGETS = {
    "P1": [("RSA 4096-bit limit, p.32", r"4096\s*bits")],
    "P2": [("I2C Fast mode 400 Kbit/s, p.37", r"Fast\s*mode\s*\(\s*400"),
           ("SPI0-SPI3 roles, p.36", r"SPI0\s*is\s*used\s*as\s*a\s*buffer"),
           ("UART pins via GPIO Matrix, p.37", r"pins\s*for\s*UART\s*can\s*be\s*chosen"),
           ("UART baud rates up to 5 MBaud, p.37", r"up\s*to\s*5\s*MBaud"),
           ("strapping and input-only counts, p.4", r"strapping\s*GPIOs")],
    "P3": [("power-up timing tSTBL 50 us, p.19", r"ST\s*BL"),
           ("strapping tSU/tH, Table 3-2", r"Setup\s*time\s*is\s*the\s*time\s*reserved"),
           ("boot mode table, Table 3-3", r"Joint\s*Download\s*Boot|JointDownloadBoot"),
           ("uart_download_dis, Section 3", r"uart_download_dis"),
           ("U0TXD is GPIO1 in the pin overview, p.15", r"U0TXD,\s*Function\s*=\s*GPIO1")],
    "P4": [("3.3 V / 500 mA supply, p.19", r"500\s*mA"),
           ("VDD_SDIO LDO 40 mA, p.51", r"LDO\s*can\s*offer\s*is\s*40\s*mA"),
           ("MTDI selects VDD_SDIO, p.24", r"MTDI\s*=\s*1"),
           ("2 kOhm resistor for 1.8 V, p.19", r"2\s*k\s*(Ω|ohm)"),
           ("6 Ohm resistor from VDD3P3_RTC, p.18", r"6\s*(Ω|ohm)\s*resistor")],
    "P5": [("four general-purpose timers, p.31", r"four\s*general-purpose\s*timers"),
           ("three watchdog timers, p.31", r"three\s*watchdog\s*timers"),
           ("watchdog four stages, p.31", r"four\s*stages")],
}


def rank_targets(hits, targets, top_n):
    """Rank (1-based) of the first chunk matching each target, and duplicate chunks in the top N."""
    ranks = {}
    for name, pattern in targets:
        ranks[name] = next((i for i, h in enumerate(hits, 1)
                            if re.search(pattern, h.payload["text"], re.I)), None)
    seen, duplicates = set(), 0
    for h in hits[:top_n]:
        text = " ".join(h.payload["text"].split())
        duplicates += text in seen
        seen.add(text)
    return ranks, duplicates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--depth", type=int, default=50, help="how many chunks to rank (default 50)")
    parser.add_argument("--board", help="board id, as in rag.py's /board")
    parser.add_argument("--compare", nargs=2, choices=list(SETTINGS), default=["keywords", "split"],
                        metavar=("BEFORE", "AFTER"), help=f"two of: {', '.join(SETTINGS)}")
    args = parser.parse_args()

    rag.client = rag.OpenAI(base_url=rag.BASE_URL, api_key=rag.API_KEY)
    rag.qdrant = rag.QdrantClient(path=rag.QDRANT_PATH)
    top_n, rag.TOP_N_CHUNKS = rag.TOP_N_CHUNKS, args.depth
    defaults = {name: getattr(rag, name) for name in SETTINGS["vectors"]}
    before, after = args.compare
    try:
        print(f"Library sources: {', '.join(rag.list_sources()) or '(empty)'}\n")
        for pid, question in load_prompts().items():
            results = {}
            for setting in (before, after):
                for name, value in SETTINGS[setting].items():
                    setattr(rag, name, value)
                start = time.monotonic()
                hits = rag.retrieve(question, None, args.board)
                results[setting] = hits, time.monotonic() - start, *rank_targets(hits, TARGETS[pid], top_n)
            (_, t_before, ranks_before, dup_before), (after_hits, t_after, ranks_after, dup_after) = \
                results[before], results[after]
            print(f"=== {pid}: {before} {t_before:.1f}s, {after} {t_after:.1f}s; "
                  f"duplicates in the top {top_n}: {dup_before} / {dup_after}")
            for name in ranks_before:
                pair = (ranks_before[name], ranks_after[name])
                cells = [f"{r}" if r else f">{args.depth}" for r in pair]
                sent = tuple(r is not None and r <= top_n for r in pair)
                note = {(False, True): "   <- now sent", (True, False): "   <- no longer sent",
                        (False, False): "   <- not sent either way"}.get(sent, "")
                print(f"  {name:42} rank {cells[0]:>4} -> {cells[1]:>4}{note}")
            # First line of each chunk: Docling puts the heading path there.
            print(f"  top {top_n} with {after}:")
            for rank, h in enumerate(after_hits[:top_n], 1):
                first = " ".join(h.payload["text"].split("\n", 1)[0].split())[:70]
                print(f"    {rank:2}. {rag.source_label(h.payload):22} {first}")
            print()
    finally:
        rag.TOP_N_CHUNKS = top_n
        for name, value in defaults.items():
            setattr(rag, name, value)
        rag.teardown()


if __name__ == "__main__":
    main()
