import requests
import logging

from seafile_ai.utils.utils import parse_response

logger = logging.getLogger(__name__)


class OpenAIAPI:
    def __init__(self, server_url, timeout=180):
        self.server_url = server_url.rstrip('/') + '/api/v1/chat-completions/create'
        self.timeout = timeout

    def chat_completions(self, messages, temperature=0):
        json_data = {
            'model': 'gpt-4o-mini',
            'messages': messages,
            'temperature': temperature
        }
        response = requests.post(self.server_url, json=json_data, timeout=self.timeout)
        data = parse_response(response)
        result = data['choices'][0]['message']['content']

        return result
