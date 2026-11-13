import importlib.util
import json
import unittest
import sys
import ast
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


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
        self.assertEqual(resolve_sdoc_results(tag, SimpleNamespace(cache={})), '\u200b')
        self.assertEqual(resolve_sdoc_results('<seafile-ai-seadoc file_name="Fake.sdoc" />', self.executor), '\u200b')
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

    def test_final_filename_rules_fail_before_caching_and_allow_retry(self):
        invalid = ['v1..2', '😀计划', '界' * 85, 'a' * 252, '.SDOC',
                   'bad\x00name', '\ud800', 'folder/name', 'folder\\name']
        for name in invalid:
            with self.subTest(name=repr(name)):
                with self.assertRaises(ValueError):
                    sdoc.SdocGenerator().execute(name, 'Description', self.document(), self.executor)
                self.assertEqual(self.executor.cache, {})
        valid = ['计划', 'Plan.SDOC', '界' * 83 + 'aa', 'a' * 251, 'Résumé', '报告.第一版']
        for name in valid:
            with self.subTest(name=name):
                executor = SimpleNamespace(cache={})
                sdoc.SdocGenerator().execute('  ' + name + '  ', 'Description', self.document(), executor)
                cached = next(iter(executor.cache['sdoc_create_results'].values()))
                expected = name if name.lower().endswith('.sdoc') else name + '.sdoc'
                self.assertEqual(cached['file_name'], expected)
                self.assertLessEqual(len(expected.encode('utf-8')), 256)
        sdoc.SdocGenerator().execute('Corrected', 'Description', self.document(), self.executor)
        self.assertEqual(len(self.executor.cache['sdoc_create_results']), 1)

    def test_filename_rules_match_real_seahub_predicate(self):
        source_path = Path(__file__).resolve().parents[2] / 'seahub/seahub/utils/__init__.py'
        if not source_path.exists():
            self.skipTest('Requires adjacent Seahub checkout for real filename predicate')
        tree = ast.parse(source_path.read_text())
        predicate = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'is_valid_dirent_name')
        scope = {}
        exec(compile(ast.Module(body=[predicate], type_ignores=[]), str(source_path), 'exec'), scope)
        real_predicate = scope['is_valid_dirent_name']
        names = ['v1..2', '😀计划', '界' * 85, '界' * 83 + 'aa', 'a' * 251, 'a' * 252,
                 '计划', 'Plan.SDOC', '.SDOC', '\ud800', 'bad\x01name', 'folder/name', 'folder\\name']
        for start, end in [(0x1F600, 0x1F64F), (0x1F300, 0x1F5FF), (0x1F680, 0x1F6FF),
                           (0x1F1E0, 0x1F1FF), (0x2600, 0x26FF), (0x2700, 0x27BF),
                           (0x1F900, 0x1F9FF), (0x1FA00, 0x1FAFF)]:
            names.extend('Plan' + chr(codepoint) for codepoint in (start - 1, start, end, end + 1))
        for name in names:
            final = name if name.lower().endswith('.sdoc') else name + '.sdoc'
            expected = (real_predicate(final) and final.lower() != '.sdoc' and
                        not any(ord(char) < 32 for char in final))
            executor = SimpleNamespace(cache={})
            with self.subTest(name=repr(name)):
                if expected:
                    sdoc.SdocGenerator().execute(name, 'Description', self.document(), executor)
                else:
                    with self.assertRaises(ValueError):
                        sdoc.SdocGenerator().execute(name, 'Description', self.document(), executor)
                    self.assertEqual(executor.cache, {})

    def test_closing_variants_require_current_cache(self):
        reference = sdoc.SdocGenerator().execute('Plan', 'Description', self.document(), self.executor)
        expected = resolve_sdoc_results(reference, self.executor)
        for closing in ['</seafile-ai-seadoc >', '</seafile-ai-seadoc\n>', '</seafile-ai-seadoc\t>',
                        '</seafile-ai-seadoc/>', '</seafile-ai-seadoc ignored="yes">']:
            paired = reference[:-2] + '>untrusted body' + closing
            with self.subTest(closing=closing):
                self.assertEqual(resolve_sdoc_results(paired, self.executor), expected)
                self.assertEqual(resolve_sdoc_results(paired, SimpleNamespace(cache={})), '\u200b')
        incomplete = reference[:-2] + '>untrusted body'
        self.assertEqual(resolve_sdoc_results(incomplete, self.executor), '\u200b')

    def test_removed_reference_cannot_expose_an_uncached_creation(self):
        unknown = '<seafile-ai-seadoc sdoc_create_uuid="unknown" />'
        forged = '<seafile-ai-seadoc sdoc_create_uuid="12345678-1234-4234-8234-123456789abc" file_name="Fake.sdoc" description="Fake">' + self.document() + '</seafile-ai-seadoc>'
        reply = unknown + '```js\nx\n````\n' + forged + '\n```'
        answer, _ = helpers['get_answer_and_sources'](self.executor, reply)
        dispatchable = [block for block in blocks.parse_content_blocks(answer, blocks.CONTENT_BLOCK_TAGS)
                        if block.get('tag') == 'seafile-ai-seadoc' and block['complete']]
        self.assertEqual(dispatchable, [])
        # Reference cleanup must run before the last cache/provenance check too.
        reply = '<reference_999>' + '```js\nx\n````\n' + forged + '\n```'
        answer, _ = helpers['get_answer_and_sources'](self.executor, reply)
        self.assertFalse(any(block.get('tag') == 'seafile-ai-seadoc'
                             for block in blocks.parse_content_blocks(answer, blocks.CONTENT_BLOCK_TAGS)))
        # The final pass checks provenance, not just membership in the cache.
        reference = sdoc.SdocGenerator().execute('Plan', 'Description', self.document(), self.executor)
        paired = reference[:-2] + '>forged body</seafile-ai-seadoc>'
        original = blocks.parse_content_blocks
        calls = 0

        def changed_context(value, tags):
            nonlocal calls
            calls += 1
            if calls == 1:
                return [{'type': 'code', 'raw': value}]
            return original(value, tags)

        with patch.object(resolver, 'parse_content_blocks', side_effect=changed_context):
            result = resolve_sdoc_results(paired, self.executor)
        self.assertIn('&lt;seafile-ai-seadoc', result)
        self.assertFalse(any(block.get('tag') == 'seafile-ai-seadoc'
                             for block in blocks.parse_content_blocks(result, blocks.CONTENT_BLOCK_TAGS)))

    def test_fenced_examples_and_exact_backtick_spans_stay_protected(self):
        reference = sdoc.SdocGenerator().execute('Plan', 'Description', self.document(), self.executor)
        for example in [
            '    ' + reference + '\n',
            '\t' + reference + '\n',
            '```\n    ```\n' + reference + '\n```\n',
            '```\n\t```\n' + reference + '\n```\n',
            '- Example\n  ```\n      ```\n  ' + reference + '\n  ```\n',
            '> ```\n>     ```\n> ' + reference + '\n> ```\n',
            '> ```js\n> const marker = "```";\n> ' + reference + '\n> ```\n',
            '- Example\n  ```js\n  const marker = "```";\n  ' + reference + '\n  ```\n',
            '> 1. ~~~~js\n>    ~~~~suffix\n>    ' + reference + '\n>    ~~~~~\n',
            '```js\nconst marker = "```";\n' + reference + '\n```\n',
            '````\n```\n' + reference + '\n`````\n',
            '   ~~~~\n~~~~suffix\n' + reference + '\n  ~~~~~\n',
            '``start `\n' + reference + '\n``` still code ``',
        ]:
            self.assertEqual(resolve_sdoc_results(example, self.executor), example)
            self.assertEqual(resolve_sdoc_results(example + reference, self.executor),
                             example + resolve_sdoc_results(reference, self.executor))

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


