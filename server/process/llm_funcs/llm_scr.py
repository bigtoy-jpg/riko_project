# OpenAI tool calling with history 
### Uses a sample function
import yaml
import json
import os
from pathlib import Path
from openai import OpenAI

CONFIG_PATH = Path(__file__).resolve().parents[3] / 'character_config.yaml'

with open(CONFIG_PATH, 'r') as f:
    char_config = yaml.safe_load(f)

client = OpenAI(api_key=char_config['OPENAI_API_KEY'])

# Constants
_history = Path(char_config['history_file'])
HISTORY_FILE = _history if _history.is_absolute() else CONFIG_PATH.parent / _history
MODEL = char_config['model']
SYSTEM_PROMPT =  [
        {
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": char_config['presets']['default']['system_prompt']  
                }
            ]
        }
    ]

# Load/save chat history
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            # A corrupt history file shouldn't break every request; start fresh.
            pass
    return list(SYSTEM_PROMPT)

MAX_HISTORY_MESSAGES = 40

def trim_history(history):
    # Keep the system prompt plus the most recent turns so the context never outgrows the model.
    if len(history) <= MAX_HISTORY_MESSAGES + 1:
        return history
    return history[:1] + history[-MAX_HISTORY_MESSAGES:]

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)



def get_riko_response_no_tool(messages):

    # Call OpenAI with system prompt + history
    response = client.responses.create(
        model=MODEL,
        input= messages,
        temperature=1,
        top_p=1,
        max_output_tokens=2048,
        stream=False,
        text={
            "format": {
            "type": "text"
            }
        },
    )

    return response


def llm_response(user_input):

    messages = load_history()

    # Append user message to memory
    messages.append({
        "role": "user",
        "content": [
            {"type": "input_text", "text": user_input}
        ]
    })


    riko_test_response = get_riko_response_no_tool(messages)


    # just append assistant message to regular response. 
    messages.append({
    "role": "assistant",
    "content": [
        {"type": "output_text", "text": riko_test_response.output_text}
    ]
    })

    save_history(trim_history(messages))
    return riko_test_response.output_text


if __name__ == "__main__":
    print('running main')