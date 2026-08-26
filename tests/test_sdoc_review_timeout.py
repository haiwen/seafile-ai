import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name, source_path, modules=None):
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules or {}):
        spec.loader.exec_module(module)
    return module


def load_llm_api():
    config_module = ModuleType('seafile_ai.config')
    config_module.LLM_MODEL_ID_MODELS_MAP = {}
    config_module.LLM_MODEL_TIER_MODELS_MAP = {}
    config_module.DEFAULT_LLM_MODEL = {}

    utils_module = ModuleType('seafile_ai.utils')
    utils_module.LLMChatCompletionException = Exception
    constants_module = ModuleType('seafile_ai.utils.constants')
    constants_module.MODEL_USAGE_STATISTIC_CHANNEL_NAME = 'model-usage'
    litellm_module = ModuleType('litellm')
    litellm_module.completion = Mock()

    module = load_module(
        'test_sdoc_review_llm_api_module',
        PROJECT_ROOT / 'seafile_ai/utils/llm_api.py',
        {
            'seafile_ai.config': config_module,
            'seafile_ai.utils': utils_module,
            'seafile_ai.utils.constants': constants_module,
            'litellm': litellm_module,
        },
    )
    return module, litellm_module


class SDocReviewTimeoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context_module = load_module(
            'test_sdoc_review_context_module',
            PROJECT_ROOT / 'seafile_ai/server/sdoc_review_utils.py',
        )

    def test_review_context_preserves_usage_and_timeout_metadata(self):
        context = self.context_module.build_sdoc_ai_context({
            'org_id': 7,
            'repo_id': 'repo-id',
            'scenario': 'chat',
            'request_timeout_seconds': 28,
        }, 'user@example.com')

        self.assertEqual(context, {
            'username': 'user@example.com',
            'org_id': 7,
            'repo_id': 'repo-id',
            'scenario': 'chat',
            'request_timeout_seconds': 28,
        })

    def test_review_timeout_is_bounded(self):
        context = self.context_module.build_sdoc_ai_context({
            'request_timeout_seconds': 999,
        }, 'user@example.com')

        self.assertEqual(context['request_timeout_seconds'], 180)

    def test_llm_call_uses_request_scoped_timeout(self):
        module, litellm_module = load_llm_api()
        litellm_module.completion.return_value = Mock(
            choices=[Mock(message=Mock(content='done'))],
            usage=Mock(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        api = module.LLMAPI(Mock(), 'test-model', timeout=180)

        result = api.run(
            [{'role': 'user', 'content': 'Improve this.'}],
            {'request_timeout_seconds': 28, 'log_data': False},
        )

        self.assertEqual(result, 'done')
        self.assertEqual(litellm_module.completion.call_args.kwargs['timeout'], 28)


if __name__ == '__main__':
    unittest.main()
