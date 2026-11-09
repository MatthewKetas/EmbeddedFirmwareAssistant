import contextlib
import importlib.util
import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from RAG import rag


class StubTokenizer:
    def __call__(self, text, **_):
        return {"offset_mapping": [match.span() for match in re.finditer(r"\S+", text)]}

    def apply_chat_template(self, messages, **_):
        return "\n".join(message["content"] for message in messages)

    def encode(self, text, **_):
        return text.split()


@unittest.skipUnless(
    importlib.util.find_spec("tree_sitter") and importlib.util.find_spec("tree_sitter_c"),
    "requires Tree-sitter and its C grammar",
)
class CodeTests(unittest.TestCase):
    def test_code_command_scopes_retrieval_and_refreshes_index(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            repo = Path(temp, "motor fw")
            repo.mkdir()
            header = repo / "pins.h"
            header.write_text("#define PWM_PIN 12\n")
            (repo / "pwm.c").write_text(
                "#include \"pins.h\"\n\n#if BOARD_A\nint pwm(void) { return PWM_PIN; }\n#endif\n"
            )
            commands = iter([f'/code "{repo}"', "What pin is used?", "/quit"])
            with (
                contextlib.closing(rag.QdrantClient(path=str(Path(temp, "db")))) as db,
                patch.object(rag, "qdrant", db),
                patch.object(rag, "EMBED_DIM", 2),
                patch.object(rag, "EMBED_BATCH", 1),
                patch.object(rag, "UNLOAD_AFTER_INGEST", False),
                patch.object(rag, "get_tokenizer", return_value=StubTokenizer()),
                patch.object(rag, "embed", side_effect=lambda texts: [[1.0, 0.0] for _ in texts]),
                patch.object(rag, "make_prompt", return_value=lambda _: next(commands)),
                patch.object(rag, "stream_reply", return_value="PWM uses pin 12.") as reply,
            ):
                rag.ensure_collection()
                db.upsert(rag.COLLECTION, points=[rag.PointStruct(
                    id=1, vector=[1.0, 0.0],
                    payload={"source": "unrelated.pdf", "page": 1, "text": "unrelated"},
                )])
                rag.interactive_loop()
                prompt = reply.call_args.args[0][-1]["content"]
                self.assertIn("[motor fw/pins.h:1-1]\n#define PWM_PIN 12", prompt)
                self.assertIn("[motor fw/pwm.c:3-5]\n#if BOARD_A", prompt)
                self.assertNotIn("unrelated.pdf", prompt)

                header.write_text("#define PWM_PIN 13\n")
                with patch.object(rag, "embed", side_effect=[[[1.0, 0.0]], RuntimeError("offline")]):
                    with self.assertRaisesRegex(RuntimeError, "offline"):
                        rag.ingest_code(str(repo))
                hits = rag.retrieve("pin", [str(repo.resolve())])
                self.assertIn("PWM_PIN 12", rag.build_rag_prompt("pin", hits))
                self.assertNotIn("PWM_PIN 13", rag.build_rag_prompt("pin", hits))

                (repo / "pwm.c").unlink()
                rag.ingest_code(str(repo))
                hits = rag.retrieve("pin", [str(repo.resolve())])
                self.assertEqual([h.payload["text"] for h in hits], ["#define PWM_PIN 13"])
                with patch.object(rag, "RAG_CONTEXT_TOKENS", 1):
                    self.assertEqual(rag.fit_code_context("pin", hits, []), [])
