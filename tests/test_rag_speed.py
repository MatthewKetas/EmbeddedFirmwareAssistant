import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from RAG import rag


def chunk(content=None, reasoning=None):
    delta = SimpleNamespace(content=content, reasoning_content=reasoning)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)


class FakeStream:
    """Yields chunks while advancing a fake clock, like a server producing tokens."""

    def __init__(self, clock, chunks, step):
        self.clock, self.chunks, self.step = clock, chunks, step

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for c in self.chunks:
            self.clock[0] += self.step
            yield c


class SpeedTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.clock = [0.0]
        self.stack.enter_context(patch.object(rag.time, "monotonic", lambda: self.clock[0]))

        def slow_load(*_, **__):
            self.clock[0] += 10.0     # a model load that takes 10 s
            return MagicMock(status_code=200, json=lambda: {"status": "success"})

        self.post = self.stack.enter_context(patch.object(rag.httpx, "post", side_effect=slow_load))
        self.client = self.stack.enter_context(patch.object(rag, "client", MagicMock()))

    def reply(self, model, chunks, step=0.01):
        self.client.chat.completions.create.return_value = FakeStream(self.clock, chunks, step)
        return rag.stream_reply([{"role": "user", "content": "q"}], model)

    def test_decode_speed_excludes_model_load_and_prefill(self):
        # Load 10 s, then 101 tokens 0.01 s apart: first token at 0.01 s, the other 100 over 1 s.
        tokens = [chunk(content="x")] * 101
        usage = SimpleNamespace(prompt_tokens=50, completion_tokens=101, total_tokens=151)
        final = SimpleNamespace(choices=[], usage=usage)
        reply, stats = self.reply(rag.LEXICAL_MODEL, tokens + [final])
        self.assertEqual(reply, "x" * 101)
        self.assertAlmostEqual(stats["load_s"], 10.0)
        self.assertAlmostEqual(stats["ttft_s"], 0.01)
        self.assertAlmostEqual(stats["decode_tps"], 100.0, places=3)
        # The old figure divided by load + prefill + decode: 101 / 11.02 s = ~9.2 tok/s.
        self.assertAlmostEqual(stats["total_s"], 11.02, places=3)

    def test_server_timings_are_used_when_reported(self):
        final = SimpleNamespace(
            choices=[], usage=SimpleNamespace(prompt_tokens=50, completion_tokens=2, total_tokens=52),
            timings={"predicted_per_second": 88.5, "prompt_per_second": 1200.0},
        )
        _, stats = self.reply(rag.LEXICAL_MODEL, [chunk(content="a"), chunk(content="b"), final])
        self.assertEqual(stats["decode_tps"], 88.5)
        self.assertEqual(stats["prefill_tps"], 1200.0)

    def test_thinking_is_counted_and_kept_out_of_the_reply(self):
        chunks = [chunk(reasoning="hm")] * 3 + [chunk(content="answer")]
        reply, stats = self.reply(rag.CODE_MODEL, chunks)
        self.assertEqual(reply, "answer")
        self.assertEqual(stats["thinking_tokens"], 3)
        self.assertAlmostEqual(stats["ttft_s"], 0.01)      # thinking token = prefill finished
        self.assertAlmostEqual(stats["answer_s"], 0.04)    # first visible answer token

    def test_both_chat_models_have_thinking_off_by_default(self):
        for model in (rag.LEXICAL_MODEL, rag.CODE_MODEL):
            self.reply(model, [chunk(content="a")])
            self.assertIs(self.client.chat.completions.create.call_args.kwargs["extra_body"]["enable_thinking"], False)

    def test_thinking_on_leaves_the_server_default(self):
        with patch.dict(rag.MODEL_OPTIONS[rag.CODE_MODEL], thinking=True):
            self.reply(rag.CODE_MODEL, [chunk(content="a")])
        self.assertNotIn("enable_thinking", self.client.chat.completions.create.call_args.kwargs["extra_body"])
        # Reasoning counts towards max_tokens, so a thinking model is not capped.
        self.assertNotIn("max_tokens", self.client.chat.completions.create.call_args.kwargs)

    def test_replies_are_capped_and_a_cut_is_reported(self):
        out = io.StringIO()
        last = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="b", reasoning_content=None),
                                                        finish_reason="length")], usage=None)
        self.client.chat.completions.create.return_value = FakeStream(self.clock, [chunk(content="a"), last], 0.01)
        with contextlib.redirect_stdout(out):
            reply, stats = rag.stream_reply([{"role": "user", "content": "q"}], rag.CODE_MODEL, echo=False)
        self.assertEqual(self.client.chat.completions.create.call_args.kwargs["max_tokens"], rag.RAG_REPLY_TOKENS)
        self.assertEqual(reply, "ab")
        self.assertTrue(stats["cut"])
        self.assertIn(f"stopped at the {rag.RAG_REPLY_TOKENS}-token limit", out.getvalue())
        _, stats = self.reply(rag.CODE_MODEL, [chunk(content="a")])
        self.assertFalse(stats["cut"])

    def test_reply_text_can_be_kept_off_the_terminal(self):
        out = io.StringIO()
        self.client.chat.completions.create.return_value = FakeStream(self.clock, [chunk(content="secret answer")], 0.01)
        with contextlib.redirect_stdout(out):
            reply, _ = rag.stream_reply([{"role": "user", "content": "q"}], rag.LEXICAL_MODEL, echo=False)
        self.assertEqual(reply, "secret answer")
        self.assertNotIn("secret answer", out.getvalue())
        self.assertIn(f"[{rag.LEXICAL_MODEL} | load", out.getvalue())   # the stats line still prints

    def test_answer_rules_go_to_gemma_and_the_review_checklist_to_the_code_model(self):
        self.reply(rag.LEXICAL_MODEL, [chunk(content="a")])
        sent = self.client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(sent[0]["role"], "system")
        self.assertIn("Lead with the direct answer", sent[0]["content"])
        self.assertEqual(sent[1:], [{"role": "user", "content": "q"}])
        # The rules cut Qwen's planted-bug finds from 17 to 10 of 24 in review_bench.py; it gets a checklist.
        self.reply(rag.CODE_MODEL, [chunk(content="a")])
        sent = self.client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(sent[0], {"role": "system", "content": rag.REVIEW_CHECKLIST})
        self.assertNotIn("what it lacks", sent[0]["content"])
        self.assertIn("full or empty", sent[0]["content"])
        # Qwen wrote its tracing out (up to 12,020 tokens) when told only to report traced bugs.
        self.assertIn("write only the findings, not the tracing", sent[0]["content"])

    def test_rules_ask_for_the_key_values_and_set_no_length_cap(self):
        # A "briefly ... under 350 words" version cost 9 points of key facts in the rules bench.
        rules = rag.system_prompt(rag.LEXICAL_MODEL)
        self.assertIn("Cover every part of the question", rules)
        self.assertIn("values, limits and pin cautions", rules)
        self.assertNotIn("words", rules)
        self.assertNotIn("briefly", rules)

    def test_rules_stay_short(self):
        # Small models follow a few rules better than a long list, and every prompt carries them.
        for model in (rag.LEXICAL_MODEL, rag.CODE_MODEL):
            self.assertLess(len(rag.system_prompt(model).split()), 130)

    def test_load_error_shows_lemonade_message(self):
        # A mistyped model name used to surface only as "404 Not Found".
        self.post.side_effect = None
        self.post.return_value = httpx.Response(
            404, json={"error": "Model not found: Gemma-4-E48-it-GGUF"},
            request=httpx.Request("POST", f"{rag.BASE_URL}/load"),
        )
        with self.assertRaisesRegex(RuntimeError, r"Could not load .*: 404 .*Model not found: Gemma-4-E48-it-GGUF"):
            rag.stream_reply([{"role": "user", "content": "q"}], rag.LEXICAL_MODEL)
        self.client.chat.completions.create.assert_not_called()

    def test_load_sends_each_models_options(self):
        with patch.dict(rag.MODEL_OPTIONS[rag.CODE_MODEL], llamacpp_args="--n-cpu-moe 20", ctx_size=8192):
            self.reply(rag.CODE_MODEL, [chunk(content="a")])
        self.assertEqual(self.post.call_args.kwargs["json"], {
            "model_name": rag.CODE_MODEL, "ctx_size": 8192, "llamacpp_args": "--n-cpu-moe 20",
        })
        self.reply(rag.LEXICAL_MODEL, [chunk(content="a")])
        self.assertEqual(self.post.call_args.kwargs["json"], {
            "model_name": rag.LEXICAL_MODEL, "ctx_size": rag.MODEL_OPTIONS[rag.LEXICAL_MODEL]["ctx_size"],
        })


