# Embedded Firmware Assistant

I am developing a local AI assistant for embedded firmware and Arduino-related hardware questions. My current work focuses on answering ESP32 design questions using datasheet evidence.

I have implemented PDF extraction and chunking with Docling, local embedding and answer generation through Lemonade, and persistent passage storage with Qdrant. My indexed documents and conversion cache survive restarts. Complete chat transcripts are not yet saved automatically by the RAG script.

## My Milestone 1 results

My evaluation record contains ten responses across five scenarios: server authentication, peripheral interfaces, custom-PCB flashing, power design, and RTOS timing. I rated the saved responses from 1 to 5 on completeness and correctness.

| Recorded condition | Responses | Mean completeness / 5 | Mean correctness / 5 |
|---|---|---|---|
| RAG | 5 | 3.6 | 3.0 |
| Without RAG | 5, including 2 partial records | 3.8 | 3.2 |

These are qualitative scores for a small recorded sample. Missing run metadata and two incomplete answers prevent a controlled performance comparison. I found both missing evidence coverage and incorrect interpretations of retrieved or supplied hardware information.

My [RAG results summary](RAG/README.md) reports the scores by scenario and the current implementation settings. My [full Milestone 1 evaluation](reading-and-background/milestone-data-collection/milestone-1.md) contains the scoring rubric, reasons for each rating, source references, prompts, and original responses.

My project materials are also collected in [Google Drive](https://drive.google.com/drive/u/3/folders/1S25RYl8OwbaISl_hC2jNwLhn0ZIYrT5T).
