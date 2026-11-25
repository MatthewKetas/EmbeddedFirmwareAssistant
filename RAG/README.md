# My ESP32 Datasheet RAG Results

I am developing a local datasheet assistant for embedded firmware questions. My current pipeline uses Docling to extract and chunk documents, Lemonade to serve a Qwen embedding model and two chat models (Qwen for code, Gemma for everything else), and Qdrant to persist the searchable passages.

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

My Milestone 1 record has only one performance measurement, for RAG P1: 4,188 prompt tokens, 2,984 completion tokens, 72.69 seconds, and approximately 41.1 completion tokens per second. That figure divides completion tokens by the whole request time, including model loading and prompt processing. I do not have a comparable latency record for the other Milestone 1 answers; my later speed measurements are in [My speed measurements](#my-speed-measurements).

## My current implementation

The following values describe the current source code. I cannot assume they were identical for every recorded response.

| Component or setting | Current value |
|---|---|
| Code chat model | Qwen3.6-35B-A3B-GGUF, for turns whose retrieved context contains code |
| Lexical chat model | Gemma-4-E4B-it-GGUF, for all other turns and for /file |
| Thinking | Off for both chat models |
| Embedding model | Qwen3-Embedding-8B-GGUF |
| Embedding dimensions | 4,096 |
| Vector similarity | Cosine |
| Retrieved passages per question | Up to 10; code passages are trimmed to a 4,000-token budget |
| Chunk token budget | 768, measured with the Qwen embedding tokenizer |
| Requested chat context | 16,384 tokens for each chat model |
| Generation settings | Temperature 1.0; top_p 0.9; top_k 40 |
| OCR | Disabled |

My converted documents are cached locally, and my Qdrant library persists across restarts. The saved passage metadata includes source filename, chunk number, page, and text. My conversation messages remain in memory during a session; the optional prompt-history file records input history, not a complete answer log. The code requests model unloading and client cleanup on graceful shutdown, with cleanup errors reported separately. Each reply reports model load time, prefill time and speed, decode speed, and the number of thinking tokens.

## My speed measurements

I timed both chat models with [bench.py](bench.py) on the five Milestone 1 prompts, with and without retrieval, one run each. My machine has a 12 GB NVIDIA GPU and 32 GB of RAM, and runs Lemonade 2026.45.3 with the CUDA backend. Lemonade keeps one model of each type loaded (`max_loaded_models` = 1), so one chat model and the embedding model share the GPU. Values are medians of the five prompts.

| Configuration | Retrieval | Prefill | First answer text | Decode | Thinking tokens | Total |
|---|---|---|---|---|---|---|
| Gemma-4-E4B, thinking off | Yes | 3.1 s | 3.1 s | 98.5 tok/s | 0 | 13.4 s |
| Gemma-4-E4B, thinking off | No | 0.1 s | 0.1 s | 103.6 tok/s | 0 | 9.4 s |
| Qwen3.6-35B-A3B, thinking on, two chat models allowed | Yes | 34.9 s | 230.0 s | 14.6 tok/s | 2,778 | 302.9 s |
| Qwen3.6-35B-A3B, thinking on, two chat models allowed | No | 1.4 s | 100.6 s | 29.5 tok/s | 3,339 | 151.9 s |
| Qwen3.6-35B-A3B, thinking off | Yes | 28.0 s | 28.0 s | 50.9 tok/s | 0 | 57.2 s |
| Qwen3.6-35B-A3B, thinking off | No | 1.1 s | 1.1 s | 51.8 tok/s | 0 | 37.8 s |

Between the thinking-on and thinking-off runs I changed two things: I turned thinking off, and I lowered Lemonade's limit from two loaded chat models to one. Gemma was loaded only during the thinking-on run's first prompt, yet Qwen still decoded at about 14 tok/s on P2-P4, so I do not know why that run was slower. A repeat of the thinking-off retrieval run the next day gave 47.0 tok/s and 57.8 s. Two other settings made Qwen slower with retrieval: an 8,192-token context (14.8 tok/s, 132.7 s) and `--n-cpu-moe 20` (7.0 tok/s, 316.0 s).

With thinking off, Qwen's retrieval answers kept the same key datasheet facts as with thinking on, by my fact check; one thinking-off P2 answer wrongly allows UART TX on input-only pins. I have not scored these answers on the 1-5 scale, and I have not checked thinking off on coding questions. Each median includes the first prompt after loading, which is slower. Prefill is now about half of Qwen's retrieval answer time.

## My evidence

I used [ESP32 Series Datasheet v5.3](datasheets/ESP32.pdf), a 78-page hardware reference. The [full milestone report](../reading-and-background/milestone-data-collection/milestone-1.md) preserves the prompts, source hash, evidence locations, all ten response records, and individual score explanations. No new model responses were generated for this review.
