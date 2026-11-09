import contextlib
import importlib.util
import io
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from RAG import rag


class BoardMapTests(unittest.TestCase):
    def test_commands_persist_facts_by_board_and_add_context(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            board_map = rag.board_map
            commands = iter([
                "/remember pwm_pin=unscoped",
                "/board arduino-uno",
                "/remember pwm_pin=D9",
                "/remember PWM_PIN=D10",
                "What are my PWM pin and the PORTB register?",
                "/board esp-32",
                "/remember pwm_pin=GPIO18",
                "What are my PWM pin and the GPIO_OUT_REG register?",
                "/board none",
                "What is my PWM pin?",
                "/quit",
            ])
            hit = SimpleNamespace(payload={"source": "firmware.pdf", "page": 2, "text": "PWM documentation"})
            with (
                patch.object(board_map, "DB_PATH", Path(temp, "knowledge.sql")),
                patch.object(rag, "make_prompt", return_value=lambda _: next(commands)),
                patch.object(rag, "retrieve", return_value=[hit]),
                patch.object(rag, "stream_reply", return_value="reply") as reply,
            ):
                rag.interactive_loop()
                uno, esp, unscoped = (call.args[0] for call in reply.call_args_list)
                self.assertEqual([len(uno), len(esp), len(unscoped)], [1, 1, 1])
                self.assertIn("[remember:pwm_pin] User-confirmed pwm_pin = D10", uno[0]["content"])
                self.assertIn("[atmega328p.svd] PORTB.PORTB", uno[0]["content"])
                self.assertIn("[firmware.pdf, p.2]", uno[0]["content"])
                self.assertIn("[esp32.svd] GPIO.OUT", esp[0]["content"])
                self.assertIn("pwm_pin = GPIO18", esp[0]["content"])
                self.assertNotIn("D10", esp[0]["content"])
                self.assertNotIn("[remember:", unscoped[0]["content"])

                with board_map.connect() as db:
                    board_map.initialize(db)
                    rows = db.execute("SELECT board_id, value FROM board_facts ORDER BY board_id").fetchall()
                    self.assertEqual([tuple(row) for row in rows], [("arduino-uno", "D10"), ("esp-32", "GPIO18")])
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM svd_devices").fetchone()[0], 2)
                    self.assertFalse(db.execute("PRAGMA foreign_key_check").fetchall())


class StubChunker:
    def chunk(self, dl_doc):
        return [SimpleNamespace(meta=None, text=dl_doc)]

    def contextualize(self, chunk):
        return chunk.text


class StubTokenizer:
    def __call__(self, text, **_):
        return {"offset_mapping": [match.span() for match in re.finditer(r"\S+", text)]}


class BoardTagTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        stdout = contextlib.redirect_stdout(io.StringIO())
        stdout.__enter__()
        self.addCleanup(stdout.__exit__, None, None, None)
        db = rag.QdrantClient(path=str(Path(self.temp.name, "db")))
        self.addCleanup(db.close)
        for patcher in (
            patch.object(rag, "qdrant", db),
            patch.object(rag, "EMBED_DIM", 2),
            patch.object(rag, "UNLOAD_AFTER_INGEST", False),
            patch.object(rag, "embed", side_effect=lambda texts: [[1.0, 0.0] for _ in texts]),
            patch.object(rag, "resolve_path", side_effect=Path),
            patch.object(rag, "convert", side_effect=lambda path: path.stem),
            patch.object(rag, "get_chunker", return_value=StubChunker()),
            patch.object(rag, "get_tokenizer", return_value=StubTokenizer()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def sources(self, board_id):
        return sorted(hit.payload["source"] for hit in rag.retrieve("pin", None, board_id))

    def test_documents_are_tagged_and_retrieval_is_limited_to_the_selected_board(self):
        rag.ingest("esp32.pdf", "esp-32")
        rag.ingest("uno.pdf", "arduino-uno")
        rag.ingest("generic.pdf")

        self.assertEqual(self.sources("arduino-uno"), ["generic.pdf", "uno.pdf"])
        self.assertEqual(self.sources("esp-32"), ["esp32.pdf", "generic.pdf"])
        self.assertEqual(self.sources(None), ["esp32.pdf", "generic.pdf", "uno.pdf"])

    def test_board_filter_combines_with_the_only_scope(self):
        rag.ingest("esp32.pdf", "esp-32")
        rag.ingest("uno.pdf", "arduino-uno")

        self.assertEqual([h.payload["source"] for h in rag.retrieve("pin", ["uno.pdf"], "arduino-uno")], ["uno.pdf"])
        self.assertEqual(rag.retrieve("pin", ["uno.pdf"], "esp-32"), [])

    @unittest.skipUnless(
        importlib.util.find_spec("tree_sitter") and importlib.util.find_spec("tree_sitter_c"),
        "requires Tree-sitter and its C grammar",
    )
    def test_code_is_tagged_and_retrieval_is_limited_to_the_selected_board(self):
        repo = Path(self.temp.name, "motor fw")
        repo.mkdir()
        (repo / "pwm.c").write_text("int pwm(void) { return 12; }\n")
        source = rag.ingest_code(str(repo), "esp-32")

        hits = rag.retrieve("pin", [source], "esp-32")
        self.assertEqual([hit.payload["board_id"] for hit in hits], ["esp-32"])
        self.assertEqual(rag.retrieve("pin", [source], "arduino-uno"), [])