import json
import requests
import logging
from openai import OpenAI
from seafile_ai.utils import OpenAIInvalidException, parse_response
from seafile_ai.utils.constants import MODEL_USAGE_STATISTIC_CHANNEL_NAME
logger = logging.getLogger(__name__)


class OpenAIAPI:
    def __init__(self, llm_type, base_url=None, api_key=None, model='gpt-4o-mini', timeout=180):
        self.timeout = timeout
        self.model = model
        if llm_type == 'openai-proxy' and base_url:
            # Proxy mode
            self.mode = 'proxy'
            self.openai_proxy_url = base_url.rstrip('/') + '/api/v1/chat-completions/create'
        elif llm_type == 'openai' and api_key:
            # OpenAI SDK mode
            self.mode = 'sdk'
            client = OpenAI(
                    api_key=api_key,
                    timeout=timeout
                )
            self.model = model
            self.chat = client.chat
        elif llm_type == 'other' and api_key:
            # Other OpenAI SDK mode
            self.mode = 'sdk'
            client = OpenAI(
                    base_url=base_url,
                    api_key=api_key,
                    timeout=timeout
                )
            self.model = model
            self.chat = client.chat
        else:
            raise ValueError("Either LLM_URL or LLM_KEY must be provided")

    def init(self, data_logger):
        self.data_logger = data_logger

    def chat_completions(self, messages, context, temperature=0):
        if self.mode == 'proxy':
            # Use proxy mode
            json_data = {
                'model': self.model,
                'messages': messages,
                'temperature': temperature
            }
            response = requests.post(self.openai_proxy_url, json=json_data, timeout=self.timeout)
            data = parse_response(response)
            self.data_logger.log_data(MODEL_USAGE_STATISTIC_CHANNEL_NAME, json.dumps({
            'model': self.model,
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
                    model=self.model,
                    messages=messages,
                    temperature=temperature
                )
                usage = response.usage.to_dict() if response.usage else None
                content = response.choices[0].message.content

                self.data_logger.log_data(MODEL_USAGE_STATISTIC_CHANNEL_NAME, json.dumps({
                    'model': self.model,
                    'usage': usage,
                    'username': context.get('username'),
                    'org_id': context.get('org_id'),
                }))

                return content
            except Exception as e:
                logger.warning('openai sdk error: %s', str(e))
                logger.warning('Please check if LLM_URL, LLM_KEY and LLM_MODEL match')
                raise OpenAIInvalidException('openai sdk error: %s' % e)
