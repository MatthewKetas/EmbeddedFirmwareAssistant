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

    def test_keyword_search_brings_in_a_chunk_that_shares_rare_words(self):
        self.chunks = ["Feature List - Fast mode (400 Kbit/s)", "board overview", "flash pins", "boot modes"]
        question = "Which bus mode supports 400 Kbit/s?"
        # The I2C speed chunk sits far from the question in vector space, as on the real datasheet.
        vector = lambda text: [0.0, 1.0] if "400" in text and not text.startswith("Instruct:") else [1.0, 0.0]
        with patch.object(rag, "embed", side_effect=lambda texts: [vector(t) for t in texts]):
            rag.ingest("ESP32.pdf")
            with patch.object(rag, "TOP_N_CHUNKS", 2):
                with patch.object(rag, "HYBRID_SEARCH", False):
                    plain = [h.payload["text"] for h in rag.retrieve(question)]
                hybrid = [h.payload["text"] for h in rag.retrieve(question)]   # on by default
        self.assertNotIn("Feature List - Fast mode (400 Kbit/s)", plain)
        self.assertEqual(hybrid[0], "Feature List - Fast mode (400 Kbit/s)")

    def test_keyword_rank_weights_rare_words_and_skips_chunks_with_none(self):
        points = [SimpleNamespace(id=i, payload={"text": t}) for i, t in enumerate([
            "Pin Assignment: the pins can be chosen from any GPIO", "Feature List - Fast mode (400 Kbit/s)",
            "the the the bus", "Clocks and Timers"])]
        ranked = [p.id for p in rag.keyword_rank("a shared 400 Kbit/s I2C bus for the sensors", points)]
        self.assertEqual(ranked, [1, 2, 0])   # "Clocks and Timers" shares no word with the question

    def test_rag_prompt_forbids_values_from_general_knowledge(self):
        # Qwen once gave U0TXD as GPIO3 "in typical ESP32 pinouts" when the pin table was not retrieved.
        hit = SimpleNamespace(payload={"source": "ESP32.pdf", "page": 23, "text": "GPIO0 = 0"})
        prompt = rag.build_rag_prompt("Which pin is U0TXD?", [hit])
        self.assertIn("Every value, pin number, register or name you state must appear in the context", prompt)
        self.assertIn("do not fill gaps from general knowledge", prompt)
        self.assertIn("[ESP32.pdf, p.23]\nGPIO0 = 0", prompt)


class PrepareChunksTests(unittest.TestCase):
    # First lines and bodies as Docling produced them for ESP32.pdf.
    TEXTS = [
        "Product Overview\nESP32 is a single 2.4 GHz Wi-Fi-and-Bluetooth combo chip",
        "Note:\nCheck the link or the QR code to make sure that you use the latest version of this document:",
        "Contents\n\nProduct Overview, 1 = Product Overview. 2.5.3, 2 = ChipPower-upandReset",
        "List of Tables\n\n2-4, 1 = Description of Timing Parameters for Power-up and Reset",
        "List of Figures\n1-1, 1 = ESP32SeriesNomenclature",
        "4.8.4 I2CInterface\nESP32 has two I2C bus interfaces",
        "Feature List\n- Standard mode (100 Kbit/s)\n- Fast mode (400 Kbit/s)",
        "Pin Assignment\nFor regular I2C, the pins used can be chosen from any GPIOs via the GPIO Matrix.",
        "A.1. Notes on ESP32 Pin Lists\nTable 6-1. Notes on ESP32 Pin Lists",
        "Related Documentation\n- ESP32 Technical Reference Manual",
        "Revision History\n2026.07, Version = v5.3. 2026.07, Releasenotes = Fixed typos",
        "Cont'd from previous page\n2024.08, Version = v4.6. 2024.08, Releasenotes = Improved wording",
        "Disclaimer and Copyright Notice\nInformation in this document is subject to change",
    ]

    def test_front_matter_is_skipped(self):
        kept = [text.split("\n", 1)[0] for _, text in rag.prepare_chunks(self.TEXTS)]
        self.assertEqual(kept, [
            "Product Overview", "4.8.4 I2CInterface", "4.8.4 I2CInterface > Feature List",
            "4.8.4 I2CInterface > Pin Assignment", "A.1. Notes on ESP32 Pin Lists",
        ])

    def test_generic_headings_get_their_section_and_keep_their_index(self):
        prepared = dict(rag.prepare_chunks(self.TEXTS))
        self.assertEqual(prepared[6], "4.8.4 I2CInterface > Feature List\n- Standard mode (100 Kbit/s)\n"
                                      "- Fast mode (400 Kbit/s)")
        self.assertEqual(prepared[0], self.TEXTS[0])   # no numbered section before it

    def test_repeated_table_cells_are_kept_once(self):
        # Docling repeats a merged cell once per column: chunk 24 of ESP32.pdf held this nine times.
        cell = "VDDA, Function = Analogpowersupply(2.3V∼3.6V)."
        text = ("2.2 PinOverview\nTable 2-1. Pin Overview\nVDDA, No. = 1. VDDA, Type = P. " + " ".join([cell] * 9)
                + " LNA_IN, No. = 2. U0TXD, Function = GPIO1,. U0TXD, Function = U0TXD,.")
        (_, prepared), = rag.prepare_chunks([text])
        self.assertEqual(prepared, "2.2 PinOverview\nTable 2-1. Pin Overview\nVDDA, No. = 1. VDDA, Type = P. "
                                   + cell + " LNA_IN, No. = 2. U0TXD, Function = GPIO1,. U0TXD, Function = U0TXD,.")

    def test_prose_and_decimal_numbers_are_left_alone(self):
        text = "4.2.1 CPUClock\nThe PLL generates a 160 MHz clock. It runs at 2.4 GHz. The PLL generates a 160 MHz clock."
        self.assertEqual(rag.prepare_chunks([text]), [(0, text)])

    def test_a_numbered_note_is_not_a_section(self):
        texts = ["2.2 PinOverview\nTable 2-1", "1. Functionnames:\nCLK_OUT clock output",
                 "Pin Assignment\nFor SPI, the pins are multiplexed"]
        self.assertEqual([t.split("\n", 1)[0] for _, t in rag.prepare_chunks(texts)],
                         ["2.2 PinOverview", "2.2 PinOverview > 1. Functionnames:",
                          "2.2 PinOverview > Pin Assignment"])

    def test_a_continued_table_outside_the_revision_history_is_kept(self):
        texts = ["2.6 PinMappingBetweenChipandFlash/PSRAM\nTable 2-6 ...",
                 "Cont'd from previous page\nChip Pin, 1 = Off-Package PSRAM"]
        self.assertEqual([i for i, _ in rag.prepare_chunks(texts)], [0, 1])


if __name__ == "__main__":
    unittest.main()
