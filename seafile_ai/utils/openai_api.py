import requests
import logging

from seafile_ai.utils import parse_response

logger = logging.getLogger(__name__)


class OpenAIAPI:
    def __init__(self, openai_proxy_url, timeout=180):
        self.openai_proxy_url = openai_proxy_url.rstrip('/') + '/api/v1/chat-completions/create'
        self.timeout = timeout

    def chat_completions(self, messages, temperature=0):
        json_data = {
            'model': 'gpt-4o-mini',
            'messages': messages,
            'temperature': temperature
        }
        response = requests.post(self.openai_proxy_url, json=json_data, timeout=self.timeout)
        data = parse_response(response)
        try:
            result = data['choices'][0]['message']['content']
        except KeyError as e:
            logger.exception(e)
            result = None

        return result
