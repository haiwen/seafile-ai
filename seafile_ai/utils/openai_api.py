import requests
import logging

from seafile_ai.utils.seafile_api import parse_response


logger = logging.getLogger(__name__)


class OpenAIAPI:
    def __init__(self, openai_url, timeout=180):
        self.openai_url = openai_url.rstrip('/') + '/api/v1/chat-completions/create'
        self.timeout = timeout

    def chat_completions(self, sys_input, user_input, temperature):
        json_data = {
            'model': 'gpt-3.5-turbo-16k',
            'messages': [
                    {
                        "role": "system",
                        "content": sys_input,
                    },
                    {
                        "role": "user",
                        "content": user_input
                    }
            ],
            'temperature': temperature
        }
        response = requests.post(self.openai_url, json=json_data, timeout=self.timeout)
        data = parse_response(response)
        try:
            result = data['choices'][0]['message']['content']
        except KeyError as e:
            logger.exception(e)
            result = None

        return result
