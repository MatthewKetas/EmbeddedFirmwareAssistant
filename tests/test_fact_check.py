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

    def test_false_positives_from_the_runs3_check_are_not_flagged(self):
        cases = [
            ("P2", "sufficient details to finalize the wiring based on the stated requirements (e.g., 400 Kbit/s I2C, SPI master)"),
            ("P5", "Distinct Roles: * **Timers:** The general-purpose timers are used for timing events"),
            ("P5", "* **Timers:** The General-Purpose Timers and PWM timers are described as tools for precise timing"),
            ("P4", "sourced from `VDD3P3_RTC` (either via default MTDI=0 or `EFUSE_SDIO_TIEH=1`).\n* **Internal 1.8 V LDO Current Limit:**"),
            ("P2", "is not explicitly enumerated in the provided scope.** 2. **I2C/SPI Bus Speed Limits vs. Requirement:**"),
        ]
        for prompt, answer in cases:
            with self.subTest(answer=answer):
                self.assertEqual(fact_check.check(answer, prompt)[1], [])

    def test_table_cells_are_judged_separately(self):
        # Qwen3-4B's table: download has GPIO2 low (right), normal boot has GPIO2 high (wrong: any value).
        row = ("| Download mode GPIO strapping | GPIO0 = low, GPIO2 = low at power-up | Page 17 | "
               "| Normal boot GPIO strapping | GPIO0 = high, GPIO2 = high | Page 17 |")
        self.assertEqual(fact_check.check(row, "P3")[1], ["normal boot needs GPIO2 high"])
        line = "Download mode: GPIO0 = LOW, GPIO2 = LOW (Page 17) Normal boot: GPIO0 = HIGH, GPIO2 = HIGH"
        self.assertEqual(fact_check.check(line, "P3")[1], ["normal boot needs GPIO2 high"])

    def test_real_errors_from_earlier_checks_are_still_flagged(self):
        cases = [
            ("P2", "the datasheet does not explicitly confirm the maximum supported I2C speed for the two I2C buses", "says 400 Kbit/s not documented"),
            ("P2", "The datasheet lists I2C interfaces, but does **not** explicitly state they support 400 Kbit/s.", "says 400 Kbit/s not documented"),
            ("P2", "The datasheet **does not provide explicit guidance on I2C bus frequency limits**", "says 400 Kbit/s not documented"),
            ("P5", "the context does not specify any dedicated general-purpose timer functionality", "says datasheet has no general timers"),
            ("P5", "The provided text does not describe general-purpose periodic timers", "says datasheet has no general timers"),
            ("P4", "MTDI = 0 selects the 1.8 V LDO for VDD_SDIO", "MTDI=0 gives 1.8 V"),
            ("P3", "**Download Mode Configuration:**\n- **GPIO0** must be **LOW**\n- **GPIO2** must be **HIGH** (3.3V)",
             "download needs GPIO2 high"),
        ]
        for prompt, answer, error in cases:
            with self.subTest(answer=answer):
                self.assertIn(error, fact_check.check(answer, prompt)[1])

    def test_summary_groups_by_label_model_and_retrieval(self):
        rows = [
            {"label": "a", "model": "m", "rag": True, "prompt": "P1", "facts": 3, "of": 3, "errors": [], "tokens": 300},
            {"label": "a", "model": "m", "rag": True, "prompt": "P2", "facts": 1, "of": 5, "errors": ["x"], "tokens": 500},
            {"label": "a", "model": "m", "rag": False, "prompt": "P1", "facts": 0, "of": 3, "errors": [], "tokens": 90},
        ]
        self.assertEqual(fact_check.summarize(rows),
                         [("a", "m", True, 2, 4, 8, 1, 400), ("a", "m", False, 1, 0, 3, 0, 90)])


if __name__ == "__main__":
    unittest.main()
