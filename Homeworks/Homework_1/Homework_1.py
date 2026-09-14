import re
from pathlib import Path
from ollama import chat, ChatResponse

# Path and prompt definitions
DEFAULT_PROMPT = ('Design a fault-detection strategy for a temperature sensor used in an embedded monitoring system. '
                  'Provide three possible approaches and recommend one.')
FOLDER_PATH = './Responses'
MODEL = 'qwen3.5'
N_RESPONSES = 10
OPTIONS = {
    'temperature': 1.0,
    'top_k': 40,
    'top_p': 0.9,
}

# Markdown file creation / management
folder = Path(FOLDER_PATH)
folder.mkdir(parents=True, exist_ok=True)
pattern = re.compile(r'Responses(\d+)\.md')
existing = [int(m.group(1)) for f in folder.glob('Responses*.md')
            if (m := pattern.fullmatch(f.name))]
next_num = max(existing, default=0) + 1
output_path = folder / f'Responses{next_num}.md'

# Generation
responses: list[ChatResponse] = []

with open(output_path, 'w', encoding='utf-8') as file:
    file.write(f'# Responses {next_num}\n\n')
    file.write(f'**Model:** `{MODEL}`\n\n')
    file.write(f'**Options:** {OPTIONS}\n\n')
    file.write(f'**Prompt:** {DEFAULT_PROMPT}\n\n')
    file.write('---\n\n')

    for i in range(1, N_RESPONSES + 1):
        response: ChatResponse = chat(
            model=MODEL,
            messages=[
                {
                    'role': 'user',
                    'content': DEFAULT_PROMPT,
                }],
            options=OPTIONS,
        )
        responses.append(response)

        file.write(f'## Response {i}\n\n')
        file.write(response.message.content.strip() + '\n\n')
        file.write('---\n\n')
        file.flush()

        print(f'[{i}/{N_RESPONSES}] written to {output_path}')

print(f'\nDone. {N_RESPONSES} responses saved to {output_path}')