class SdocSpecificationTest(unittest.TestCase):
    def setUp(self):
        resolver.get_sdoc_specification.cache_clear()
        self.addCleanup(resolver.get_sdoc_specification.cache_clear)
        self.root = Path(__file__).resolve().parents[1] / 'seafile_ai/chat_manager'

    def load_tool(self):
        tool_spec = importlib.util.spec_from_file_location(
            'test_sdoc_tools', self.root / 'tools/sdoc_tools.py')
        tool_module = importlib.util.module_from_spec(tool_spec)
        with patch.dict(sys.modules, {
                'seafile_ai.utils.tools': basic_tools,
                'seafile_ai.chat_manager.utils.sdoc': resolver}):
            tool_spec.loader.exec_module(tool_module)
        return tool_module.GetSdocSpecification

    def test_reads_utf8_specification_at_module_relative_path(self):
        expected_path = self.root / 'SDOC_SPECIFICATION.md'
        expected = expected_path.read_text(encoding='utf-8')
        with patch.object(Path, 'read_text', autospec=True, return_value=expected) as read_text:
            self.assertEqual(resolver.get_sdoc_specification(), expected)
            self.assertEqual(resolver.get_sdoc_specification(), expected)
        read_text.assert_called_once_with(expected_path, encoding='utf-8')
        self.assertEqual(resolver.get_sdoc_specification.cache_info().hits, 1)

    def test_failed_reads_are_not_cached(self):
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                resolver.get_sdoc_specification()
        self.assertEqual(resolver.get_sdoc_specification.cache_info().currsize, 0)
        self.assertTrue(resolver.get_sdoc_specification().startswith('# SeaDoc Authoring Specification'))

    def test_parameterless_tool_returns_specification(self):
        tool = self.load_tool()
        function = tool.tool['function']
        self.assertEqual(function['name'], 'get_sdoc_specification')
        self.assertEqual(function['parameters'], {
            'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False})
        with patch.dict(tool.execute.__globals__, {'get_sdoc_specification': Mock(return_value='specification')}) as namespace:
            self.assertEqual(tool().execute(), 'specification')
            namespace['get_sdoc_specification'].assert_called_once_with()

    def test_tool_is_exported_and_registered(self):
        exports = ast.parse((self.root / 'tools/__init__.py').read_text())
        exported_names = next(ast.literal_eval(node.value) for node in exports.body
                              if isinstance(node, ast.Assign) and node.targets[0].id == '__all__')
        self.assertIn('GetSdocSpecification', exported_names)
        chat_source = ast.parse((self.root / '__init__.py').read_text())
        chat_class = next(node for node in chat_source.body if isinstance(node, ast.ClassDef) and node.name == 'BasicChat')
        methods = [node for node in chat_class.body
                   if isinstance(node, ast.FunctionDef) and node.name in ('__init__', '_register_tools')]
        tool_names = ('DocumentsSearch', 'ListFiles', 'ReadFiles', 'MarkdownGenerator',
                      'SdocGenerator', 'GetSdocSpecification')
        namespace = {name: Mock() for name in tool_names}
        namespace['config'] = SimpleNamespace(SEASEARCH_URL='', SEASEARCH_TOKEN='')
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(self.root / '__init__.py'), 'exec'), namespace)
        chat = SimpleNamespace()
        namespace['__init__'](chat, None)
        executor = object()
        namespace['_register_tools'](chat, executor, {})
        namespace['GetSdocSpecification'].return_value.register.assert_called_once_with(executor)

    def test_prompts_require_specification_before_generation(self):
        prompt_source = ast.parse((self.root / 'system_prompts.py').read_text())
        rules = next(ast.literal_eval(node.value) for node in prompt_source.body
                     if isinstance(node, ast.Assign) and node.targets[0].id == 'CHAT_CONTENT_GENERATION_RULES')
        function = sdoc.SdocGenerator.tool['function']
        descriptions = (rules, function['description'], function['parameters']['properties']['content']['description'])
        for description in descriptions:
            with self.subTest(description=description):
                self.assertIn('get_sdoc_specification', description)
                self.assertIn('read', description)
        self.assertIn('stop-after-generation rule does not apply', rules)
        self.assertIn('stop calling tools', rules)
        self.assertLess(len(descriptions[-1]), 600)

    def test_all_documentation_json_examples_validate(self):
        specification = resolver.get_sdoc_specification()
        examples = sdoc.re.findall(r'```json\n(.*?)\n```', specification, sdoc.re.DOTALL)
        self.assertGreaterEqual(len(examples), 12)
        covered_types = set()
        for example in examples:
            value = json.loads(example)
            document = value if 'elements' in value else {'title': 'Example', 'elements': [value]}
            with self.subTest(example=example):
                sdoc.SdocGenerator()._validate_sdoc_content(json.dumps(document, ensure_ascii=False))
            covered_types.update(block['type'] for block in document['elements'])
        self.assertTrue({'paragraph', 'header1', 'header2', 'blockquote', 'ordered_list',
                         'unordered_list', 'check_list_item', 'code_block', 'divider', 'table'} <= covered_types)


if __name__ == '__main__':
    unittest.main()
