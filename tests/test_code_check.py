import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "RAG"))
import code_check  # noqa: E402

rag = code_check.rag


def hit(file, start, end, text="x"):
    return SimpleNamespace(payload={"file": file, "start_line": start, "end_line": end, "text": text,
                                    "source": "motor_fw"})


class CodeCheckTests(unittest.TestCase):
    def test_every_anchor_is_in_the_sample_repo(self):
        for qid, _, anchors, _ in code_check.QUESTIONS:
            for file, text in anchors:
                with self.subTest(qid=qid, anchor=text):
                    code_check.anchor_line(file, text)   # raises if the line is not there

    def test_anchor_rank_is_the_chunk_that_holds_the_line(self):
        line = code_check.anchor_line("motor.c", "#define STALL_TIME_MS")
        hits = [hit("pwm.c", 1, 40), hit("motor.c", 30, 60), hit("motor.c", 1, 26)]
        self.assertEqual(code_check.anchor_ranks(hits, [("motor.c", "#define STALL_TIME_MS")]),
                         {f"motor.c:{line}": 3})
        self.assertEqual(code_check.anchor_ranks(hits[:2], [("motor.c", "#define STALL_TIME_MS")]),
                         {f"motor.c:{line}": None})

    def test_budget_is_applied_with_and_without_line_numbers(self):
        seen = []

        def fit(question, hits, history):
            seen.append(rag.numbered(hits[0].payload))
            return hits[:1]

        with patch.object(rag, "fit_code_context", side_effect=fit):
            code_check.sent_with("q", [hit("pwm.c", 5, 6, "a\nb")], numbered=False)
            code_check.sent_with("q", [hit("pwm.c", 5, 6, "a\nb")], numbered=True)
        self.assertEqual(seen, ["a\nb", "5 | a\n6 | b"])
        self.assertEqual(rag.numbered(hit("pwm.c", 1, 1, "c").payload), "1 | c")   # restored afterwards

    def test_correct_answers_state_every_fact(self):
        answers = {
            "C1": "The PWM output is PIN_MOTOR_PWM, GPIO 18 [motor_fw/board_pins.h:5], at 20 kHz (PWM_FREQUENCY_HZ = 20000u).",
            "C2": "The ISR drops the new byte and increments rx_overruns, so queued data is not overwritten.",
            "C3": "It retries 3 more times (SENSOR_RETRIES), and each transfer waits up to 50 ms.",
            "C4": "A stall is current above 1500 mA while speed is below 30 rpm for 500 ms without a break.",
            "C5": "The timeout is 2000 ms; it is fed only when every registered task has checked in.",
            "C6": "Below 3300 mV for 5 consecutive readings; power_check_battery runs once a second.",
            "C7": "It falls back to the defaults and writes them back at once with config_save_now().",
            "C8": "Every 10 ms (CONTROL_PERIOD_MS).",
        }
        for qid, _, anchors, facts in code_check.QUESTIONS:
            with self.subTest(qid=qid):
                result = code_check.score_answer(answers[qid], anchors, facts, [])
                self.assertEqual(len(result["facts"]), result["of"])

    def test_values_written_as_the_code_spells_them(self):
        # Qwen's answers from the first --answer run; the first patterns missed all four.
        cases = {
            "C1": "It switches at a frequency of 20,000 Hz [motor_fw/pwm.c:6].",
            "C5": "The watchdog timeout is **2000u** milliseconds (defined as **WDT_TIMEOUT_MS**).",
            "C6": "below **BATTERY_SHUTDOWN_MV** (defined as **3300u** mV) [motor_fw/power.c:8-9].",
            "C8": "The main loop runs the motor control step every 10 milliseconds.",
            "C1b": "The GPIO is **PIN_MOTOR_PWM** (pin number **18**) [motor_fw/board_pins.h:6].",
        }
        names = {"C1": "20 kHz", "C5": "2000 ms", "C6": "3300 mV", "C8": "every 10 ms", "C1b": "GPIO 18"}
        facts = {qid: f for qid, _, _, f in code_check.QUESTIONS}
        for qid, answer in cases.items():
            with self.subTest(qid=qid):
                self.assertIn(names[qid], code_check.score_answer(answer, [], facts[qid[:2]], [])["facts"])

    def test_wrong_answers_miss_the_facts(self):
        facts = {qid: f for qid, _, _, f in code_check.QUESTIONS}
        cases = [("C1", "The PWM runs on GPIO 19 at 25 kHz.", 0), ("C1", "Pin number 118 at 2 kHz.", 0), ("C4", "A stall is 2 A for one second.", 0),
                 ("C8", "The control step runs every 100 ms.", 0), ("C6", "It shuts down at 3.0 V right away.", 0),
                 ("C5", "The timeout is 12000 ms, fed by a timer.", 0), ("C8", "It runs every 110 milliseconds.", 0)]
        for qid, answer, expected in cases:
            with self.subTest(answer=answer):
                self.assertEqual(len(code_check.score_answer(answer, [], facts[qid], [])["facts"]), expected)

    def test_a_cited_line_counts_when_it_falls_in_an_answer_chunk(self):
        facts = [("x", r"x")]
        self.assertTrue(code_check.score_answer("See motor.c line 70.", [], facts, [(64, 87)])["located"])
        self.assertTrue(code_check.score_answer("[motor_fw/motor.c:64-87]", [], facts, [(64, 87)])["located"])
        self.assertFalse(code_check.score_answer("See line 12.", [], facts, [(64, 87)])["located"])
        self.assertFalse(code_check.score_answer("motor.c:1-200", [], facts, [(64, 87)])["located"])


class SampleRepoTests(unittest.TestCase):
    def test_sample_repo_chunks_put_each_anchor_in_one_chunk(self):
        # A stand-in tokenizer: one token per word or run of spaces.
        tokenizer = lambda text, **_: {"offset_mapping": [m.span() for m in re.finditer(r"\S+|\s+", text)]}
        with patch.object(rag, "get_tokenizer", return_value=tokenizer):
            chunks = list(rag.code_chunks(code_check.REPO))
        for _, _, anchors, _ in code_check.QUESTIONS:
            for file, text in anchors:
                line = code_check.anchor_line(file, text)
                holding = [c for c in chunks if c["file"] == file and c["start_line"] <= line <= c["end_line"]]
                with self.subTest(anchor=text):
                    self.assertEqual(len(holding), 1)
                    self.assertIn(text, holding[0]["text"])


if __name__ == "__main__":
    unittest.main()
