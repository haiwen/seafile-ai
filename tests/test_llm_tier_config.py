import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name, source_path, modules=None):
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules or {}):
        spec.loader.exec_module(module)
    return module


def load_llm_api(tier_models, default_model):
    config_module = ModuleType('seafile_ai.config')
    config_module.LLM_MODEL_ID_MODELS_MAP = {}
    config_module.LLM_MODEL_TIER_MODELS_MAP = tier_models
    config_module.DEFAULT_LLM_MODEL = default_model

    utils_module = ModuleType('seafile_ai.utils')
    utils_module.LLMChatCompletionException = Exception
    constants_module = ModuleType('seafile_ai.utils.constants')
    constants_module.MODEL_USAGE_STATISTIC_CHANNEL_NAME = 'model-usage'
    litellm_module = ModuleType('litellm')

    return load_module(
        'test_llm_api_module',
        PROJECT_ROOT / 'seafile_ai/utils/llm_api.py',
        {
            'seafile_ai.config': config_module,
            'seafile_ai.utils': utils_module,
            'seafile_ai.utils.constants': constants_module,
            'litellm': litellm_module,
        },
    )


class LLMModelTierTest(unittest.TestCase):
    def test_selects_tier_model_or_default(self):
        default_model = {'model': 'default-model', 'type': 'openai', 'key': 'default-key'}
        module = load_llm_api(
            {'low': {'model': 'low-model', 'type': 'openai', 'key': 'low-key'}},
            default_model,
        )

        for tier, expected_model in (
            ('low', 'low-model'),
            ('missing', 'default-model'),
            (None, 'default-model'),
        ):
            with self.subTest(tier=tier):
                client = module.get_llm_client_by_model_tier(None, tier)
                self.assertEqual(client.model_id, expected_model)

        module = load_llm_api({}, default_model)
        client = module.get_llm_client_by_model_tier(None, 'low')
        self.assertEqual(client.model_id, 'default-model')


class AIUtilsTierConfigTest(unittest.TestCase):
    def test_non_mapping_values_fall_back_to_empty_mapping(self):
        for value in ('null', '"low"', '["low"]'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temp_dir:
                config_path = Path(temp_dir) / 'seafile_ai_config.yaml'
                config_path.write_text(
                    'global:\n'
                    '  EMBEDDING_MODEL:\n'
                    '    type: openai\n'
                    '    model: text-embedding-3-large\n'
                    '    key: test-key\n'
                    f'  AI_UTILS_TIER: {value}\n',
                    encoding='utf-8',
                )

                with patch.dict(sys.modules, {'seafile_ai_settings': None}):
                    with patch.dict('os.environ', {'CONF_PATH': temp_dir}, clear=False):
                        module = load_module(
                            f'test_config_module_{value}',
                            PROJECT_ROOT / 'seafile_ai/config.py',
                        )

                self.assertEqual(module.AI_UTILS_TIER, {})
