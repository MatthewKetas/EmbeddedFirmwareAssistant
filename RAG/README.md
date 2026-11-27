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
| Retrieved passages per question | Up to 10 distinct passages, ranked by vector similarity merged with keyword (BM25) ranking; code passages are trimmed to a 4,000-token budget |
| Indexing | Front matter (contents, lists of tables and figures, revision history, back-matter links) is skipped; generic headings such as "Feature List" carry their section name |
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

Between the thinking-on and thinking-off runs I changed two things: I turned thinking off, and I lowered Lemonade's limit from two loaded chat models to one. Gemma was loaded only during the thinking-on run's first prompt, yet Qwen still decoded at about 14 tok/s on P2-P4. Thinking alone does not explain that: in the coding test below, Qwen decoded at about 57 tok/s with thinking on, although with a much shorter prompt. I do not know the cause. A repeat of the thinking-off retrieval run the next day gave 47.0 tok/s and 57.8 s. Two other settings made Qwen slower with retrieval: an 8,192-token context (14.8 tok/s, 132.7 s) and `--n-cpu-moe 20` (7.0 tok/s, 316.0 s).

With thinking off, Qwen's retrieval answers kept the same key datasheet facts as with thinking on, by my fact check; one thinking-off P2 answer wrongly allows UART TX on input-only pins. I have not scored these answers on the 1-5 scale, and I have not checked thinking off on coding questions. Each median includes the first prompt after loading, which is slower. Prefill is now about half of Qwen's retrieval answer time.

I also tried larger prompt batches for Qwen (`-b 2048 -ub 2048`), since its prefill of 3-5k-token prompts takes 15-38 s with part of the model in system RAM. Run back to back at normal speed, one first run per prompt, the median prefill went from 21.2 s to 19.2 s, but P3 was slower (24.2 s against 28.5 s), P3 itself varied from 18.6 s to 28.5 s between two runs with the larger batches, and decode was slightly slower (48.9 against 51.4 tok/s); the median total was 56.9 s against 56.5 s. The difference is within run-to-run noise, so I kept Lemonade's default batch sizes.

## My coding test with thinking on and off

I checked whether thinking off costs Qwen correctness on code with the Critter task in [pass@k](../pass@k/run.py): each sample implements three C functions, which hidden tests grade in four groups. All samples below finished on their own (`finish_reason` "stop"). A first thinking-on run at the default 4,096-token cap was cut off in all five samples, so the thinking-on runs below allow 12,288 and 14,336 tokens.

| Thinking | Samples | Compiled | Passed all four groups | pass@1 | Median time per sample | Median tokens per sample |
|---|---|---|---|---|---|---|
| Off | 25 (5 + 20) | 22 | 15 | 0.60 | 30.2 s | 1,580 |
| On | 25 (5 + 20) | 25 | 18 | 0.72 | 170.9 s | 9,661 |

The times and token counts come from the two 5-sample runs. With a uniform prior, the estimated success rates are 0.70 with thinking on and 0.59 with thinking off; the probability that thinking on is better is 0.81, and the 95% interval for the difference is -0.14 to +0.36. The failures differ: with thinking off, three samples did not compile (the one I checked calls `qsort` without including `stdlib.h`) and the forecast group failed most often; with thinking on, every sample compiled and the summary group failed most often. I kept thinking off for the code model because it answers about six times faster for a likely gain of about ten points in correctness.

## My model comparison

I compared six chat models from Lemonade's catalog on the same machine, with thinking off. Speed and token counts are medians of the five Milestone 1 prompts with retrieval. Critter pass@1 comes from the pass@k test above.

| Role | Model | Decode | Total per answer | Critter pass@1 |
|---|---|---|---|---|
| Lexical (chosen) | Gemma-4-E4B-it | 98.5 tok/s | 13.4 s | not tested |
| Lexical | Qwen3-4B-Instruct-2507 | 97.6 tok/s | 20.3 s | not tested |
| Code (chosen) | Qwen3.6-35B-A3B | 50.9 tok/s | 57.2 s | 0.60 (25 samples) |
| Code | Qwen3-Coder-30B-A3B-Instruct | 52.7 tok/s | 41.0 s | 0.00 (20 samples) |
| Code | Gemma-4-26B-A4B-it-MTP | 12.5 tok/s | 78.1 s | 0.20 (20 samples) |
| Code | Gemma-4-26B-A4B-it | 12.5 tok/s | 88.1 s | not tested |

