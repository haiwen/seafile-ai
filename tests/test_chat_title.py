import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TITLE_PROMPT = 'Generate a concise title for the conversation.\n\nUser Query:\n{query}\n\nAssistant Reply:\n{ai_reply}'


def load_chat_utils(llm_client):
    config_module = ModuleType('seafile_ai.config')
    config_module.AI_UTILS_TIER = {}
    prompts_module = ModuleType('seafile_ai.chat_manager.system_prompts')
    for name in (
            'CHAT_CORE_PROMPT', 'CHAT_CONTENT_GENERATION_RULES',
            'CHAT_CONTENT_GENERATOR_TOOLS_EXAMPLES', 'CHAT_GLOBAL_TOOL_RULES',
            'CHAT_LIST_FILES_TOOL_RULES', 'CHAT_OUTPUT_FORMAT_RULES',
            'CHAT_SEARCH_POLICY', 'CHAT_SEARCH_REFERENCE_RULES',
            'CHAT_SEARCH_TOOLS_EXAMPLES'):
        setattr(prompts_module, name, '')
    prompts_module.GENERATE_CHAT_TITLE_PROMPT = 'Generate concise chat titles.'
    prompts_module.GENERATE_CHAT_TITLE_USER_PROMPT = TITLE_PROMPT

    metadata_constants_module = ModuleType('seafile_ai.repo_metadata.constants')
    metadata_constants_module.METADATA_TABLE = Mock()
    metadata_api_module = ModuleType('seafile_ai.repo_metadata.metadata_server_api')
    metadata_api_module.MetadataServerAPI = Mock()
    metadata_utils_module = ModuleType('seafile_ai.repo_metadata.utils')
    metadata_utils_module.get_metadata_by_path = Mock()
    utils_module = ModuleType('seafile_ai.utils')
    utils_module.parse_file = Mock()
    constants_module = ModuleType('seafile_ai.utils.constants')
    constants_module.MODEL_REASONING_TIER = SimpleNamespace(LOW=SimpleNamespace(value='low'))
    llm_api_module = ModuleType('seafile_ai.utils.llm_api')
    llm_api_module.get_llm_client_by_model_tier = Mock(return_value=llm_client)

    spec = importlib.util.spec_from_file_location(
        'test_chat_title_utils_module',
        PROJECT_ROOT / 'seafile_ai/chat_manager/utils/__init__.py',
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        'seafile_ai.config': config_module,
        'seafile_ai.chat_manager.system_prompts': prompts_module,
        'seafile_ai.repo_metadata.constants': metadata_constants_module,
        'seafile_ai.repo_metadata.metadata_server_api': metadata_api_module,
        'seafile_ai.repo_metadata.utils': metadata_utils_module,
        'seafile_ai.utils': utils_module,
        'seafile_ai.utils.constants': constants_module,
        'seafile_ai.utils.llm_api': llm_api_module,
    }):
        spec.loader.exec_module(module)
    return module


class GenerateChatTitleTest(unittest.TestCase):
    def test_truncates_query_and_reply_before_prompting(self):
        llm_client = Mock()
        llm_client.run.return_value = '{"title": "Title"}'
        chat_utils = load_chat_utils(llm_client)
        query = 'q' * 500 + '~'
        ai_reply = 'r' * 500 + '`'

        title = chat_utils.generate_chat_title(
            SimpleNamespace(data_logger=Mock()),
            query,
            ai_reply,
            {'repo_id': 'repo-id'},
        )

        self.assertEqual(title, 'Title')
        messages = llm_client.run.call_args.args[0]
        self.assertEqual(
            messages[1]['content'],
            TITLE_PROMPT.format(query=query[:500], ai_reply=ai_reply[:500]),
        )
        self.assertNotIn('~', messages[1]['content'])
        self.assertNotIn('`', messages[1]['content'])
