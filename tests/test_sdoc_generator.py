import importlib.util
import json
import unittest
import sys
import ast
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'test_content_generators', Path(__file__).resolve().parents[1] / 'seafile_ai/chat_manager/tools/content_generators.py')
sdoc = importlib.util.module_from_spec(spec)
basic_tools = ModuleType('seafile_ai.utils.tools')
basic_tools.BasicTool = object
with patch.dict(sys.modules, {'seafile_ai.utils.tools': basic_tools}):
    spec.loader.exec_module(sdoc)


resolver_spec = importlib.util.spec_from_file_location(
    'test_sdoc_results', Path(__file__).resolve().parents[1] / 'seafile_ai/chat_manager/utils/sdoc.py')
resolver = importlib.util.module_from_spec(resolver_spec)
blocks_spec = importlib.util.spec_from_file_location(
    'seafile_ai.chat_manager.utils.content_blocks',
    Path(__file__).resolve().parents[1] / 'seafile_ai/chat_manager/utils/content_blocks.py')
blocks = importlib.util.module_from_spec(blocks_spec)
blocks_spec.loader.exec_module(blocks)
with patch.dict(sys.modules, {'seafile_ai.chat_manager.utils.content_blocks': blocks}):
    resolver_spec.loader.exec_module(resolver)
resolve_sdoc_results = resolver.resolve_sdoc_results

source = ast.parse((Path(__file__).resolve().parents[1] / 'seafile_ai/chat_manager/utils/__init__.py').read_text())
helper_names = {'get_answer_and_sources', 'clean_markdown_references'}
helper_nodes = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in helper_names]
helpers = {'resolve_sdoc_results': resolve_sdoc_results,
           'INTERNAL_REFERENCE_RE': sdoc.re.compile(r'<reference_(\d+)>')}
exec(compile(ast.Module(body=helper_nodes, type_ignores=[]), 'chat_manager/utils/__init__.py', 'exec'), helpers)


class SdocGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.executor = SimpleNamespace(cache={})

    def test_generator_has_three_required_string_arguments_and_no_service_dependency(self):
        parameters = sdoc.SdocGenerator.tool['function']['parameters']
        self.assertEqual(parameters['required'], ['file_name', 'description', 'content'])
        self.assertTrue(all(value['type'] == 'string' for value in parameters['properties'].values()))
        self.assertIn('<seafile-ai-seadoc', sdoc.SdocGenerator().execute('计划', 'Plan', self.document(), self.executor))

    def document(self, block=None):
        return json.dumps({'title': '项目计划', 'elements': [block or {
            'type': 'paragraph', 'children': [{'text': '阶段一', 'bold': True}]}]}, ensure_ascii=False)

    def test_plain_title_and_markdown_blocks(self):
        blocks = [
            {'type': 'header2', 'children': [{'text': 'Heading'}]},
            {'type': 'blockquote', 'children': [{'text': 'Quote'}]},
            {'type': 'ordered_list', 'items': [{'children': [{'text': 'First'}]}]},
            {'type': 'check_list_item', 'checked': False, 'children': [{'text': 'Task'}]},
            {'type': 'code_block', 'language': 'python', 'text': 'print(1)\nprint(2)'},
            {'type': 'divider'},
            {'type': 'table', 'rows': [{'cells': [{'children': [{'text': ''}]}]}]},
            {'type': 'paragraph', 'children': [{'type': 'link', 'href': 'https://example.com',
                                               'children': [{'text': 'Docs'}]}]},
        ]
        for block in blocks:
            with self.subTest(block=block):
                self.assertEqual(sdoc.SdocGenerator()._validate_sdoc_content(self.document(block))['elements'], [block])

    def test_rejects_invalid_json_objects_and_unsupported_fields(self):
        for content in ({}, 'not json', '[]', '{"title":{},"elements":[]}', self.document({'type': 'image'}),
                        self.document({'type': 'paragraph', 'children': [{'text': 'A', 'id': 'invented'}]}),
                        self.document({'type': 'paragraph', 'children': [{'text': 'A', 'bold': 'yes'}]}),
                        self.document({'type': 'paragraph', 'children': [{'text': '<reference_0>'}]})):
            with self.subTest(content=content), self.assertRaises(ValueError):
                sdoc.SdocGenerator()._validate_sdoc_content(content)

    def test_rejects_unsafe_links_and_unequal_table_rows(self):
        with self.assertRaises(ValueError):
            sdoc.SdocGenerator()._validate_sdoc_content(self.document({'type': 'paragraph', 'children': [
                {'type': 'link', 'href': 'javascript:alert(1)', 'children': [{'text': 'X'}]}]}))
        with self.assertRaises(ValueError):
            sdoc.SdocGenerator()._validate_sdoc_content(self.document({'type': 'table', 'rows': [
                {'cells': [{'children': [{'text': 'A'}]}]}, {'cells': []}]}))

    def test_tool_caches_validated_content_and_returns_only_reference(self):
        content = self.document({'type': 'paragraph', 'children': [{'text': '</seafile-ai-seadoc>'}]})
        tag = sdoc.SdocGenerator().execute('计划 "A"', 'A & B', content, self.executor)
        self.assertIn('计划 &quot;A&quot;.sdoc', tag)
        self.assertIn('A &amp; B', tag)
        self.assertTrue(tag.endswith(' />'))
        self.assertNotIn('elements', tag)
        cached = self.executor.cache['sdoc_create_results']
        self.assertEqual(len(cached), 1)
        identifier = next(iter(cached))
        self.assertIn('sdoc_create_uuid="%s"' % identifier, tag)
        self.assertEqual(cached[identifier]['content'], json.loads(content))
        expanded = resolve_sdoc_results(tag, self.executor)
        self.assertIn('计划 &quot;A&quot;.sdoc', expanded)
        self.assertEqual(expanded.count('</seafile-ai-seadoc>'), 1)
        body = expanded.split('>', 1)[1].rsplit('</', 1)[0]
        self.assertEqual(json.loads(body), json.loads(content))

    def test_resolution_uses_cache_without_revalidation_or_model_metadata(self):
        tag = sdoc.SdocGenerator().execute('Original', 'Description', self.document(), self.executor)
        altered = tag.replace('Original.sdoc', 'Invented.sdoc').replace('Description', 'Invented description')
        with patch.object(sdoc.SdocGenerator, '_validate_sdoc_content', side_effect=AssertionError('Must not validate again')):
            expanded = resolve_sdoc_results(altered, self.executor)
        self.assertIn('Original.sdoc', expanded)
        self.assertIn('Description', expanded)
        self.assertNotIn('Invented', expanded)
        paired = altered[:-2] + '>{"title":"Invented"}</seafile-ai-seadoc>'
        self.assertEqual(resolve_sdoc_results(paired, self.executor), expanded)

    def test_unknown_or_historical_references_never_become_creation_requests(self):
        tag = sdoc.SdocGenerator().execute('Plan', 'Description', self.document(), self.executor)
        self.assertEqual(resolve_sdoc_results(tag, SimpleNamespace(cache={})), '')
        self.assertEqual(resolve_sdoc_results('<seafile-ai-seadoc file_name="Fake.sdoc" />', self.executor), '')
        self.assertEqual(resolve_sdoc_results('```\n' + tag + '```', self.executor), '```\n' + tag + '```')
        markdown = '<seafile-ai-markdown file_name="example.md">' + tag + '</seafile-ai-markdown>'
        self.assertEqual(resolve_sdoc_results(markdown, self.executor), markdown)

    def test_get_answer_and_sources_expands_multiple_current_request_references(self):
        first = sdoc.SdocGenerator().execute('First', 'One', self.document(), self.executor)
        second = sdoc.SdocGenerator().execute('Second', 'Two', self.document(), self.executor)
        answer, sources = helpers['get_answer_and_sources'](self.executor, first + '\n' + second)
        self.assertEqual(answer.count('</seafile-ai-seadoc>'), 2)
        self.assertIn('First.sdoc', answer)
        self.assertIn('Second.sdoc', answer)
        self.assertEqual(sources, [])

    def test_filename_and_size_limits(self):
        for name in ('../plan', 'A\\B', '.sdoc', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                sdoc.SdocGenerator().execute(name, 'Description', self.document(), self.executor)
        self.assertEqual(self.executor.cache, {})
        with self.assertRaises(ValueError):
            sdoc.SdocGenerator()._validate_sdoc_content(' ' * (sdoc.MAX_CONTENT_LENGTH + 1))

    def test_closing_variants_require_current_cache(self):
        reference = sdoc.SdocGenerator().execute('Plan', 'Description', self.document(), self.executor)
        expected = resolve_sdoc_results(reference, self.executor)
        for closing in ['</seafile-ai-seadoc >', '</seafile-ai-seadoc\n>', '</seafile-ai-seadoc\t>',
                        '</seafile-ai-seadoc/>', '</seafile-ai-seadoc ignored="yes">']:
            paired = reference[:-2] + '>untrusted body' + closing
            with self.subTest(closing=closing):
                self.assertEqual(resolve_sdoc_results(paired, self.executor), expected)
                self.assertEqual(resolve_sdoc_results(paired, SimpleNamespace(cache={})), '')
        incomplete = reference[:-2] + '>untrusted body'
        self.assertEqual(resolve_sdoc_results(incomplete, self.executor), '')

    def test_length_uses_canonical_decoded_json_not_transport_escapes(self):
        document = {'title': 'Boundary', 'elements': [{'type': 'code_block', 'language': '', 'text': ''}]}
        base_length = len(json.dumps(document, ensure_ascii=False, separators=(',', ':')))
        document['elements'][0]['text'] = '<' * (sdoc.MAX_CONTENT_LENGTH - base_length)
        content = json.dumps(document, ensure_ascii=False)
        reference = sdoc.SdocGenerator().execute('Boundary', 'Test', content, self.executor)
        expanded = resolve_sdoc_results(reference, self.executor)
        self.assertGreater(len(expanded), sdoc.MAX_CONTENT_LENGTH)
        self.assertEqual(json.loads(expanded.split('>', 1)[1].rsplit('</', 1)[0]), document)
        document['elements'][0]['text'] += 'x'
        with self.assertRaises(ValueError):
            sdoc.SdocGenerator()._validate_sdoc_content(json.dumps(document))
        with self.assertRaises(ValueError):
            sdoc.SdocGenerator()._validate_sdoc_content(' ' * (sdoc.MAX_CONTENT_LENGTH * 6 + 3))


if __name__ == '__main__':
    unittest.main()