Qwen3-Coder and Gemma 26B failed Critter on documented requirements: they called the sensor more than the 64-sample capacity, Qwen3-Coder also miscounted the total rejected readings and accepted an infinite high limit, and some samples omitted `#include <stdlib.h>` for `qsort`. The MTP version of Gemma 26B decoded no faster than the plain version, so Lemonade either did not use its multi-token prediction or gained nothing from it on this GPU.

### Datasheet fact check

I checked all 77 saved answers against key facts that I located in the datasheet, for example the 4,096-bit RSA limit (p.32), the 40 mA VDD_SDIO LDO limit (p.51) and I2C Fast mode at 400 Kbit/s (p.37). A script found the facts each answer states and the wrong claims it makes; I read every flagged error in context and removed three false positives. This is a checklist, not my 1-5 rubric, and most configurations have one run per prompt.

| Model | With retrieval: key facts | With retrieval: errors | Without retrieval: key facts | Without retrieval: errors |
|---|---|---|---|---|
| Gemma-4-E4B-it | 21/26 (81%) | 0 | 5/26 (19%) | 1 |
| Qwen3-4B-Instruct-2507 | 23/26 (88%) | 1 | 7/26 (27%) | 6 |
| Qwen3.6-35B-A3B, thinking off | 93/107 (87%) | 1 | 8/26 (31%) | 4 |
| Qwen3.6-35B-A3B, thinking on | 23/26 (88%) | 1 | 11/26 (42%) | 4 |
| Qwen3-Coder-30B-A3B-Instruct | 25/26 (96%) | 1 | 9/26 (35%) | 2 |
| Gemma-4-26B-A4B-it, with and without MTP | 45/55 (82%) | 2 | not run | not run |

Without retrieval, every model invented datasheet values, such as a 200 mA or 1.8 mA LDO limit, a 2.7-2.95 V minimum supply, or eFuse names the datasheet does not contain. With retrieval, the models were close, so I chose by speed. Most remaining gaps were retrieval misses shared by every model: no answer gave the 50 µs power-up time in Table 2-4 (p.19), only one listed the four 64-bit general-purpose timers (p.31), and six answers said the datasheet does not confirm 400 Kbit/s I2C although p.37 states it.

## My retrieval improvements

I checked where the passages that answer each Milestone 1 prompt rank with [retrieval_check.py](retrieval_check.py), which needs only the embedding model. Three problems kept answers from the facts above:

- **Duplicate chunks.** The library held the datasheet as both `ESP32.pdf` and `esp32.pdf`, because on Windows `/add esp32.pdf` opens `ESP32.pdf` but the typed name became the source. Five of the ten chunks sent per question were duplicates. `/add` now uses the name on disk and replaces copies stored under other case, and retrieval skips identical chunks.
- **Front matter.** The contents, lists of tables and figures, revision history and back-matter links matched almost any question and took up to seven of the ten slots. They are no longer indexed (22 of 218 ESP32 chunks).
- **Missing section names and exact terms.** A chunk headed only "Feature List" never mentioned I2C, and embeddings ranked passages low even when they repeated the question's exact terms, such as "400 Kbit/s". Generic headings now carry their section, and a keyword (BM25) ranking is merged with the vector ranking.

| Passage (ESP32.pdf page) | Rank before | Rank after |
|---|---|---|
| P1: RSA 4,096-bit limit (p.32) | 2 | 1 |
| P2: I2C Fast mode 400 Kbit/s (p.37) | 37 | 8 |
| P3: power-up time tSTBL 50 µs (p.19) | outside the top 10 | 6 |
| P5: four general-purpose timers (p.31) | 11 | 2 |
| P2: UART pins via the GPIO Matrix (p.37) | not in the top 50 | 30 |

Searching each sentence of the question separately made ranking worse, because the instruction sentences shared by every prompt pulled the same generic chunks to the top, so I removed it. The keyword ranking added about 0.1 s per question.

In a bench run with the ESP32 board selected, both chosen models stated the three facts that no earlier configuration had covered: the 400 Kbit/s I2C mode, the 50 µs power-up time and the four general-purpose timers. Gemma-4-E4B took a median 13.8 s per answer and Qwen3.6-35B-A3B 48.2 s. I read these ten answers myself rather than with the fact-check script. They still contained errors that retrieval does not explain: Gemma labelled the SPI flash boot setting as SDIO download boot, and Qwen gave U0TXD as GPIO3 instead of GPIO1 and called U0TXD a strapping pin.