class HistoryTests(unittest.TestCase):
    def test_only_the_last_few_exchanges_are_kept(self):
        history = [{"role": r, "content": str(i)} for i in range(5) for r in ("user", "assistant")]
        with patch.object(rag, "HISTORY_TURNS", 3):
            self.assertEqual([m["content"] for m in rag.recent(history)], ["2", "2", "3", "3", "4", "4"])
        with patch.object(rag, "HISTORY_TURNS", 0):
            self.assertEqual(rag.recent(history), [])

    def test_a_long_session_sends_a_bounded_history(self):
        doc = SimpleNamespace(payload={"source": "ESP32.pdf", "page": 3, "text": "3.3 V"})
        commands = iter([f"question {i}" for i in range(6)] + ["/quit"])
        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch.object(rag, "make_prompt", return_value=lambda _: next(commands)),
            patch.object(rag, "retrieve", return_value=[doc]),
            patch.object(rag, "stream_reply", return_value=("answer", {})) as reply,
        ):
            rag.interactive_loop()
        last = reply.call_args.args[0]
        self.assertEqual(len(last), 2 * rag.HISTORY_TURNS + 1)   # earlier exchanges plus this question
        self.assertEqual(last[0]["content"], "question 2")
        self.assertIn("Answer only the question at the end of this message", last[-1]["content"])


