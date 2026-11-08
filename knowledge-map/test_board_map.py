import contextlib
import io
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