## My stricter answer instruction

Some remaining errors came from the models filling gaps from memory: when the pin table was not retrieved, Qwen wrote that U0TXD is GPIO3 "in typical ESP32 pinouts" (it is GPIO1). The retrieval prompt now requires every stated value, pin number, register or name to appear in the context and asks the model to say what is missing. I also stopped indexing repeated table cells: Docling repeated a merged cell once per column, so one pin-table row held the same description nine times.

I compared a bench run with the new instruction against the run before it, one run per model with the ESP32 board selected, by reading the answers. Errors fell from five to two. Qwen stopped inventing the U0TXD pin and instead said the mapping was not in the context; Gemma stopped mislabelling the SPI flash boot setting; Qwen described the 6 Ω resistor correctly as the internal path from VDD3P3_RTC. The new errors were Gemma listing VDDA as one of the three digital power domains and Qwen stating that the datasheet does not describe secure boot, which it lists as a feature on a page that was not retrieved. Facts that were in the context, such as the 400 Kbit/s I2C mode and the 50 µs power-up time, were still stated. Qwen decoded at only 15 tok/s in this run, so I do not use it as a speed measurement.

## My three-run check

To see whether the results hold beyond one run, I ran both chosen models on all five prompts three times, with and without retrieval, using the ESP32 board and the stricter instruction (60 answers). I checked the answers with [fact_check.py](fact_check.py) and confirmed each flagged error by hand; seven of the first thirteen flags were false and I tightened the patterns.

| Model | With retrieval: key facts | With retrieval: errors | Without retrieval: key facts | Without retrieval: errors |
|---|---|---|---|---|
| Gemma-4-E4B-it | 59/78 (76%) | 0 | 16/78 (21%) | 2, plus 1 unclear |
| Qwen3.6-35B-A3B | 74/78 (95%) | 0 | 31/78 (40%) | 2 |

Neither model made a confirmed error in its 15 answers with retrieval. Gemma stated fewer key facts than Qwen because its answers became shorter under the stricter instruction: it left out details such as the 1 ms strapping hold time, the 6 Ω and 2 kΩ resistors and the number of strapping pins, each in at most three of its fifteen answers, rather than whole topics. Without retrieval, one of Qwen's answers was only "No response: Text completion blocked by content filters", which the model generated itself; nothing in this pipeline filters content.

With the screen kept on, Qwen decoded at 48-55 tok/s in each prompt's first run, so I suspect the earlier 15 tok/s runs came from low-power behaviour when the screen turned off. In the second and third runs of a prompt, llama.cpp reused the cached prompt, so their prefill times are not real measurements; first runs took 1.4-3.2 s of prefill and 9-14 s in total for Gemma, and 22-35 s of prefill and 58-82 s in total for Qwen.

## My answer rules

Every chat request now starts with a short system prompt (`ANSWER_RULES` in [rag.py](rag.py)): lead with the direct answer, cover every part of the question with the values, limits and pin cautions that bear on it, take facts only from the context when there is one, and label design inferences. Qwen also gets one code-review rule: findings most severe first, each with file, line and a fix. I compared two versions against the three-run check above, each with three runs of the five prompts on the ESP32 board (60 answers per version):

| Version | Gemma with retrieval: key facts | Gemma: median answer tokens | Qwen with retrieval: key facts | Qwen: median answer tokens | Errors with retrieval |
|---|---|---|---|---|---|
| No rules (three-run check) | 59/78 (76%) | 836 | 74/78 (95%) | 1660 | 0 |
| First rules: "briefly", under about 350 words | 52/78 (67%) | 511 | 67/78 (86%) | 672 | 0 |
| Final rules: cover every part, no length limit | 62/78 (79%) | 827 | 67/78 (86%) | 1044 | 0 |