class FollowUpTests(unittest.TestCase):
    HISTORY = [{"role": "user", "content": "When does the motor stall?"}, {"role": "assistant", "content": "..."}]

    def test_a_question_that_refers_back_also_searches_with_the_previous_one(self):
        for question in ("And what happens when that fault trips?", "What about the watchdog?", "Why does it reset?"):
            with self.subTest(question=question):
                self.assertEqual(rag.retrieval_query(question, self.HISTORY), f"When does the motor stall?\n{question}")

    def test_a_new_question_or_a_first_question_searches_alone(self):
        self.assertEqual(rag.retrieval_query("Which GPIO drives the PWM?", self.HISTORY), "Which GPIO drives the PWM?")
        self.assertEqual(rag.retrieval_query("And the timeout?", []), "And the timeout?")

    def test_the_chat_loop_retrieves_with_the_follow_up_query(self):
        doc = SimpleNamespace(payload={"source": "ESP32.pdf", "page": 3, "text": "3.3 V"})
        commands = iter(["When does the motor stall?", "And what trips that fault?", "/quit"])
        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch.object(rag, "make_prompt", return_value=lambda _: next(commands)),
            patch.object(rag, "retrieve", return_value=[doc]) as retrieve,
            patch.object(rag, "stream_reply", return_value=("answer", {})),
        ):
            rag.interactive_loop()
        self.assertEqual([c.args[0] for c in retrieve.call_args_list],
                         ["When does the motor stall?", "When does the motor stall?\nAnd what trips that fault?"])


class RoutingTests(unittest.TestCase):
    def test_code_hits_go_to_the_code_model(self):
        code = SimpleNamespace(payload={"file": "pwm.c", "source": "/repo", "text": ""})
        doc = SimpleNamespace(payload={"source": "ESP32.pdf", "page": 3, "text": ""})
        self.assertEqual(rag.pick_model([doc, code]), rag.CODE_MODEL)
        self.assertEqual(rag.pick_model([doc]), rag.LEXICAL_MODEL)
        self.assertEqual(rag.pick_model([]), rag.LEXICAL_MODEL)

    def test_document_question_is_answered_by_the_lexical_model(self):
        doc = SimpleNamespace(payload={"source": "ESP32.pdf", "page": 3, "text": "3.3 V"})
        commands = iter(["What voltage?", "/quit"])
        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch.object(rag, "make_prompt", return_value=lambda _: next(commands)),
            patch.object(rag, "retrieve", return_value=[doc]),
            patch.object(rag, "stream_reply", return_value=("3.3 V", {})) as reply,
        ):
            rag.interactive_loop()
        self.assertEqual(reply.call_args.args[1], rag.LEXICAL_MODEL)


if __name__ == "__main__":
    unittest.main()
