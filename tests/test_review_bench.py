import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "RAG"))
import rag  # noqa: E402
import review_bench  # noqa: E402


class ReviewBenchTests(unittest.TestCase):
    def test_every_case_file_exists_and_each_bug_line_is_found(self):
        self.assertEqual(sorted(review_bench.BUGS), sorted(p.name for p in review_bench.CASES_DIR.glob("*.c")))
        self.assertLessEqual(review_bench.HELD_OUT, set(review_bench.BUGS))
        for name, bugs in review_bench.BUGS.items():
            for bug, anchor, *_ in bugs:
                with self.subTest(bug=bug):
                    review_bench.bug_line(name, anchor)   # raises if the anchor is not in the file

    def test_case_is_labelled_like_a_repository_snippet(self):
        prompt = review_bench.rag.build_rag_prompt(review_bench.QUESTION, [review_bench.case_hit("adc_average.c")])
        self.assertIn("[review_cases/adc_average.c:1-24]\n 1 | /* Averages", prompt)
        self.assertIn("\n13 |     uint16_t sum = 0;\n", prompt)
        self.assertIn("Question: Review this code for bugs.", prompt)

    def test_a_review_that_names_both_bugs_severe_first(self):
        answer = ("1. adc_average.c line 13: uint16_t sum overflows after 16 samples; use uint32_t.\n"
                  "2. line 17: division by zero when count is 0.")
        self.assertEqual(review_bench.score(answer, "adc_average.c"),
                         {"found": [b for b, *_ in review_bench.BUGS["adc_average.c"]], "of": 2, "severe_first": True,
                          "located": [b for b, *_ in review_bench.BUGS["adc_average.c"]]})   # lines 13 and 17

    def test_severe_bug_mentioned_second_is_not_first(self):
        answer = "Missing check: i2c_write return value is ignored. Also len can exceed the 4-byte buf, a buffer overflow."
        result = review_bench.score(answer, "sensor_i2c.c")
        self.assertEqual(len(result["found"]), 2)
        self.assertFalse(result["severe_first"])

    def test_a_review_that_misses_the_bugs(self):
        answer = "The code looks fine. Consider adding comments and using const where possible."
        for name in review_bench.BUGS:
            with self.subTest(name=name):
                self.assertEqual(review_bench.score(answer, name)["found"], [])

    def test_known_phrasings_are_matched(self):
        cases = [
            ("uart_ring.c", "Off-by-one: `next > RB_SIZE` lets head equal RB_SIZE", 0),
            ("uart_ring.c", "The ISR never checks whether the buffer is full, so it overwrites unread data", 1),
            ("tick_timer.c", "tick_flag must be declared volatile", 0),
            ("tick_timer.c", "elapsed_since returns 0 after tick_ms wraps around", 1),
        ]
        for name, answer, index in cases:
            with self.subTest(answer=answer):
                self.assertIn(review_bench.BUGS[name][index][0], review_bench.score(answer, name)["found"])

    def test_matches_from_the_first_run_that_were_wrong_are_cleared(self):
        cases = [
            # Says the planted wrap bug is correct.
            ("tick_timer.c", "*(Note: The `elapsed_since` function handles 32-bit wrap-around correctly by returning 0 if `now < start`)*", 1),
            ("tick_timer.c", "(though the logic handles overflow by returning 0 if `now < start`, the variable `tick_ms` is modified", 1),
            # Mentions i2c_write only to say the context does not cover it.
            ("sensor_i2c.c", "The context does not provide information on whether other logic bugs exist "
                             "(e.g., bounds checking, error handling in `i2c_write`).", 1),
            # Compares len with what the sensor returns, not with buf.
            ("sensor_i2c.c", "The function `sensor_read` passes `len` to `i2c_read`. If `len` is greater than the "
                             "number of bytes the sensor returns, or if the sensor", 0),
        ]
        for name, answer, index in cases:
            with self.subTest(answer=answer):
                self.assertNotIn(review_bench.BUGS[name][index][0], review_bench.score(answer, name)["found"])

    def test_correct_findings_from_the_first_run_are_still_matched(self):
        cases = [
            ("sensor_i2c.c", "If the `len` argument passed to `sensor_read` is greater than 4, this will cause a buffer overflow on the stack.", 0),
            ("sensor_i2c.c", "The function should validate that `len <= sizeof(buf)`.", 0),
            ("sensor_i2c.c", "It ignores the return value of `i2c_write(SENSOR_ADDR, &reg, 1);`.", 1),
            ("tick_timer.c", "`elapsed_since` returns 0 on overflow instead of wrapping; fix by allowing unsigned "
                             "wrap-around (return `now - start` unconditionally).", 1),
            ("tick_timer.c", "elapsed_since does not handle wrap-around: it returns 0 once tick_ms rolls over.", 1),
        ]
        for name, answer, index in cases:
            with self.subTest(answer=answer):
                self.assertIn(review_bench.BUGS[name][index][0], review_bench.score(answer, name)["found"])

    def test_quoting_the_held_out_code_is_not_a_finding(self):
        quote = ("`return (*PERIPH_STATUS & STATUS_READY == STATUS_READY);` [review_cases/status_poll.c:1-23]. "
                 "The local reply buffer is 32 bytes. The while loop can wait forever if the peripheral never becomes ready.")
        for name in ("status_poll.c", "cmd_parser.c"):
            with self.subTest(name=name):
                self.assertEqual(review_bench.score(quote, name)["found"], [])

    def test_line_numbers_are_scored_per_finding(self):
        # From the checklist-read run: the wrap bug is on line 19, the review said 26.
        uart = ("Bug 1: Array bounds out-of-bounds write in `uart_rx_isr`\n- **File**: [review_cases/uart_ring.c:1-35]\n"
                "- **Line**: 26\n- The check `next > RB_SIZE` is an off-by-one.\n\n"
                "Bug 2: Buffer full condition not handled\n- **Line**: 23\n- It does not check if the ring buffer is full.")
        result = review_bench.score(uart, "uart_ring.c")
        self.assertEqual(len(result["found"]), 2)
        self.assertEqual(result["located"], [review_bench.BUGS["uart_ring.c"][1][0]])   # 23 is right, 26 is not
        # Line 17 for the division; "Lines 13-16" covers the uint16_t sum on line 13.
        adc = ("**1. Integer Overflow in Summation**\n* **File:** `review_cases/adc_average.c`, Lines 13-16\n"
               "* `uint16_t sum` overflows; use uint32_t sum.\n\n"
               "**2. Division by Zero**\n* **File:** `review_cases/adc_average.c`, Line 17\n* If count is 0, division by zero.")
        self.assertEqual(review_bench.score(adc, "adc_average.c")["located"],
                         [b for b, *_ in review_bench.BUGS["adc_average.c"]])

    def test_the_whole_file_range_is_not_a_location(self):
        self.assertFalse(review_bench.located([(1, 35)], 19))
        self.assertTrue(review_bench.located([(18, 20)], 19))
        self.assertTrue(review_bench.located([(42, 42)], 43))   # within one line
        self.assertFalse(review_bench.located([(14, 14)], 12))
        self.assertEqual(review_bench.cited_lines("see uart_ring.c:22-26 and line 30", 5), [(22, 26), (30, 30)])

    def test_summary_groups_by_prompt_and_keeps_held_out_files_apart(self):
        rows = [
            {"prompt": "none", "case": "adc_average.c", "found": ["a", "b"], "of": 2, "severe_first": True,
             "completion_tokens": 400, "total_s": 10.0},
            {"prompt": "none", "case": "uart_ring.c", "found": ["a"], "of": 2, "severe_first": False,
             "completion_tokens": 600, "total_s": 14.0},
            {"prompt": "none", "case": "cmd_parser.c", "found": [], "of": 2, "severe_first": False,
             "completion_tokens": 900, "total_s": 20.0},
        ]
        rows[0]["located"] = ["a"]
        self.assertEqual(review_bench.summarize(rows), [("none", "checked", 2, 3, 4, 1, 1, 500, 12.0),
                                                        ("none", "held out", 1, 0, 2, 0, 0, 900, 20.0)])

    def test_held_out_bugs_are_matched_and_not_named_by_the_checklist(self):
        cases = [
            ("cmd_parser.c", "run_command returns `reply`, a local array that goes out of scope: a dangling pointer.", 0),
            ("cmd_parser.c", "case CMD_LED_ON is missing a `break`, so it falls through to CMD_LED_OFF.", 1),
            ("status_poll.c", "Operator precedence: `==` is evaluated before `&`, so this tests bit 0.", 0),
            ("status_poll.c", "`uint8_t i` can never reach a count above 255, so the loop never ends.", 1),
        ]
        for name, answer, index in cases:
            with self.subTest(answer=answer):
                self.assertIn(review_bench.BUGS[name][index][0], review_bench.score(answer, name)["found"])
        checklist = review_bench.rag.REVIEW_CHECKLIST.lower()
        for word in ("scope", "dangling", "break", "fall", "precedence", "operator"):
            self.assertNotIn(word, checklist)

class NoRulesTests(unittest.TestCase):
    def test_no_system_message_is_sent_when_the_rules_are_off(self):
        client = MagicMock()
        stream = MagicMock()
        stream.__enter__.return_value = stream
        stream.__iter__.return_value = iter([])
        client.chat.completions.create.return_value = stream
        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch.object(rag, "client", client),
            patch.object(rag, "system_prompt", lambda model: ""),
            patch.object(rag.httpx, "post", return_value=MagicMock(status_code=200, json=lambda: {})),
        ):
            rag.stream_reply([{"role": "user", "content": "q"}], rag.CODE_MODEL)
        self.assertEqual(client.chat.completions.create.call_args.kwargs["messages"], [{"role": "user", "content": "q"}])


if __name__ == "__main__":
    unittest.main()
