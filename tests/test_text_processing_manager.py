import sys
import types
import unittest


document_module = types.ModuleType('seafile_ai.parsers.document')
document_module.parse_file = lambda file_name, file_content: file_content.decode() if isinstance(file_content, bytes) else file_content
document_module.get_file_ext = lambda file_name: '.' + file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''
document_module.resize_image_binary = lambda image_binary, ext, size: image_binary
document_module.is_pdf = lambda file_name: file_name.lower().endswith('.pdf')
sys.modules.setdefault('seafile_ai.parsers.document', document_module)

from seafile_ai.exceptions import FormatNotSupportedException, InvalidWritingTypeException
from seafile_ai.text_processing.text_processing_manager import TextProcessingManager
from seafile_ai.utils.constants import WritingType


class DummyLLMAPI:
    def __init__(self, result='ok'):
        self.result = result
        self.calls = []

    def run(self, messages, context):
        self.calls.append((messages, context))
        return self.result


class DummySeafileClient:
    def __init__(self, content):
        self.content = content

    def get_file_by_token(self, token, filename):
        return self.content


class TextProcessingManagerTest(unittest.TestCase):
    def test_generate_summary_uses_downloaded_file_content(self):
        llm_api = DummyLLMAPI('summary')
        file_client = DummySeafileClient(b'# title')
        manager = TextProcessingManager(llm_api, file_client)

        result = manager.generate_summary('/docs/test.md', 'token', {'username': 'u'})

        self.assertEqual(result, 'summary')
        self.assertTrue(llm_api.calls)

    def test_extract_text_rejects_unsupported_format(self):
        manager = TextProcessingManager(DummyLLMAPI(), DummySeafileClient(b''))

        with self.assertRaises(FormatNotSupportedException):
            manager.extract_text('demo.txt', 'token', {})

    def test_get_predefined_prompt_rejects_unknown_writing_type(self):
        manager = TextProcessingManager(DummyLLMAPI(), DummySeafileClient(b''))

        with self.assertRaises(InvalidWritingTypeException):
            manager.get_predefined_prompt('prefix', 'unknown')

    def test_get_predefined_prompt_supports_known_type(self):
        manager = TextProcessingManager(DummyLLMAPI(), DummySeafileClient(b''))

        prompt = manager.get_predefined_prompt('prefix', WritingType.MORE_CONCISE)

        self.assertIn('concise', prompt)


if __name__ == '__main__':
    unittest.main()
