from ollama import chat, ChatResponse

PROMPT = ('A series RC circuit contains a 10 kΩ resistor and a 100 '
               'μF capacitor. A 5.0 V step input is applied at (t=0), with '
               'the capacitor initially discharged.'
               'The measured capacitor voltage is shown on the right'
               'Analyze whether these measurements are consistent '
               'with the expected time constant of the circuit.'
               'Your response must:'
               'Calculate the theoretical time constant.'
               ' State the expected capacitor voltage equation.'
               'Estimate the time constant indicated by the measurements.'
               'Compare the measured and theoretical behavior.'
               'Conclude whether the measurements are consistent with '
               'the circuit model, using a ±10% tolerance.'
               'Show the principal calculations and state any assumptions.'
          'Time [s] Measured [V] '
          '0.0 0.02'
          '0.5 1.94'
          '1.0 3.18'
          '2.0 4.28'
          '3.0 4.75')
print(PROMPT)

response: ChatResponse = chat(
  model='qwen3.5',
  messages=[
  {
    'role': 'user',
    'content': PROMPT,
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
