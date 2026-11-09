import contextlib
import io
import signal
import unittest
from unittest.mock import MagicMock, call, patch

import httpx

from RAG import rag


class ShutdownTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.object(rag, "client", None))
        self.stack.enter_context(patch.object(rag, "qdrant", None))
        self.openai = self.stack.enter_context(patch.object(rag, "OpenAI"))
        self.qdrant = self.stack.enter_context(patch.object(rag, "QdrantClient"))
        self.post = self.stack.enter_context(patch.object(rag.httpx, "post"))
        self.post.return_value.status_code = 200
        self.post.return_value.json.return_value = {"status": "success"}

    def assert_cleaned_up(self):
        self.openai.return_value.close.assert_called_once_with()
        self.qdrant.return_value.close.assert_called_once_with()
        unloads = [c for c in self.post.call_args_list if c.args[0].endswith("/unload")]
        self.assertEqual(unloads, [
            call(f"{rag.BASE_URL}/unload", json={"model_name": model}, timeout=10)
            for model in (rag.EMBED_MODEL, rag.CHAT_MODEL)
        ])

    def test_normal_exit(self):
        with patch.object(rag, "make_prompt", return_value=lambda _: "/quit"):
            rag.main()
        self.assert_cleaned_up()

    def test_multiple_replies_keep_session_open_until_quit(self):
        commands = iter(["first question", "second question", "/quit"])

        def ask(_):
            self.openai.return_value.close.assert_not_called()
            self.qdrant.return_value.close.assert_not_called()
            self.assertFalse(any(c.args[0].endswith("/unload") for c in self.post.call_args_list))
            return next(commands)

        streams = [MagicMock(), MagicMock()]
        for stream in streams:
            stream.__iter__.return_value = [MagicMock(
                choices=[MagicMock(delta=MagicMock(content="answer"))], usage=None,
            )]
        create = self.openai.return_value.chat.completions.create
        create.side_effect = streams
        with patch.object(rag, "make_prompt", return_value=ask), \
             patch.object(rag, "retrieve", return_value=[]):
            rag.main()
        self.assertEqual(create.call_count, 2)
        loads = [c for c in self.post.call_args_list if c.args[0].endswith("/load")]
        self.assertEqual(loads, [call(
            f"{rag.BASE_URL}/load",
            json={"model_name": rag.CHAT_MODEL, "ctx_size": rag.CHAT_CONTEXT_TOKENS},
            timeout=120,
        )] * 2)
        self.assertEqual(create.call_args.kwargs["messages"], [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "second question"},
        ])
        for stream in streams:
            stream.__exit__.assert_called_once_with(None, None, None)
        self.assert_cleaned_up()

    def test_error_survives_cleanup_failures(self):
        error = RuntimeError("chat failed")
        self.openai.return_value.close.side_effect = RuntimeError("close failed")
        self.post.side_effect = [httpx.ConnectError("server unavailable"), MagicMock(status_code=200)]
        with patch.object(rag, "interactive_loop", side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                rag.main()
        self.assertIs(raised.exception, error)
        self.assert_cleaned_up()

    def test_partial_startup(self):
        self.qdrant.side_effect = RuntimeError("database locked")
        with self.assertRaisesRegex(RuntimeError, "database locked"):
            rag.main()
        self.openai.return_value.close.assert_called_once_with()
        self.assertEqual(self.post.call_count, 2)

    def test_stop_signals_unwind_and_restore_handlers(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=sig):
                original = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
                with patch.object(rag, "interactive_loop", side_effect=lambda: signal.raise_signal(sig)):
                    with self.assertRaises(SystemExit) as raised:
                        rag.main()
                self.assertEqual(raised.exception.code, 128 + sig)
                self.assert_cleaned_up()
                for s, handler in original.items():
                    self.assertEqual(signal.getsignal(s), handler)
                self.openai.reset_mock()
                self.qdrant.reset_mock()
                self.post.reset_mock()

    def test_prompt_interrupt_and_eof_exit(self):
        for error in (KeyboardInterrupt, EOFError):
            with self.subTest(error=error):
                ask = MagicMock(side_effect=error)
                with patch.object(rag, "make_prompt", return_value=ask):
                    rag.main()
                ask.assert_called_once()
                self.assert_cleaned_up()
                self.openai.reset_mock()
                self.qdrant.reset_mock()
                self.post.reset_mock()

    def test_interrupt_during_work(self):
        with patch.object(rag, "interactive_loop", side_effect=KeyboardInterrupt):
            rag.main()
        self.assert_cleaned_up()

    def test_stream_closes_on_error(self):
        rag.client = self.openai.return_value
        stream = rag.client.chat.completions.create.return_value
        error = RuntimeError("stream failed")
        stream.__iter__.side_effect = error
        with self.assertRaisesRegex(RuntimeError, "stream failed"):
            rag.stream_reply([])
        stream.__exit__.assert_called_once_with(RuntimeError, error, unittest.mock.ANY)

    def test_model_load_failure_exits_before_generation_and_cleans_up(self):
        for response in (
            httpx.Response(500, request=httpx.Request("POST", f"{rag.BASE_URL}/load")),
            httpx.Response(200, json={"status": "error", "message": "not enough memory"},
                           request=httpx.Request("POST", f"{rag.BASE_URL}/load")),
        ):
            with self.subTest(status=response.status_code):
                self.post.side_effect = [response, MagicMock(status_code=200), MagicMock(status_code=200)]
                ask = MagicMock(side_effect=["question", "/quit"])
                with patch.object(rag, "make_prompt", return_value=ask), \
                     patch.object(rag, "retrieve", return_value=[]):
                    with self.assertRaises((httpx.HTTPStatusError, RuntimeError)):
                        rag.main()
                self.openai.return_value.chat.completions.create.assert_not_called()
                ask.assert_called_once()
                self.assert_cleaned_up()
                self.openai.reset_mock()
                self.qdrant.reset_mock()
                self.post.reset_mock(side_effect=True)

    def test_command_errors_exit_and_clean_up(self):
        cases = [
            ("/add missing.pdf", "ingest"),
            ("/file missing.pdf", "resolve_path"),
            ("/file example.pdf", "convert"),
            ('/only "unterminated', "shlex.split"),
            ("question", "retrieve"),
            ("question", "stream_reply"),
        ]
        for command, operation in cases:
            with self.subTest(operation=operation):
                ask = MagicMock(side_effect=[command, "/quit"])
                error = RuntimeError("failed")
                with patch.object(rag, "make_prompt", return_value=ask), \
                     patch.object(rag, "resolve_path"), \
                     patch.object(rag, "retrieve", return_value=[]), \
                     patch(f"RAG.rag.{operation}", side_effect=error):
                    with self.assertRaises(RuntimeError) as raised:
                        rag.main()
                self.assertIs(raised.exception, error)
                ask.assert_called_once()
                self.assert_cleaned_up()
                self.openai.reset_mock()
                self.qdrant.reset_mock()
                self.post.reset_mock()


if __name__ == "__main__":
    unittest.main()
