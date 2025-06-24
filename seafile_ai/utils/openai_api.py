import json
import requests
import logging

from seafile_ai.utils import OpenAIInvalidException, parse_response
from seafile_ai.utils.constants import MODEL_USAGE_STATISTIC_CHANNEL_NAME
logger = logging.getLogger(__name__)


class OpenAIAPI:
    def __init__(self, openai_proxy_url=None, api_key=None, timeout=180):
        self.timeout = timeout        
        if openai_proxy_url:
            # Proxy mode
            self.mode = 'proxy'
            self.openai_proxy_url = openai_proxy_url.rstrip('/') + '/api/v1/chat-completions/create'
        elif api_key:
            # OpenAI SDK mode
            self.mode = 'sdk'
            import openai
            client = openai.OpenAI(api_key=api_key, timeout=timeout)

            # Cache `OpenAI.chat` properties in `__init__` to avoid registering atexit Apps after shutdown in the Docker environment when first-time calling `OpenAI.chat.competion` on function `chat_completions`.
            self.chat = client.chat
        else:
            raise ValueError("Either openai_proxy_url or api_key must be provided")

    def init(self, data_logger):
        self.data_logger = data_logger

    def chat_completions(self, messages, context, temperature=0, model='gpt-4o-mini'):
        if self.mode == 'proxy':
            # Use proxy mode
            json_data = {
                'model': model,
                'messages': messages,
                'temperature': temperature
            }
            response = requests.post(self.openai_proxy_url, json=json_data, timeout=self.timeout)
            data = parse_response(response)
            self.data_logger.log_data(MODEL_USAGE_STATISTIC_CHANNEL_NAME, json.dumps({
            'model': data.get('model'),
            'usage': data.get('usage'),
            'username': context.get('username'),
            'org_id': context.get('org_id')
        }))

            try:
                result = data['choices'][0]['message']['content']
            except Exception as e:
                logger.warning('openai parse data:%s, error', json.dumps(data))
                raise OpenAIInvalidException('openai parse data error: %s' % e)
            return result
        
        elif self.mode == 'sdk':
            # Use OpenAI SDK mode
            try:
                response = self.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature
                )
                self.data_logger.log_data(MODEL_USAGE_STATISTIC_CHANNEL_NAME, json.dumps({
                'model': response.get('model'),
                'usage': response.get('usage'),
                'username': context.get('username'),
                'org_id': context.get('org_id'),
                'assistant_uuid': context.get('assistant_uuid'),
            }))
                return response.choices[0].message.content
            except Exception as e:
                logger.warning('openai sdk error: %s', str(e))
                raise OpenAIInvalidException('openai sdk error: %s' % e)
