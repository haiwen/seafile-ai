import logging
import re

import litellm

from seafile_ai.utils import LLMChatCompletionException
from seafile_ai.utils.llm_api import BasicLLMAPI

logger = logging.getLogger(__name__)


class CompletionAPI(BasicLLMAPI):
    def completion(self, **kwargs):
        if 'model' in kwargs:
            kwargs.pop('model')
        if 'base_url' in kwargs:
            kwargs.pop('base_url')
        if 'api_key' in kwargs:
            kwargs.pop('api_key')

        context = kwargs.pop('context', {})
        try:
            gpt_version = re.search(r'\bgpt-(\d+)\b', self.model_id)
            if gpt_version and int(gpt_version.group(1)) >= 5:
                kwargs['temperature'] = 1
                if kwargs.get('tools'):
                    kwargs.setdefault('reasoning_effort', 'low')
            if re.search(r'\bclaude\b', self.model_id, re.IGNORECASE):
                # Newer Claude models reject temperature, including explicit values.
                kwargs.pop('temperature', None)
            if self.llm_type == 'openai' and 'reasoning_effort' in kwargs:
                allowed_params = list(kwargs.get('allowed_openai_params') or [])
                if 'reasoning_effort' not in allowed_params:
                    allowed_params.append('reasoning_effort')
                kwargs['allowed_openai_params'] = allowed_params
            response = litellm.completion(
                model=self.model,
                base_url=self.base_url,
                api_key=self.api_key,
                custom_llm_provider=self.llm_type,
                timeout=self.timeout,
                **kwargs,
            )
        except Exception as error:
            logger.error('Chat completion error: %s', str(error))
            raise LLMChatCompletionException('LLM chat completion error: %s' % error)

        try:
            self.last_token_usage = {
                'input_tokens': response.usage.prompt_tokens,
                'output_tokens': response.usage.completion_tokens,
            }
        except Exception:
            self.last_token_usage = {}
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

    def _logger_usage_from_response(self, response, context, model=None):
        try:
            self.logger_usage({
                'input_tokens': response.usage.prompt_tokens,
                'output_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens,
            }, context, model)
        except Exception:
            pass
