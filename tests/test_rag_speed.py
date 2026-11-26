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

    def test_reply_text_can_be_kept_off_the_terminal(self):
        out = io.StringIO()
        self.client.chat.completions.create.return_value = FakeStream(self.clock, [chunk(content="secret answer")], 0.01)
        with contextlib.redirect_stdout(out):
            reply, _ = rag.stream_reply([{"role": "user", "content": "q"}], rag.LEXICAL_MODEL, echo=False)
        self.assertEqual(reply, "secret answer")
        self.assertNotIn("secret answer", out.getvalue())
        self.assertIn(f"[{rag.LEXICAL_MODEL} | load", out.getvalue())   # the stats line still prints

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
