from ollama import chat, ChatResponse

response: ChatResponse = chat(
  model='qwen3.5',
  messages=[
  {
    'role': 'user',
    'content': 'Why is the sky blue?',
  }],
  options={
    'temperature':  1.0,
    'top-k' : '40',
    'top-p': '0.9'
  }
)
print(response['message']['content'])
# or access fields directly from the response object
print(response.message.content)
