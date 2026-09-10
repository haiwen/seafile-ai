import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FILE_UUID_1 = '11111111-1111-1111-1111-111111111111'
FILE_UUID_2 = '22222222-2222-2222-2222-222222222222'
FileSizeLimitExceeded = type('FileSizeLimitExceeded', (Exception,), {})


def load_memory(
        get_file_path_by_uuid=None, get_repo_info=None, get_file_id_by_path=None, parse_file=None,
        max_file_size=10 * 1024 * 1024, max_total_chars=15000):
    sqlalchemy_module = ModuleType('sqlalchemy')
    sqlalchemy_module.desc = lambda value: value

    config_module = ModuleType('seafile_ai.config')
    config_module.READ_FILES_MAX_FILE_SIZE = max_file_size
    config_module.READ_FILES_MAX_TOTAL_CHARS = max_total_chars
    seafile_ai_module = ModuleType('seafile_ai')
    seafile_ai_module.config = config_module

    chat_utils_module = ModuleType('seafile_ai.chat_manager.utils')
    chat_utils_module.combine_attachments_to_message = Mock()
    chat_utils_module.retrieve_origin_reference_format = Mock()
    chat_utils_module.strip_content_details_from_attachments = Mock()

    metadata_utils_module = ModuleType('seafile_ai.repo_metadata.utils')
    metadata_utils_module.get_file_path_by_uuid = get_file_path_by_uuid or Mock()
    metadata_utils_module.get_repo_info = get_repo_info or Mock(return_value={'repo_id': 'repo-id'})
    metadata_utils_module.get_file_id_by_path = get_file_id_by_path or Mock(return_value='obj-id')

    utils_module = ModuleType('seafile_ai.utils')
    utils_module.parse_file = parse_file or Mock(return_value='current content')
    utils_module.FileSizeLimitExceeded = FileSizeLimitExceeded

    spec = importlib.util.spec_from_file_location(
        'test_chat_memory_module',
        PROJECT_ROOT / 'seafile_ai/chat_manager/memory.py',
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        'sqlalchemy': sqlalchemy_module,
        'seafile_ai': seafile_ai_module,
        'seafile_ai.config': config_module,
        'seafile_ai.chat_manager.utils': chat_utils_module,
        'seafile_ai.repo_metadata.utils': metadata_utils_module,
        'seafile_ai.utils': utils_module,
    }):
        spec.loader.exec_module(module)
    return module


def build_artifact(file_uuid, file_name, content):
    return (
        f'<seafile-ai-markdown-link url="https://seafile.example.com/smart-link/{file_uuid}/{file_name}">'
        '</seafile-ai-markdown-link>\n\n'
        f'<seafile-ai-markdown file_name="{file_name}">{content}</seafile-ai-markdown>'
    )


