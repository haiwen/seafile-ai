import json
import logging

from seafile_ai.config import LLM_MODEL_ID_MODELS_MAP, LLM_MODEL_TIER_MODELS_MAP, DEFAULT_LLM_MODEL
from seafile_ai.utils.constants import MODEL_USAGE_STATISTIC_CHANNEL_NAME

logger = logging.getLogger(__name__)


class BasicLLMAPI:
    def __init__(self, data_logger, model, llm_type='openai', base_url=None, api_key=None, timeout=180):
        self.data_logger = data_logger
        self.timeout = timeout
        self.last_token_usage = {}
        if llm_type == 'other':
            llm_type = 'hosted_vllm'
        if llm_type in ('other', 'hosted_vllm') and not base_url:
            raise ValueError(f'The llm_url has to set in llm_type = {llm_type}')
        self.llm_type = llm_type
        self.model = f'{llm_type}/{model}' if llm_type else model
        self.model_id = model
        self.base_url = base_url
        self.api_key = api_key

    def logger_usage(self, token_usage, context, model=None):
        if context.get('log_data') is False:
            return
        try:
            self.data_logger.log_data(MODEL_USAGE_STATISTIC_CHANNEL_NAME, json.dumps({
                'model': self.model_id if not model else model,
                'usage': {
                    'prompt_tokens': token_usage.get('input_tokens', 0),
                    'completion_tokens': token_usage.get('output_tokens', 0),
                    'total_tokens': token_usage.get('total_tokens', 0),
                },
                'repo_id': context.get('repo_id'),
                'scenario': context.get('scenario', 'unknown'),
            }))
        except Exception as error:
            logger.warning('Chat completed but failure to log usages: %s', error)


from seafile_ai.utils.llm_api.completion import CompletionAPI
from seafile_ai.utils.llm_api.responses import ResponsesAPI, ResponsesResult
from seafile_ai.utils.llm_api.responses.constants import STREAM_TEXT_DELTA, STREAM_COMPLETED


def get_completion_client_by_model_tier(data_logger, tier):
    model_config = LLM_MODEL_TIER_MODELS_MAP.get(tier, DEFAULT_LLM_MODEL)
    return CompletionAPI(data_logger, model_config.get('model'), model_config.get('type', 'openai'), model_config.get('url'), model_config.get('key'))


def get_responses_client_by_model_id(data_logger, model_id):
    model_config = LLM_MODEL_ID_MODELS_MAP.get(model_id, DEFAULT_LLM_MODEL) if model_id else DEFAULT_LLM_MODEL
    return ResponsesAPI(data_logger, model_config.get('model'), model_config.get('type', 'openai'), model_config.get('url'), model_config.get('key'))
