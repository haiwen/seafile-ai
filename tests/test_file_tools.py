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


def load_file_tools(
    query_metadata_rows,
    metadata_enabled=True,
    default_max_records=100,
    get_repo_info=None,
    get_file_id_by_path=None,
    parse_file=None,
):
    config_module = ModuleType('seafile_ai.config')
    config_module.DEFAULT_LIST_FILES_MAX_RECORDS = default_max_records
    seafile_ai_module = ModuleType('seafile_ai')
    seafile_ai_module.config = config_module

    callbacker_module = ModuleType('seafile_ai.chat_manager.utils.callbacker')
    callbacker_module.ChatCallBacker = type('ChatCallBacker', (), {})

    columns_mock = Mock()
    columns_mock.is_dir.name = '_is_dir'
    columns_mock.parent_dir.name = '_parent_dir'
    columns_mock.file_name.name = '_name'
    columns_mock.file_mtime.name = '_file_mtime'
    constants_module = ModuleType('seafile_ai.repo_metadata.constants')
    metadata_table_mock = Mock()
    metadata_table_mock.name = 'Table1'
    metadata_table_mock.columns = columns_mock
    constants_module.METADATA_TABLE = metadata_table_mock

    metadata_server_api_module = ModuleType('seafile_ai.repo_metadata.metadata_server_api')
    metadata_server_api_module.MetadataServerAPI = Mock()

    metadata_utils_module = ModuleType('seafile_ai.repo_metadata.utils')
    metadata_utils_module.query_metadata_rows = query_metadata_rows
    metadata_utils_module.is_repo_metadata_enabled = Mock(return_value=metadata_enabled)
    metadata_utils_module.get_repo_info = get_repo_info or Mock()
    metadata_utils_module.get_file_id_by_path = get_file_id_by_path or Mock()

    utils_module = ModuleType('seafile_ai.utils')
    utils_module.parse_file = parse_file or Mock()

    tools_module = ModuleType('seafile_ai.utils.tools')
    tools_module.BasicTool = object

    return load_module(
        'test_file_tools_module',
        PROJECT_ROOT / 'seafile_ai/chat_manager/tools/file_tools.py',
        {
            'seafile_ai': seafile_ai_module,
            'seafile_ai.config': config_module,
            'seafile_ai.chat_manager.utils.callbacker': callbacker_module,
            'seafile_ai.repo_metadata.constants': constants_module,
            'seafile_ai.repo_metadata.metadata_server_api': metadata_server_api_module,
            'seafile_ai.repo_metadata.utils': metadata_utils_module,
            'seafile_ai.utils': utils_module,
            'seafile_ai.utils.tools': tools_module,
        },
    )

class ListFilesTest(unittest.TestCase):
    def test_lists_files_with_configured_limit(self):
        records = [
            {'_parent_dir': '/', '_name': 'plan.sdoc', '_is_dir': False, '_ai_summary': 'Project plan'},
            {'_parent_dir': '/plans', '_name': 'roadmap.sdoc', '_is_dir': False, '_ai_summary': 'Product roadmap'},
        ]
        query_metadata_rows = Mock(return_value=records)
        module = load_file_tools(query_metadata_rows, default_max_records=10)
        tool = module.ListFiles()

        result = tool.execute(context={'repo_id': 'repo-id'}, call_back=None)

        query_metadata_rows.assert_called_once_with(
            'repo-id', tool.metadata_server_api,
            'SELECT * FROM `Table1` WHERE (`_is_dir` = false OR `_is_dir` IS NULL) ORDER BY `_file_mtime` DESC',
            params=[], limit=11,
        )
        self.assertEqual(result, {
            'records': [
                {
                    '_parent_dir': '/',
                    '_name': 'plan.sdoc',
                    '_is_dir': False,
                    '_ai_summary': 'Project plan',
                    'path': '<seafile-ai-file>/plan.sdoc</seafile-ai-file>',
                },
                {
                    '_parent_dir': '/plans',
                    '_name': 'roadmap.sdoc',
                    '_is_dir': False,
                    '_ai_summary': 'Product roadmap',
                    'path': '<seafile-ai-file>/plans/roadmap.sdoc</seafile-ai-file>',
                },
            ],
        })

    def test_returns_metadata_enablement_warning(self):
        query_metadata_rows = Mock()
        module = load_file_tools(query_metadata_rows, metadata_enabled=False)
        tool = module.ListFiles()

        result = tool.execute(context={'repo_id': 'repo-id'}, call_back=None)

        self.assertEqual(result['records'], [])
        self.assertIn('Tell the user to enable library metadata', result['warning'])
        query_metadata_rows.assert_not_called()