class RefreshGeneratedMarkdownArtifactsTest(unittest.TestCase):
    def test_refreshes_only_latest_snapshot_of_same_artifact(self):
        get_file_path_by_uuid = Mock(return_value='/AI Generated/plan.md')
        parse_file = Mock(return_value='manually updated content')
        module = load_memory(get_file_path_by_uuid=get_file_path_by_uuid, parse_file=parse_file)
        messages = [
            {'role': 'assistant', 'content': build_artifact(FILE_UUID_1, 'plan.md', 'version 1')},
            {'role': 'user', 'content': 'Revise the document'},
            {'role': 'assistant', 'content': build_artifact(FILE_UUID_1, 'plan.md', 'version 2')},
        ]

        result = module.refresh_generated_markdown_artifacts(messages, 'repo-id')

        self.assertIn('version 1', result[0]['content'])
        self.assertNotIn('manually updated content', result[0]['content'])
        self.assertIn('manually updated content', result[2]['content'])
        self.assertNotIn('version 2', result[2]['content'])
        get_file_path_by_uuid.assert_called_once_with('repo-id', FILE_UUID_1)
        parse_file.assert_called_once_with('/AI Generated/plan.md', 'repo-id', 'obj-id', 10 * 1024 * 1024)

    def test_refreshes_multiple_artifacts_independently(self):
        paths = {
            FILE_UUID_1: '/AI Generated/plan.md',
            FILE_UUID_2: '/AI Generated/notes.md',
        }
        contents = {
            '/AI Generated/plan.md': 'current plan',
            '/AI Generated/notes.md': 'current notes',
        }
        get_file_path_by_uuid = Mock(side_effect=lambda repo_id, file_uuid: paths[file_uuid])
        parse_file = Mock(side_effect=lambda file_path, repo_id, obj_id, max_size: contents[file_path])
        module = load_memory(get_file_path_by_uuid=get_file_path_by_uuid, parse_file=parse_file)
        messages = [{
            'role': 'assistant',
            'content': (
                build_artifact(FILE_UUID_1, 'plan.md', 'old plan')
                + '\n'
                + build_artifact(FILE_UUID_2, 'notes.md', 'old notes')
            ),
        }]

        result = module.refresh_generated_markdown_artifacts(messages, 'repo-id')

        self.assertIn('current plan', result[0]['content'])
        self.assertIn('current notes', result[0]['content'])
        self.assertNotIn('old plan', result[0]['content'])
        self.assertNotIn('old notes', result[0]['content'])

    def test_keeps_artifact_without_uploaded_file_link_unchanged(self):
        get_repo_info = Mock(return_value={'repo_id': 'repo-id'})
        module = load_memory(get_repo_info=get_repo_info)
        content = '<seafile-ai-markdown file_name="plan.md">draft</seafile-ai-markdown>'
        messages = [{'role': 'assistant', 'content': content}]

        result = module.refresh_generated_markdown_artifacts(messages, 'repo-id')

        self.assertEqual(result[0]['content'], content)
        get_repo_info.assert_not_called()

    def test_does_not_pair_uploaded_link_with_unrelated_markdown_block(self):
        module = load_memory(
            get_file_path_by_uuid=Mock(return_value='/AI Generated/plan.md'),
            parse_file=Mock(return_value='current plan'),
        )
        unlinked_content = '<seafile-ai-markdown file_name="draft.md">local draft</seafile-ai-markdown>'
        messages = [{
            'role': 'assistant',
            'content': unlinked_content + '\n' + build_artifact(FILE_UUID_1, 'plan.md', 'old plan'),
        }]

        result = module.refresh_generated_markdown_artifacts(messages, 'repo-id')

        self.assertIn(unlinked_content, result[0]['content'])
        self.assertIn('current plan', result[0]['content'])
        self.assertNotIn('old plan', result[0]['content'])

    def test_marks_missing_uploaded_artifact_as_unavailable(self):
        get_file_path_by_uuid = Mock(return_value=None)
        get_file_id_by_path = Mock()
        parse_file = Mock()
        module = load_memory(
            get_file_path_by_uuid=get_file_path_by_uuid,
            get_file_id_by_path=get_file_id_by_path,
            parse_file=parse_file,
        )
        messages = [{
            'role': 'assistant',
            'content': build_artifact(FILE_UUID_1, 'plan.md', 'stale content'),
        }]

        result = module.refresh_generated_markdown_artifacts(messages, 'repo-id')

        self.assertIn(module.MARKDOWN_ARTIFACT_UNAVAILABLE, result[0]['content'])
        self.assertNotIn('stale content', result[0]['content'])
        get_file_id_by_path.assert_not_called()
        parse_file.assert_not_called()

    def test_marks_oversized_artifact_as_unavailable(self):
        parse_file = Mock(side_effect=FileSizeLimitExceeded())
        module = load_memory(
            get_file_path_by_uuid=Mock(return_value='/AI Generated/plan.md'),
            parse_file=parse_file,
            max_file_size=100,
        )
        messages = [{
            'role': 'assistant',
            'content': build_artifact(FILE_UUID_1, 'plan.md', 'stale content'),
        }]

        result = module.refresh_generated_markdown_artifacts(messages, 'repo-id')

        self.assertIn(module.MARKDOWN_ARTIFACT_UNAVAILABLE, result[0]['content'])
        self.assertNotIn('stale content', result[0]['content'])
        parse_file.assert_called_once_with('/AI Generated/plan.md', 'repo-id', 'obj-id', 100)

    def test_truncates_refreshed_content_at_total_limit(self):
        parse_file = Mock(return_value='abcdefgh')
        module = load_memory(
            get_file_path_by_uuid=Mock(return_value='/AI Generated/plan.md'),
            parse_file=parse_file,
            max_file_size=100,
            max_total_chars=5,
        )
        messages = [{
            'role': 'assistant',
            'content': build_artifact(FILE_UUID_1, 'plan.md', 'old plan'),
        }]

        result = module.refresh_generated_markdown_artifacts(messages, 'repo-id')

        self.assertIn('abcde' + module.MARKDOWN_ARTIFACT_TRUNCATED, result[0]['content'])
        self.assertNotIn('abcdef', result[0]['content'])
        parse_file.assert_called_once_with('/AI Generated/plan.md', 'repo-id', 'obj-id', 100)


if __name__ == '__main__':
    unittest.main()