The first version shortened answers by 40-60% but dropped facts the questions need, such as the 2.3-3.6 V supply range, the strapping and input-only pins and the LDO's 40 mA limit, so I replaced it. With the final rules, Gemma, which answers datasheet questions, states as many key facts as before at the same length. Qwen's datasheet answers are 37% shorter, about 13 s less at 50 tok/s, but state fewer key facts; that matters only if Qwen answers datasheet questions again. I confirmed every flagged error by hand: none with retrieval in any version. Without retrieval, Qwen made three real errors with the final rules (an RSA limit of 3072 bits instead of 4096, and LDO limits of 300 mA and 200 mA instead of 40 mA).

Qwen ran at about 15 tok/s during the first-rules run even with the screen timeout set to two hours, so the slow state is not only caused by the screen turning off.

## My code-review check

To test the rules on Qwen's actual job, I wrote four short C files with two planted bugs each, the more severe first: a ring buffer that writes one byte past its end and never checks for full, an ADC average whose `uint16_t` sum overflows and that divides by a count that may be zero, an I2C read that copies `len` bytes into a 4-byte buffer and ignores the write result, and a timer whose ISR flag is not `volatile` and whose elapsed time returns 0 on wrap. [review_bench.py](review_bench.py) sends each file to Qwen as a retrieved code snippet, three times with the rules and three without. I confirmed every match by hand and tightened the patterns that matched wrongly.

| Rules | Planted bugs found | Median answer tokens | Median time |
|---|---|---|---|
| Gemma's rules plus a code-review rule | 10/24 | 280 | 5.8 s |
| None | 17/24, plus 2 unclear | 833 | 15.0 s |

With the rules, Qwen opened four of nine weak reviews with "No bugs found", called the overflowing `uint16_t` sum sufficient, and found neither I2C bug in any run; it seems to read "say what the context lacks" as a reason to stop. Without them it found the ring-buffer overrun and both ADC bugs every time, though never the missing full check. Gemma keeps the rules.

Without any rules Qwen found the missing full check in only one of six reviews, so I gave it a short review checklist instead (`REVIEW_CHECKLIST` in [rag.py](rag.py)): bounds including full and empty buffers, integer overflow and division by zero, ignored return values, data shared with interrupts, and counter wrap-around, then "report every real bug, most severe first" and "only report a bug you have traced through the code". Because the checklist names the categories of the four files' bugs, I added two held-out files whose bugs it does not name: a function returning a pointer to its local buffer, a `switch` case missing its `break`, an `&`/`==` precedence error, and a `uint8_t` loop counter that cannot reach a count above 255 (the last is partly a truncation bug). I ran both prompts three times on all six files and confirmed every match by hand:

| Qwen system prompt | Checked files: bugs found | Held-out files: bugs found | Median answer tokens (checked / held out) |
|---|---|---|---|
| None | 15/24 | 9/12 | 655 / 238 |
| Review checklist | 23/24 | 12/12 | 1365 / 838 |

The checklist found the missing full check in all three runs and did as well on the held-out bugs, including the `uint8_t` counter that no review without it noticed, so the gain is not only on the bugs it lists. The cost is length: about 10-12 s more per review at 58 tok/s. Without a prompt, one review was 28 tokens and found nothing, and one called the `i2c_write` usage correct. The checklist put the more severe bug first less often on the held-out files (2 of 6 against 3 of 6), mostly by listing the missing `break` before the dangling pointer. The script counts only planted bugs, so I have not checked whether the longer reviews also contain invented findings. Qwen now gets the checklist; Gemma keeps the answer rules.

## My code retrieval check

The review check sends whole files, so it does not test what `/code` depends on: finding the right snippets in a repository. For that I wrote a made-up motor controller in [code_cases/motor_fw](code_cases/motor_fw), 13 files and about 900 lines with its own hardware layer, so no answer can come from memory of a real SDK, and eight questions whose answers sit in known lines (the PWM pin and frequency, what happens when the UART buffer is full, the sensor retries, the stall condition, the watchdog, the shutdown voltage, a failed configuration CRC, and the control period). [code_check.py](code_check.py) indexes it into its own collection, shows where the chunks holding each answer rank and whether they fit the 4,000-token code budget with and without line numbers, and with `--answer` scores Qwen's answers on key facts and on citing a line in an answer chunk.

The first run showed that a function's explanatory comment went into the chunk before it, because chunks split at function boundaries. The comments and `#define`s ranked 1-4, but four of the functions ranked 30th or lower. I now keep a comment directly above a function, with no blank line, in the function's chunk:

