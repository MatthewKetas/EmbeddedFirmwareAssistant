import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app_prototype.backend.app import app, rag


BOARD_XML = b"""<device xmlns="urn:example:svd">
  <name>Demo Board</name><version>1</version>
  <peripherals><peripheral><name>GPIO_TEST</name><baseAddress>0x4000</baseAddress>
    <registers><register><name>MODE_TEST</name><addressOffset>0x04</addressOffset></register></registers>
  </peripheral></peripherals>
</device>"""


class LocalAppTests(unittest.TestCase):
    def test_board_import_persists_and_grounds_chat_with_history(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(rag.board_map, "DB_PATH", Path(directory, "boards.sqlite")),
            patch.object(rag, "QDRANT_PATH", Path(directory, "qdrant")),
            patch.object(rag, "open_chat_stream") as open_stream,
        ):
            stream = open_stream.return_value
            stream.__enter__.return_value = [MagicMock(choices=[MagicMock(delta=MagicMock(content="Reply"))])]

            with TestClient(app, base_url="http://localhost") as client:
                self.assertEqual(client.post("/api/boards", files={"file": ("invalid.xml", b"<not-svd/>")}).status_code, 422)
                self.assertEqual(client.post("/api/boards", files={"file": ("dtd.xml", b"<!DOCTYPE device><device/>")}).status_code, 422)
                uploaded = client.post("/api/boards", files={"file": ("board.xml", BOARD_XML)},
                                       headers={"Origin": "http://127.0.0.1:3000"})
                self.assertEqual(uploaded.status_code, 200, uploaded.text)
                board = uploaded.json()
                self.assertEqual(client.post("/api/boards", files={"file": ("board.xml", BOARD_XML)}).json(), board)
                changed = BOARD_XML.replace(b"0x04", b"0x08")
                self.assertEqual(client.post("/api/boards", files={"file": ("board.xml", changed)}).status_code, 422)
                rejected = client.post("/api/boards", files={"file": ("board.xml", BOARD_XML)},
                                       headers={"Origin": "https://example.test"})
                self.assertEqual(rejected.status_code, 403)

            with TestClient(app, base_url="http://localhost") as client:
                self.assertIn(board, client.get("/api/boards").json())
                history = [{"role": "user", "content": "first question"}, {"role": "assistant", "content": "first answer"}]
                response = client.post("/api/chat", json={
                    "board_id": board["id"], "prompt": "What is MODE_TEST?", "history": history,
                })
                self.assertEqual([json.loads(line) for line in response.text.splitlines()], [
                    {"text": "Reply"}, {"done": True},
                ])
                messages = open_stream.call_args.args[0]
                self.assertEqual(messages[:-1], history)
                self.assertIn("GPIO_TEST.MODE_TEST, offset 0x04", messages[-1]["content"])
