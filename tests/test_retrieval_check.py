import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "RAG"))
import retrieval_check  # noqa: E402  (imports rag the way the script does)


def hit(text):
    return SimpleNamespace(payload={"text": text, "source": "ESP32.pdf", "page": 1})


class RankTargetsTests(unittest.TestCase):
    def test_ranks_first_match_and_counts_duplicates_in_the_top_n(self):
        hits = [hit("watchdog timers"), hit("watchdog  timers"), hit("Fast mode (400 Kbit/s)"),
                hit("other")]
        targets = [("fast mode", r"Fast\s*mode\s*\(\s*400"), ("missing", r"tSTBL")]
        ranks, duplicates = retrieval_check.rank_targets(hits, targets, top_n=3)
        self.assertEqual(ranks, {"fast mode": 3, "missing": None})
        self.assertEqual(duplicates, 1)   # the second chunk differs only in whitespace

    def test_every_setting_names_a_real_rag_option(self):
        for setting in retrieval_check.SETTINGS.values():
            for name in setting:
                self.assertTrue(hasattr(retrieval_check.rag, name), name)

    def test_every_prompt_has_targets(self):
        self.assertEqual(set(retrieval_check.TARGETS), set(retrieval_check.load_prompts()))


if __name__ == "__main__":
    unittest.main()
