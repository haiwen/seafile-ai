import json
import logging

import litellm

from seafile_ai.utils import LLMChatCompletionException
from seafile_ai.utils.constants import MODEL_USAGE_STATISTIC_CHANNEL_NAME

logger = logging.getLogger(__name__)


class LLMAPI:
    def __init__(self, data_logger, llm_type='openai', base_url=None, api_key=None, model='gpt-4o-mini', timeout=180):
        self.data_logger = data_logger
        self.timeout = timeout
        if llm_type == 'other':
            llm_type = 'hosted_vllm'
        if llm_type in ('other', 'hosted_vllm') and not base_url:
            raise ValueError(f'The llm_url has to set in llm_type = {llm_type}')
        self.llm_type = llm_type
        self.model = f'{llm_type}/{model}' if llm_type else model
        self.model_id = model
        self.base_url = base_url
        self.api_key = api_key

    def completion(self, **kwargs):
        if 'model' in kwargs:
            kwargs.pop('model')
        if 'base_url' in kwargs:
            kwargs.pop('base_url')
        if 'api_key' in kwargs:
            kwargs.pop('api_key')

        context = kwargs.pop('context', {})
        try:
            response = litellm.completion(
                model=self.model,
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
                **kwargs,
            )
        except Exception as error:
            logger.error('Chat completion error: %s', str(error))
            raise LLMChatCompletionException('LLM chat completion error: %s' % error)

        self._logger_usage_from_response(response, context)
        return response

    def run(self, messages, context=None, **kwargs):
        context = context or {}
        assert isinstance(messages, (list, tuple))

        kwargs['messages'] = messages
        if 'temperature' not in kwargs:
            kwargs['temperature'] = 0
        if kwargs.get('json_mode'):
            kwargs.pop('json_mode')
            response_format = kwargs.get('response_format', {})
            response_format.update({'type': 'json_object'})
            kwargs['response_format'] = response_format

        response = self.completion(context=context, **kwargs)
        return response.choices[0].message.to_dict() if 'tools' in kwargs else response.choices[0].message.content

    def logger_usage(self, token_usage, context, model=None):
        try:
            self.data_logger.log_data(MODEL_USAGE_STATISTIC_CHANNEL_NAME, json.dumps({
                'model': self.model_id if not model else model,
                'usage': {
                    'prompt_tokens': token_usage.get('input_tokens', 0),
                    'completion_tokens': token_usage.get('output_tokens', 0),
                    'total_tokens': token_usage.get('total_tokens', 0),
                },
                'username': context.get('username'),
                'org_id': context.get('org_id'),
            }))
        except Exception as error:
            logger.warning('Chat completed but failure to log usages: %s', error)

    def _logger_usage_from_response(self, response, context, model=None):
        try:
            self.logger_usage({
                'input_tokens': response.usage.prompt_tokens,
                'output_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens,
            }, context, model)
        except Exception:
            pass