class ReadFilesTest(unittest.TestCase):
    def test_reads_content_by_path_without_metadata(self):
        query_metadata_rows = Mock()
        get_repo_info = Mock(return_value={'repo_id': 'repo-id'})
        get_file_id_by_path = Mock(return_value='obj-id')
        parse_file = Mock(return_value='Project plan')
        module = load_file_tools(
            query_metadata_rows,
            get_repo_info=get_repo_info,
            get_file_id_by_path=get_file_id_by_path,
            parse_file=parse_file,
        )

        result = module.ReadFiles().execute(['/documents/plan.sdoc'], {'repo_id': 'repo-id'}, None)

        self.assertEqual(result, [{
            'path': '/documents/plan.sdoc',
            'content': 'Project plan',
        }])
        get_repo_info.assert_called_once_with('repo-id')
        get_file_id_by_path.assert_called_once_with({'repo_id': 'repo-id'}, '/documents/plan.sdoc')
        parse_file.assert_called_once_with('/documents/plan.sdoc', 'repo-id', 'obj-id')
        query_metadata_rows.assert_not_called()

    def test_reads_every_requested_file(self):
        query_metadata_rows = Mock()
        get_repo_info = Mock(return_value={'repo_id': 'repo-id'})
        get_file_id_by_path = Mock(side_effect=['obj-%d' % index for index in range(6)])
        parse_file = Mock(side_effect=['content-%d' % index for index in range(6)])
        module = load_file_tools(
            query_metadata_rows,
            get_repo_info=get_repo_info,
            get_file_id_by_path=get_file_id_by_path,
            parse_file=parse_file,
        )
        file_paths = ['/documents/plan-%d.sdoc' % index for index in range(6)]

        result = module.ReadFiles().execute(file_paths, {'repo_id': 'repo-id'}, None)

        self.assertEqual(result, [
            {'path': file_path, 'content': 'content-%d' % index}
            for index, file_path in enumerate(file_paths)
        ])
        self.assertEqual(get_file_id_by_path.call_count, 6)
        self.assertEqual(parse_file.call_count, 6)

    def test_returns_full_content_without_a_character_limit(self):
        query_metadata_rows = Mock()
        get_repo_info = Mock(return_value={'repo_id': 'repo-id'})
        get_file_id_by_path = Mock(return_value='obj-id')
        content = 'a' * 6001
        parse_file = Mock(return_value=content)
        module = load_file_tools(
            query_metadata_rows,
            get_repo_info=get_repo_info,
            get_file_id_by_path=get_file_id_by_path,
            parse_file=parse_file,
        )

        result = module.ReadFiles().execute(['/documents/plan.sdoc'], {'repo_id': 'repo-id'}, None)

        self.assertEqual(result, [{'path': '/documents/plan.sdoc', 'content': content}])

    def test_reports_unavailable_files_without_reading_them(self):
        query_metadata_rows = Mock()
        get_repo_info = Mock(return_value={'repo_id': 'repo-id'})
        get_file_id_by_path = Mock(return_value=None)
        parse_file = Mock()
        module = load_file_tools(
            query_metadata_rows,
            get_repo_info=get_repo_info,
            get_file_id_by_path=get_file_id_by_path,
            parse_file=parse_file,
        )

        result = module.ReadFiles().execute(
            ['/documents/missing.sdoc', '/documents/image.png'],
            {'repo_id': 'repo-id'},
            None,
        )

        self.assertEqual(result, [
            {'path': '/documents/missing.sdoc', 'error': 'File not found'},
            {'path': '/documents/image.png', 'error': 'Unsupported file type'},
        ])
        parse_file.assert_not_called()
        query_metadata_rows.assert_not_called()
