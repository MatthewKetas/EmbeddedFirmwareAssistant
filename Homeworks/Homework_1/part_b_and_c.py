# Authored By: Matthew Ketas
# Last Edited: 9/14/2026
# LLMs Used: Claude Opus 5

import re
from pathlib import Path
from typing import NamedTuple

from ollama import chat, ChatResponse

# Path and prompt definitions
DEFAULT_PROMPT = ('Design a fault-detection strategy for a temperature sensor used in an embedded monitoring system. '
                  'Provide three possible approaches and recommend one.')
VARIATION_1 = ('Design a reliable fault-detection strategy for a temperature sensor used in an embedded monitoring system. '
               'Provide three possible approaches and recommend one.')
VARIATION_2 = ('Design a reliable and fail-safe fault-detection strategy for a temperature sensor used in an embedded monitoring system. '
               'Provide three possible approaches and recommend one.')
VARIATION_3 = ('Design a reliable fault-detection strategy for a temperature sensor used in an embedded monitoring system. '
               'Provide three possible approaches and recommend one that matches industry standards.')
VARIATION_4 = ('Design a fault-detection strategy for a temperature sensor used in a vital embedded monitoring system. '
               'Provide three possible approaches and recommend one.')
VARIATION_5 = ('Design a fault-detection strategy for a high-precision temperature sensor used in an embedded monitoring system. '
               'Provide three possible approaches and recommend one.')

FOLDER_PATH = Path(__file__).parent / 'Responses'
MODEL = 'qwen3.5'

# Baseline sampling options. Each parameter sweep below varies one of these
# and holds the other two at these values.
DEFAULT_OPTIONS = {
    'temperature': 1.0,
    'top_k': 40,
    'top_p': 0.9,
}

TEMPERATURE_SWEEP = (0.5, 1.0, 1.5)
TOP_K_SWEEP = (20, 40, 60)
TOP_P_SWEEP = (0.6, 0.75, 0.9)

PROMPT_VARIATIONS = (
    ('VARIATION_1', VARIATION_1),
    ('VARIATION_2', VARIATION_2),
    ('VARIATION_3', VARIATION_3),
    ('VARIATION_4', VARIATION_4),
    ('VARIATION_5', VARIATION_5),
)


class Run(NamedTuple):
    varied: str          # what this run is testing
    prompt_name: str
    prompt: str
    options: dict


def build_runs() -> list[Run]:
    """Assemble the 15-run plan: 10 parameter runs, then 5 prompt runs."""
    runs = [Run('baseline', 'DEFAULT_PROMPT', DEFAULT_PROMPT, dict(DEFAULT_OPTIONS))]

    for temperature in TEMPERATURE_SWEEP:
        runs.append(Run(f'temperature = {temperature}', 'DEFAULT_PROMPT', DEFAULT_PROMPT,
                        {**DEFAULT_OPTIONS, 'temperature': temperature}))

    for top_k in TOP_K_SWEEP:
        runs.append(Run(f'top_k = {top_k}', 'DEFAULT_PROMPT', DEFAULT_PROMPT,
                        {**DEFAULT_OPTIONS, 'top_k': top_k}))

    for top_p in TOP_P_SWEEP:
        runs.append(Run(f'top_p = {top_p}', 'DEFAULT_PROMPT', DEFAULT_PROMPT,
                        {**DEFAULT_OPTIONS, 'top_p': top_p}))

    for name, prompt in PROMPT_VARIATIONS:
        runs.append(Run(f'prompt = {name}', name, prompt, dict(DEFAULT_OPTIONS)))

    return runs


def options_line(options: dict) -> str:
    return (f"`temperature={options['temperature']}` "
            f"`top_k={options['top_k']}` "
            f"`top_p={options['top_p']}`")


# Markdown file creation / management
folder = FOLDER_PATH
folder.mkdir(parents=True, exist_ok=True)
pattern = re.compile(r'Responses(\d+)\.md')
existing = [int(m.group(1)) for f in folder.glob('Responses*.md')
            if (m := pattern.fullmatch(f.name))]
next_num = max(existing, default=0) + 1
output_path = folder / f'Responses{next_num}.md'

# Generation
runs = build_runs()
responses: list[ChatResponse] = []

with open(output_path, 'w', encoding='utf-8') as file:
    file.write(f'# Responses {next_num}\n\n')
    file.write(f'**Model:** `{MODEL}`\n\n')
    file.write(f'**Baseline options:** {options_line(DEFAULT_OPTIONS)}\n\n')

    # Index table so the whole run plan is visible without scrolling
    file.write('| Run | Varied | temperature | top_k | top_p | Prompt |\n')
    file.write('| --- | --- | --- | --- | --- | --- |\n')
    for i, run in enumerate(runs, start=1):
        file.write(f"| {i} | {run.varied} | {run.options['temperature']} | "
                   f"{run.options['top_k']} | {run.options['top_p']} | {run.prompt_name} |\n")
    file.write('\n---\n\n')

    for i, run in enumerate(runs, start=1):
        response: ChatResponse = chat(
            model=MODEL,
            messages=[
                {
                    'role': 'user',
                    'content': run.prompt,
                }],
            options=run.options,
        )
        responses.append(response)

        file.write(f'## Run {i} — {run.varied}\n\n')
        file.write(f'{options_line(run.options)} — prompt: **{run.prompt_name}**\n\n')
        file.write(f'> {run.prompt}\n\n')
        file.write(response.message.content.strip() + '\n\n')
        file.write('---\n\n')
        file.flush()

        print(f'[{i}/{len(runs)}] {run.varied} — written to {output_path}')

print(f'\nDone. {len(runs)} responses saved to {output_path}')