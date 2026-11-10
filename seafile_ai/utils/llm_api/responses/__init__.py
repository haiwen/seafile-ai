import re

import litellm

from seafile_ai.utils.llm_api import BasicLLMAPI
from seafile_ai.utils.llm_api.responses.parser import ResponsesParser, ResponsesResult


class ResponsesAPI(BasicLLMAPI):
    def responses_stream(self, **kwargs):
        kwargs.pop('context', None)
        for key in ('model', 'base_url', 'api_base', 'api_key'):
            kwargs.pop(key, None)

        gpt_version = re.search(r'\bgpt-(\d+)\b', self.model_id)
        if gpt_version and int(gpt_version.group(1)) >= 5:
            kwargs['temperature'] = 1
        if re.search(r'\bclaude\b', self.model_id, re.IGNORECASE):
            kwargs.pop('temperature', None)

        events = litellm.responses(
            model=self.model,
            api_key=self.api_key,
            api_base=self.base_url,
            timeout=self.timeout,
            store=False,
            stream=True,
            include=['reasoning.encrypted_content'],
            **kwargs,
        )
        return ResponsesParser.iter_stream(events)
