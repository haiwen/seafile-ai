import requests
import logging


logger = logging.getLogger(__name__)


def parse_response(response):
    if response.status_code >= 400 or response.status_code < 200:
        raise ConnectionError(response.status_code, response.text)
    else:
        try:
            return response.json()
        except:
            pass


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
        if 'error' in data.keys():
            logger.error('OpenAI API error: %s', data['error']['message'])
            return None

        result = data['choices'][0]['message']['content']
        return result
