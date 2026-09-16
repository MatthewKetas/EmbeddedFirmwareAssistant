# Authored By: Matthew Ketas
# Last Edited: 9/15/2026
# LLMs Used: Claude Opus 5

import argparse
import re
from pathlib import Path
from typing import List, NamedTuple, Union

from ollama import chat, ChatResponse

# Path and prompt definitions
DEFAULT_PROMPT = ('Design a fault-detection strategy for a temperature sensor used in an embedded monitoring system. '
                  'Provide three possible approaches and recommend one.')
VARIATION_1 = ('Design a reliable fault-detection strategy for a temperature sensor used in an embedded monitoring system. '
               'Provide three possible approaches and recommend one.')
VARIATION_2 = ('Design a reliable and fail-safe fault-detection strategy for a temperature sensor used in an embedded monitoring system. '
               'Provide three possible approaches and recommend one.')
FOLDER_PATH = Path(__file__).parent / 'Responses'
# Smaller qwen3.5 Ollama tag; downloaded with `ollama pull`.
MODEL = 'qwen3.5:2b'
REPETITIONS = 3

# Sampling options. The experiment varies temperature or prompt wording while
# keeping the other generation settings fixed.
DEFAULT_OPTIONS = {
    'temperature': 1.0,
}

TEMPERATURE_SWEEP = (0.5, 1.0, 1.5)

PROMPT_VARIATIONS = (
    ('VARIATION_1', VARIATION_1),
    ('VARIATION_2', VARIATION_2),
)


class Run(NamedTuple):
    varied: str
    repetition: int
    prompt_name: str
    prompt: str
    options: dict


def build_runs() -> List[Run]:
    """Assemble 15 runs: 3 temperatures x 3 repetitions, then 2 prompts x 3."""
    runs = []

    for temperature in TEMPERATURE_SWEEP:
        for repetition in range(1, REPETITIONS + 1):
            runs.append(Run(f'temperature = {temperature}', repetition,
                            'DEFAULT_PROMPT', DEFAULT_PROMPT,
                            {**DEFAULT_OPTIONS, 'temperature': temperature}))

    for name, prompt in PROMPT_VARIATIONS:
        for repetition in range(1, REPETITIONS + 1):
            runs.append(Run(f'prompt = {name}', repetition, name, prompt,
                            dict(DEFAULT_OPTIONS)))

    return runs


def options_line(options: dict) -> str:
    return f"`temperature={options['temperature']}`"


def response_token_count(response: ChatResponse) -> Union[int, str]:
    """Return the number of generated tokens reported by Ollama."""
    token_count = getattr(response, 'eval_count', None)
    if token_count is not None:
        return token_count

    # Keep this compatible with response-like objects returned by older
    # Ollama client versions.
    if isinstance(response, dict):
        return response.get('eval_count', 'unavailable')
    return 'unavailable'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run Ollama response experiments.')
    parser.add_argument(
        '--runs',
        help='Comma-separated original run numbers to execute, for example 4,5,10.',
    )
    parser.add_argument(
        '--no-thinking',
        action='store_true',
        help='Disable Qwen thinking mode for the selected responses.',
    )
    parser.add_argument(
        '--append-to',
        help='Append selected responses to an existing Markdown file.',
    )
    return parser.parse_args()


args = parse_args()


# Markdown file creation / management
folder = FOLDER_PATH
folder.mkdir(parents=True, exist_ok=True)
pattern = re.compile(r'Responses(\d+)\.md')
existing = [int(m.group(1)) for f in folder.glob('Responses*.md')
            if (m := pattern.fullmatch(f.name))]
next_num = max(existing, default=0) + 1
append_mode = bool(args.append_to)
if append_mode:
    output_path = folder / args.append_to
else:
    output_path = folder / f'Responses{next_num}.md'

# Generation
all_runs = build_runs()
numbered_runs = list(enumerate(all_runs, start=1))
if args.runs:
    selected_numbers = [int(number.strip()) for number in args.runs.split(',')]
    invalid_numbers = [number for number in selected_numbers
                       if number < 1 or number > len(all_runs)]
    if invalid_numbers:
        raise ValueError(f'Invalid run number(s): {invalid_numbers}')
    numbered_runs = [(number, all_runs[number - 1]) for number in selected_numbers]

thinking_enabled = not args.no_thinking
responses: List[ChatResponse] = []

with open(output_path, 'a' if append_mode else 'w', encoding='utf-8') as file:
    if append_mode:
        file.write('\n## Additional Runs\n\n')
        file.write(f'**Thinking mode:** `{thinking_enabled}`\n\n')
    else:
        file.write(f'# Responses {next_num}\n\n')
        file.write(f'**Model:** `{MODEL}`\n\n')
        file.write(f'**Thinking mode:** `{thinking_enabled}`\n\n')
        file.write(f'**Fixed sampling options:** {options_line(DEFAULT_OPTIONS)}\n\n')

    # Index table so the whole run plan is visible without scrolling
    if not append_mode:
        file.write('| Original Run | Repetition | Varied | temperature | Prompt |\n')
        file.write('| --- | --- | --- | --- | --- |\n')
        for original_number, run in numbered_runs:
            file.write(f"| {original_number} | {run.repetition} | {run.varied} | "
                       f"{run.options['temperature']} | {run.prompt_name} |\n")
    file.write('\n---\n\n')

    for original_number, run in numbered_runs:
        response: ChatResponse = chat(
            model=MODEL,
            think=thinking_enabled,
            messages=[
                {
                    'role': 'user',
                    'content': run.prompt,
                }],
            options=run.options,
        )
        responses.append(response)
        token_count = response_token_count(response)

        file.write(f'## Run {original_number} — {run.varied}, repetition {run.repetition}\n\n')
        file.write(f'{options_line(run.options)} — prompt: **{run.prompt_name}** — '
                   f'**response tokens: {token_count}**\n\n')
        file.write(f'> {run.prompt}\n\n')
        file.write(response.message.content.strip() + '\n\n')
        file.write('---\n\n')
        file.flush()

        print(f'[{original_number}] {run.varied}, repetition {run.repetition}, '
              f'{token_count} tokens — written to {output_path}')

print(f'\nDone. {len(numbered_runs)} responses saved to {output_path}')
