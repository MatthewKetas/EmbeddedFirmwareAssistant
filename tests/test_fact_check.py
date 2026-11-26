import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "RAG"))
import fact_check  # noqa: E402


class FactCheckTests(unittest.TestCase):
    def test_power_up_time_is_found_in_plain_and_latex_forms(self):
        for answer in ("tSTBL is 50 µs.", "**50 µs**", "is 50 $\\mu$s [ESP32.pdf, p.19]",
                       "($\\text{tST\\_BL, Min}$) is $50 \\text{ } \\mu\\text{s}$"):
            with self.subTest(answer=answer):
                facts, _ = fact_check.check(answer, "P3")
                self.assertIn("power-up 50 us p19", facts)

    def test_an_error_is_ignored_when_its_context_says_otherwise(self):
        _, errors = fact_check.check("RSA-3072 needs numbers up to 3072 bits; the limit is 4096 bits.", "P1")
        self.assertEqual(errors, [])
        _, errors = fact_check.check("The RSA accelerator supports keys up to 3072 bits.", "P1")
        self.assertEqual(errors, ["says RSA limit is 3072"])

    def test_errors_seen_in_bench_answers(self):
        self.assertIn("U0TXD given as GPIO3", fact_check.check("U0TXD is also listed as GPIO3.", "P3")[1])
        self.assertIn("SPI boot labelled SDIO download",
                      fact_check.check("SDIO Download Boot: Requires GPIO0 = 1 and GPIO2 = Any value", "P3")[1])
        self.assertIn("VDDA called a digital domain",
                      fact_check.check("The three digital power supplies are VDDA, VDD3P3_RTC, and VDD3P3.", "P4")[1])
        self.assertEqual(fact_check.check("U0TXD is GPIO1 and U0RXD is GPIO3.", "P3")[1], [])

    def test_summary_groups_by_label_model_and_retrieval(self):
        rows = [
            {"label": "a", "model": "m", "rag": True, "prompt": "P1", "facts": 3, "of": 3, "errors": []},
            {"label": "a", "model": "m", "rag": True, "prompt": "P2", "facts": 1, "of": 5, "errors": ["x"]},
            {"label": "a", "model": "m", "rag": False, "prompt": "P1", "facts": 0, "of": 3, "errors": []},
        ]
        self.assertEqual(fact_check.summarize(rows), [("a", "m", True, 2, 4, 8, 1), ("a", "m", False, 1, 0, 3, 0)])


if __name__ == "__main__":
    unittest.main()
