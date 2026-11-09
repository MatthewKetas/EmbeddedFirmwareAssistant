# My ESP32 Datasheet RAG Results

I am developing a local datasheet assistant for embedded firmware questions. My current pipeline uses Docling to extract and chunk documents, Qwen models served by Lemonade to embed text and generate answers, and Qdrant to persist the searchable passages.

## My recorded evaluation

My [Milestone 1 report](../reading-and-background/milestone-data-collection/milestone-1.md) contains five ESP32 scenarios and ten recorded responses: five from RAG and five labeled Without RAG. I rated each saved response separately for completeness and correctness on a 1-5 scale, where 5 is strongest. My detailed rubric and the reasons for each score are in that report.

| Scenario | RAG completeness / 5 | RAG correctness / 5 | Without RAG completeness / 5 | Without RAG correctness / 5 |
|---|---|---|---|---|
| P1: Security verification | 5 | 3 | 5 | 4 |
| P2: External peripherals | 3 | 2 | 4 | 3 |
| P3: Flashing a custom PCB | 3 | 4 | 5 | 4 |
| P4: Custom-board power | 3 | 3 | 3* | 3* |
| P5: RTOS timing | 4 | 3 | 2* | 2* |
| **Descriptive mean** | **3.6** | **3.0** | **3.8** | **3.2** |

*The Without RAG power response ends at an empty limitations heading; its timing response cuts off mid-heading. I scored only the saved text. These scores may change if the missing response text becomes available.*

My comparison materials include manual-context packets, but the recorded outputs do not establish the exact input and settings for each Without RAG run. I have retained the original condition labels instead of treating them as a verified no-context baseline.

## What I found

I found the strongest coverage in the security responses and the Without RAG flashing response. The latter includes the UART pin mappings and both 50 µs reset/power-stabilization requirements that the RAG response omits.

I found material errors in both conditions. The RAG peripheral response invents GPIO162 by merging GPIO16 with a footnote and confuses chip pins with memory-side signal names. The Without RAG peripheral response incorrectly attributes full-duplex communication to I2C. The timing responses include unsupported clock or power-state claims, and the power responses sometimes confuse supply recommendations with measured consumption or guaranteed behavior.

The average scores describe this small saved sample only. I have no repeated runs, complete retrieval logs, or matched per-run settings recorded here, and two responses are incomplete. These data do not establish that either approach is generally superior or isolate the cause of each failure.

My only saved performance measurement is for RAG P1: 4,188 prompt tokens, 2,984 completion tokens, 72.69 seconds, and approximately 41.1 completion tokens per second. I do not have a comparable latency record for the other answers.

## My current implementation

The following values describe the current source code. I cannot assume they were identical for every recorded response.

| Component or setting | Current value |
|---|---|
| Chat model | Qwen3.6-35B-A3B-GGUF |
| Embedding model | Qwen3-Embedding-8B-GGUF |
| Embedding dimensions | 4,096 |
| Vector similarity | Cosine |
| Retrieved passages per question | Up to 10 |
| Chunk token budget | 768, measured with the Qwen embedding tokenizer |
| Requested chat context | 16,384 tokens |
| Generation settings | Temperature 1.0; top_p 0.9; top_k 40 |
| OCR | Disabled |

My converted documents are cached locally, and my Qdrant library persists across restarts. The saved passage metadata includes source filename, chunk number, page, and text. My conversation messages remain in memory during a session; the optional prompt-history file records input history, not a complete answer log. The code requests model unloading and client cleanup on graceful shutdown, with cleanup errors reported separately.

## My evidence

I used [ESP32 Series Datasheet v5.3](datasheets/ESP32.pdf), a 78-page hardware reference. The [full milestone report](../reading-and-background/milestone-data-collection/milestone-1.md) preserves the prompts, source hash, evidence locations, all ten response records, and individual score explanations. No new model responses were generated for this review.
