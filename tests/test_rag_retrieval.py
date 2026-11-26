import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from RAG import rag


class StubChunker:
    def chunk(self, dl_doc):
        return [SimpleNamespace(meta=None, text=text) for text in dl_doc]

    def contextualize(self, chunk):
        return chunk.text


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.docs = Path(self.temp.name, "datasheets")
        self.docs.mkdir()
        (self.docs / "ESP32.pdf").write_bytes(b"%PDF")
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        db = rag.QdrantClient(path=str(Path(self.temp.name, "db")))
        self.addCleanup(db.close)
        self.chunks = ["watchdog timers", "general-purpose timers"]
        for patcher in (
            patch.object(rag, "qdrant", db),
            patch.object(rag, "DOCS_DIR", self.docs),
            patch.object(rag, "EMBED_DIM", 2),
            patch.object(rag, "UNLOAD_AFTER_INGEST", False),
            patch.object(rag, "embed", side_effect=lambda texts: [[1.0, 0.0] for _ in texts]),
            patch.object(rag, "convert", side_effect=lambda path: self.chunks),
            patch.object(rag, "get_chunker", return_value=StubChunker()),
        ):
            stack.enter_context(patcher)

    def test_add_uses_the_name_on_disk_whatever_case_was_typed(self):
        # On Windows "esp32.pdf" opens ESP32.pdf; it must not become a second source.
        self.assertEqual(rag.resolve_path("esp32.pdf"), self.docs / "ESP32.pdf")
        rag.ingest("esp32.pdf")
        rag.ingest("ESP32.pdf")
        self.assertEqual(rag.list_sources(), ["ESP32.pdf"])
        self.assertEqual(rag.qdrant.count(rag.COLLECTION).count, 2)

    def test_re_adding_replaces_a_copy_stored_under_other_case(self):
        # A library indexed before this fix holds the datasheet as both ESP32.pdf and esp32.pdf.
        rag.ingest("ESP32.pdf")
        rag.ensure_collection()
        rag.qdrant.upsert(rag.COLLECTION, points=[rag.PointStruct(
            id=99, vector=[1.0, 0.0], payload={"source": "esp32.pdf", "chunk": 0, "page": 1, "text": "old copy"},
        )])
        rag.ingest("ESP32.pdf")
        self.assertEqual(rag.list_sources(), ["ESP32.pdf"])

    def test_retrieval_skips_identical_chunks(self):
        self.chunks = ["watchdog timers", "watchdog  timers", "general-purpose timers", "watchdog timers"]
        # The watchdog copies sit closest to the query, so without skipping they fill both slots.
        vector = lambda text: [1.0, 0.0] if "watchdog" in text or "Query:" in text else [0.6, 0.8]
        with patch.object(rag, "embed", side_effect=lambda texts: [vector(t) for t in texts]):
            rag.ingest("ESP32.pdf")
            with patch.object(rag, "TOP_N_CHUNKS", 2):
                hits = rag.retrieve("timers")
        self.assertEqual(sorted(h.payload["text"] for h in hits), ["general-purpose timers", "watchdog timers"])


if __name__ == "__main__":
    unittest.main()
