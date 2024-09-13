import requests
import logging

from seafile_ai.utils.utils import parse_response

logger = logging.getLogger(__name__)


class AliyunLLMAPI:
    def __init__(self, server_url, secret_key, timeout=180):
        self.server_url = server_url.rstrip('/') + '/compatible-mode/v1/chat/completions'
        self.timeout = timeout
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + secret_key
        }

    def chat_completions(self, messages, temperature=0):
        json_data = {
            'model': 'qwen-long',
            'messages': messages,
            'temperature': temperature
        }
        response = requests.post(self.server_url, json=json_data, headers=self.headers, timeout=self.timeout)
        data = parse_response(response)
        result = data['choices'][0]['message']['content']

        return result
