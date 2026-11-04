import importlib.util
import json
import re
from copy import deepcopy
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch
from html.parser import HTMLParser


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_sdoc_create():
    tools_module = ModuleType('seafile_ai.utils.tools')
    tools_module.BasicTool = object
    spec = importlib.util.spec_from_file_location(
        'test_sdoc_create_module',
        PROJECT_ROOT / 'seafile_ai/chat_manager/tools/sdoc_tools/create_sdoc.py',
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'seafile_ai.utils.tools': tools_module}):
        spec.loader.exec_module(module)
    return module


def text(value, **marks):
    return {'type': 'text', 'text': value, **marks}


class SdocCreateSkillTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_sdoc_create()
        cls.validator = cls.module.SdocValidator

    def test_tool_schema_has_three_closed_parameters(self):
        parameters = self.module.CreateSdoc.tool['function']['parameters']

        self.assertFalse(parameters['additionalProperties'])
        self.assertEqual(parameters['properties']['elements']['properties']['elements']['maxItems'], 200)
        self.assertEqual(parameters['required'], ['file_name', 'description', 'elements'])
        self.assertEqual(parameters['properties']['elements'], self.module.ELEMENTS_SCHEMA)
        self.assertEqual(parameters['$defs'], self.module.ELEMENTS_SCHEMA['$defs'])
        self.assertEqual(parameters['properties']['elements']['properties']['elements']['items']['oneOf'][0],
                         {'$ref': '#/$defs/paragraph'})
        self.assertNotIn('requested_directory', parameters['properties'])

    def test_schema_references_resolve_from_document_and_tool_roots(self):
        for root in (self.module.ELEMENTS_SCHEMA, self.module.SDOC_PARAMETERS):
            references = []

            def visit(value):
                if isinstance(value, dict):
                    if '$ref' in value:
                        references.append(value['$ref'])
                    for child in value.values():
                        visit(child)
                elif isinstance(value, list):
                    for child in value:
                        visit(child)

            visit(root)
            self.assertTrue(references)
            for reference in references:
                with self.subTest(reference=reference, tool_root=root is self.module.SDOC_PARAMETERS):
                    self.assertTrue(reference.startswith('#/'))
                    target = root
                    for part in reference[2:].split('/'):
                        target = target[part.replace('~1', '/').replace('~0', '~')]
                    self.assertIsInstance(target, dict)

    def test_skill_tool_argument_examples_pass_validation(self):
        content = (PROJECT_ROOT / 'seafile_ai/skills/builtin/sdoc-create/SKILL.md').read_text(encoding='utf-8')
        examples = re.findall(r'```json\n(.*?)\n```', content, re.DOTALL)
        self.assertTrue(examples)
        for example in examples:
            parameters = json.loads(example)
            with self.subTest(file_name=parameters.get('file_name')):
                self.validator.validate(**parameters)

    def test_accepts_representative_complex_elements(self):
        draft = self.validator.validate(
            'release-plan',
            'A release plan.',
            {'title': {'children': [text('Release ', bold=True), text('plan')]}, 'elements': [
                {'type': 'paragraph', 'children': [
                    text('See '),
                    {'type': 'link', 'href': 'https://example.com', 'title': 'details', 'children': [text('details')]},
                ]},
                {'type': 'callout', 'children': [
                    {'type': 'paragraph', 'children': [text('Important')]},
                ]},
                {'type': 'code_block', 'language': 'python', 'text': 'one\ntwo'},
                {'type': 'table', 'rows': [
                    {'cells': [{'children': [text('A')]}, {'children': [text('B')]}]},
                    {'cells': [{'children': [text('C')]}, {'children': [text('D')]}]},
                ]},
                {'type': 'multi_column', 'columns': [
                    {'children': [{'type': 'paragraph', 'children': [text('Left')]}]},
                    {'children': [{'type': 'paragraph', 'children': [text('Right')]}]},
                ]},
            ]},
        )

        self.assertEqual(draft['schema_version'], 1)
        self.assertEqual(len(draft['elements']), 5)

    def test_create_sdoc_waits_for_creation_and_caches_only_file_reference(self):
        class Executor:
            cache = {}

        api = Mock()
        api.create_sdoc.return_value = {
            'type': 'sdoc', 'schema_version': 1, 'status': 'created',
            'name': 'plan (1).sdoc', 'path': '/AI Generated/plan (1).sdoc', 'doc_uuid': 'doc-id',
            'description': 'A & "B"',
            'elements': [{'text': 'must not be forwarded'}],
        }
        executor = Executor()
        result = self.module.CreateSdoc().execute(
            'plan',
            'Description',
            {'title': {'children': [text('Plan')]}, 'elements': [{'type': 'paragraph', 'children': [text('Content')]}]},
            context={'sdoc_create_token': 'request-token', 'selected_skill_id': 'sdoc-create'}, tool_executor=executor,
            seahub_api=api,
        )

        api.create_sdoc.assert_called_once()
        draft, token = api.create_sdoc.call_args.args
        self.assertEqual(token, 'request-token')
        self.assertEqual(draft['type'], 'sdoc_create_request')
        self.assertIn('elements', draft)
        self.assertIn('status="created"', result)
        self.assertIn('path="/AI Generated/plan (1).sdoc"', result)
        self.assertIn('description="A &amp; &quot;B&quot;"', result)
        self.assertNotIn('elements', result)
        self.assertNotIn('artifacts', executor.cache)
        self.module.CreateSdoc().execute('again', '', {}, {'selected_skill_id': 'sdoc-create'}, executor, api)
        api.create_sdoc.assert_called_once()

    def test_timeout_is_unknown_and_is_not_retried(self):
        executor = Mock(cache={})
        api = Mock()
        api.create_sdoc.side_effect = TimeoutError()
        tool = self.module.CreateSdoc()
        args = ('plan', 'Description', {'title': {'children': [text('Plan')]},
                'elements': [{'type': 'paragraph', 'children': [text('Content')]}]},
                {'sdoc_create_token': 'token', 'selected_skill_id': 'sdoc-create'}, executor, api)
        result = tool.execute(*args)
        self.assertIn('status="unknown"', result)
        self.assertEqual(tool.execute(*args), result)
        api.create_sdoc.assert_called_once()
        self.assertNotIn('artifacts', executor.cache)

    def test_invalid_content_does_not_call_creation_api(self):
        api = Mock()
        result = self.module.CreateSdoc().execute(
            'plan', 'Description', {'title': {'children': [text('Plan')]}, 'elements': [{'type': 'image'}]},
            {'sdoc_create_token': 'token', 'selected_skill_id': 'sdoc-create'}, Mock(cache={}), api,
        )
        self.assertIn('status="failed"', result)
        api.create_sdoc.assert_not_called()

    def test_rejects_deferred_element(self):
        with self.assertRaisesRegex(ValueError, 'Invalid SDoc parameters'):
            self.validator.validate(
                'plan', 'Description', {'title': {'children': [text('Plan')]},
                'elements': [{'type': 'image'}]},
            )

    def test_rejects_internal_reference_token(self):
        with self.assertRaisesRegex(ValueError, 'citation token invalid'):
            self.validator.validate(
                'plan', 'Description', {'title': {'children': [text('Plan')]},
                'elements': [{'type': 'paragraph', 'children': [text('Source <reference_0>')]}]},
            )

    def test_rejects_unknown_element_fields(self):
        with self.assertRaisesRegex(ValueError, 'Invalid SDoc parameters'):
            self.validator.validate(
                'plan', 'Description', {'title': {'children': [text('Plan')]},
                'elements': [{'type': 'paragraph', 'children': [text('Content')], 'unexpected': True}]},
            )

    def test_requires_explicit_skill_authorization(self):
        api = Mock()
        with self.assertRaisesRegex(ValueError, 'explicit'):
            self.module.CreateSdoc().execute('plan', 'Description', {}, {}, Mock(cache={}), api)
        api.create_sdoc.assert_not_called()

    def test_schema_rejects_invalid_structures(self):
        invalid_elements = [
            {'type': 'paragraph'},
            {'type': 'paragraph', 'children': []},
            {'type': 'paragraph', 'children': [text('Content', bold=1)]},
            {'type': 'paragraph', 'children': [text('Content', font_size=True)]},
            {'type': 'paragraph', 'children': [{'type': 'link', 'href': 'https://example.com', 'children': [text('Link')]}]},
            {'type': 'header1', 'children': [{'type': 'link', 'href': 'https://example.com', 'title': 'Link', 'children': [text('Link')]}]},
            {'type': 'callout', 'children': [{'type': 'divider'}]},
            {'type': 'check_list_item', 'checked': 1, 'children': [text('Task')]},
            {'type': 'ordered_list', 'items': []},
            {'type': 'embed_link', 'link': 'https://example.com', 'link_type': 'figma', 'data': {'height': 199}},
            {'type': 'table', 'rows': [{'cells': []}]},
            {'type': 'table', 'rows': [{'cells': [{'children': [text('Cell')]}] * 21}]},
            {'type': 'multi_column', 'columns': [{'children': [{'type': 'divider'}]}]},
            {'type': 'multi_column', 'columns': [{'children': [{'type': 'table', 'rows': [{'cells': [{'children': [text('Cell')]}]}]}]}] * 2},
        ]
        for element in invalid_elements:
            with self.subTest(element=element):
                document = {'title': {'children': [text('Plan')]}, 'elements': [element]}
                with self.assertRaisesRegex(ValueError, 'Invalid SDoc parameters'):
                    self.validator.validate('Plan', 'Description', document)

    def test_schema_validates_top_level_fields(self):
        document = {'title': {'children': [text('Plan')]}, 'elements': [{'type': 'divider'}]}
        for file_name, description, elements in (
            (1, 'Description', document), ('Plan', None, document),
            ('Plan', 'Description', {**document, 'unexpected': True}),
            ('Plan', 'Description', {'elements': [{'type': 'divider'}]}),
        ):
            with self.subTest(file_name=file_name, description=description, elements=elements):
                with self.assertRaisesRegex(ValueError, 'Invalid SDoc parameters'):
                    self.validator.validate(file_name, description, elements)

    def test_business_rules_reject_schema_valid_content(self):
        invalid_elements = [
            {'type': 'paragraph', 'children': [text('  ')]},
            {'type': 'paragraph', 'children': [text('Content', color='red')]},
            {'type': 'paragraph', 'children': [text('Content', superscript=True, subscript=True)]},
            {'type': 'paragraph', 'children': [{'type': 'link', 'href': 'javascript:alert(1)', 'title': 'Link', 'children': [text('Link')]}]},
            {'type': 'embed_link', 'link': 'http://example.com', 'link_type': 'figma'},
            {'type': 'formula', 'data': {'formula': '  '}},
            {'type': 'callout', 'style': {'background_color': '#123456\n'}, 'children': [{'type': 'paragraph', 'children': [text('Content')]}]},
            {'type': 'table', 'rows': [
                {'cells': [{'children': [text('Cell')]}]},
                {'cells': [{'children': [text('Cell')]}] * 2},
            ]},
        ]
        for element in invalid_elements:
            with self.subTest(element=element):
                document = {'title': {'children': [text('Plan')]}, 'elements': [element]}
                self.validator._schema_validator.validate({'file_name': 'Plan', 'description': 'Description', 'elements': document})
                with self.assertRaises(ValueError):
                    self.validator.validate('Plan', 'Description', document)

    def test_budget_checks_run_before_schema_validation(self):
        for document in (
            {'nested': [[[[[]]]]]},
            {'values': ['x'] * 25},
            {'text': 'x' * 101},
        ):
            with self.subTest(document=document):
                with patch.object(self.validator, 'MAX_DEPTH', 5), \
                        patch.object(self.validator, 'MAX_NODES', 20), \
                        patch.object(self.validator, 'MAX_TEXT_LENGTH', 100), \
                        patch.object(self.validator, '_schema_validator') as validator:
                    with self.assertRaises(ValueError):
                        self.validator.validate('Plan', 'Description', document)
                    validator.validate.assert_not_called()

    def test_rejects_non_finite_numbers(self):
        for number in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(number=number):
                document = {'title': {'children': [text('Plan', font_size=number)]}, 'elements': [{'type': 'divider'}]}
                with self.assertRaisesRegex(ValueError, 'finite'):
                    self.validator.validate('Plan', 'Description', document)

    def test_validation_preserves_input_and_normalizes_only_metadata(self):
        document = {'title': {'children': [text('Plan')]}, 'elements': [{'type': 'code_block', 'language': '', 'text': ''}]}
        original = deepcopy(document)
        result = self.validator.validate(' Plan ', ' Description ', document)
        self.assertEqual(document, original)
        self.assertEqual(result['file_name'], 'Plan')
        self.assertEqual(result['description'], 'Description')
        self.assertEqual(result['title'], original['title'])
        self.assertEqual(result['elements'], original['elements'])

    def test_accepts_embed_and_large_nested_table(self):
        document = {
            'title': {'children': [text('Plan')]},
            'elements': [
                {'type': 'embed_link', 'link': 'https://figma.com/file/example', 'link_type': 'figma', 'data': {'height': 400}},
                {'type': 'table', 'rows': [{'cells': [{'children': [text('Cell')]} for _ in range(20)]} for _ in range(20)]},
            ],
        }
        self.assertEqual(len(self.validator.validate('Plan', 'Description', document)['elements']), 2)

    def test_rejects_top_level_limit_and_unsafe_filename(self):
        document = {'title': {'children': [text('Plan')]}, 'elements': [{'type': 'divider'}] * 201}
        with self.assertRaises(ValueError):
            self.validator.validate('Plan', 'Description', document)
        document['elements'] = [{'type': 'divider'}]
        with self.assertRaises(ValueError):
            self.validator.validate('../Plan', 'Description', document)

    def test_tag_round_trips_unicode_and_escaped_metadata(self):
        class Parser(HTMLParser):
            def handle_startendtag(self, tag, attrs):
                self.tag, self.attrs = tag, dict(attrs)

        data = {'status': 'created', 'name': '计划 "A".sdoc',
                'path': '/AI Generated/计划 "A".sdoc', 'description': '<示例> & details'}
        parser = Parser()
        parser.feed(self.module.CreateSdoc.seadoc_tag(data))
        self.assertEqual(parser.tag, 'seadoc')
        self.assertEqual(parser.attrs, data)

    def test_invalid_creation_response_is_unconfirmed_and_not_retried(self):
        api = Mock()
        api.create_sdoc.return_value = {'status': 'created', 'path': '/AI Generated/../Plan.sdoc'}
        executor = Mock(cache={})
        document = {'title': {'children': [text('Plan')]}, 'elements': [{'type': 'divider'}]}
        args = ('Plan', 'Description', document,
                {'selected_skill_id': 'sdoc-create', 'sdoc_create_token': 'token'}, executor, api)
        result = self.module.CreateSdoc().execute(*args)
        self.assertIn('status="unknown"', result)
        self.assertEqual(self.module.CreateSdoc().execute(*args), result)
        api.create_sdoc.assert_called_once()


if __name__ == '__main__':
    unittest.main()
