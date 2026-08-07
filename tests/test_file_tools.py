import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name, source_path, modules):
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


def load_file_tools(query_metadata_rows):
    callbacker_module = ModuleType('seafile_ai.chat_manager.utils.callbacker')
    callbacker_module.ChatCallBacker = type('ChatCallBacker', (), {})
    constants_module = ModuleType('seafile_ai.repo_metadata.constants')
    constants_module.METADATA_TABLE = type('MetadataTable', (), {'name': 'Table1'})
    metadata_server_api_module = ModuleType('seafile_ai.repo_metadata.metadata_server_api')
    metadata_server_api_module.MetadataServerAPI = Mock()
    metadata_utils_module = ModuleType('seafile_ai.repo_metadata.utils')
    metadata_utils_module.query_metadata_rows = query_metadata_rows
    tools_module = ModuleType('seafile_ai.utils.tools')
    tools_module.BasicTool = object

    return load_module(
        'test_file_tools_module',
        PROJECT_ROOT / 'seafile_ai/chat_manager/tools/file_tools.py',
        {
            'seafile_ai.chat_manager.utils.callbacker': callbacker_module,
            'seafile_ai.repo_metadata.constants': constants_module,
            'seafile_ai.repo_metadata.metadata_server_api': metadata_server_api_module,
            'seafile_ai.repo_metadata.utils': metadata_utils_module,
            'seafile_ai.utils.tools': tools_module,
        },
    )

class ListFilesTest(unittest.TestCase):
    def test_returns_raw_full_library_metadata(self):
        records = [
            {'path': '/documents', '_is_dir': True},
            {'path': '/documents/plan.sdoc', '_is_dir': False, '_ai_summary': 'Project plan', 'custom': 'value'},
        ]
        query_metadata_rows = Mock(return_value=records)
        module = load_file_tools(query_metadata_rows)
        tool = module.ListFiles()

        result = tool.execute({'repo_id': 'repo-id'}, None)

        query_metadata_rows.assert_called_once_with('repo-id', tool.metadata_server_api, 'SELECT * FROM `Table1`')
        self.assertIs(result, records)
        self.assertEqual(module.ListFiles.tool['function']['parameters'], {'type': 'object', 'properties': {}})