| Function | Rank before | Rank after |
|---|---|---|
| `uart_rx_isr` (buffer full) | below 30 | 2 |
| `env_sensor_read` (retries) | below 30 | 2 |
| `motor_check_protection` (stall) | 30 | 1 |
| `watchdog_service` (feeding) | 30 | 1 |

Every answer chunk now ranks in the top 3, and the repository makes 61 chunks instead of 77. The budget cut in once: on the retries question, 9 of 10 chunks fit with line numbers against 10 without, and both answer chunks were still sent. Prompts grew from about 1,900-2,700 tokens to 2,900-4,200 because function chunks now carry their comments.

One answer per question, checked by hand:

| Chunking | Key facts stated | Answers citing an answer line | Answer length |
|---|---|---|---|
| Comments split off | 17/17 | 6/8 | 46-316 tokens |
| Comments with their function | 16/17 | 8/8 | 60-283 tokens |

The one miss is real: asked how quickly the board shuts down, Qwen said the interval between battery readings "is not in the context", though the chunk it cited begins with "Called once a second". Five of the misses my patterns reported were correct answers written as the code spells them ("2000u milliseconds", "20,000 Hz", "pin number 18"); I fixed the patterns and kept those answers as tests. Any repository already indexed with `/code` keeps its old chunks until it is indexed again.

Asked in `rag.py` to "Review motor.c for bugs", similarity retrieval sent chunks from four other files and missed `motor_control_step` and `motor_fault`; Qwen then reported three bugs in the code it was never sent, such as an integral clamp that "only handles positive windup", though `motor.c` clamps both ways. A code file named in a question now comes whole and first, in line order, ahead of the usual top 10, and the code budget trims the end. With that, both functions were sent and Qwen's review of `motor.c`, which has no planted bugs, found none, with each check correct against the file. The named file plus the usual 10 is the largest code prompt so far, and line numbers cost 2 of its 19 chunks; neither answer function was among them. The review grew from 541 to 1,581 tokens as Qwen worked through every function. The other eight questions kept every key fact in this run (18 of 18, with C4's values written after their macro names, "`STALL_TIME_MS` is 500u"), and every answer cited a line in an answer chunk. Over three runs of the first eight questions, 51 of 51 key facts were stated and all 24 answers cited an answer line.

## My chat history and reply length

Asked to review `motor.c` straight after a question on the stall check, Qwen ended its review by answering the stall question again. `rag.py` sends the conversation with each question, so I now send only the last three exchanges, and the retrieval prompt says to answer only the question at its end, with earlier messages as background for follow-ups. [code_check.py](code_check.py) checks it with C10, the same review asked after the same question, and C11, a follow-up ("And what happens to the motor when that fault trips?") that only makes sense with the earlier question.

Two problems showed up in those runs. First, reviews of a whole file ran away: one review of `motor.c` reasoned aloud for 5,351 tokens, and another walked the file line by line until it filled Qwen's 16,384-token context (12,020 tokens, 249 s). Replies are now capped at the 2,048 tokens `RAG_REPLY_TOKENS` already reserved, with a note when one is cut; a runaway now stops after about 60 s. I also changed the checklist from "only report a bug you have traced" to "trace each suspected bug, but write only the findings, not the tracing". That did not stop the reviews: in the next run both still reached the cap, one of them repeating the same four lines. It did not cost the other answers any facts (all 17 of C1-C8 when read by hand), though they became shorter. Because the review cut off while looping, C10 passed the "does not answer the earlier question" check in one of two runs, and I could not tell from the other.

Second, the follow-up's own words do not find `motor_fault`, which has no comment and shares few words with a question about faults, so it ranked below 30 and Qwen answered from the earlier reply, citing lines that do not exist (`motor.c:131` in a 129-line file). I tried searching follow-ups together with the previous question; `motor_fault` still ranked below 30, so I removed it rather than change retrieval for every question containing "it" or "that". Three more of the misses my patterns reported were correct answers ("defined as 18", "dropped and counted", "saves it to non-volatile storage"), now kept as tests.

## My evidence

I used [ESP32 Series Datasheet v5.3](datasheets/ESP32.pdf), a 78-page hardware reference. The [full milestone report](../reading-and-background/milestone-data-collection/milestone-1.md) preserves the prompts, source hash, evidence locations, all ten response records, and individual score explanations. No new model responses were generated for this review.
