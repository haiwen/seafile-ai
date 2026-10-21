import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_sdoc_create():
    tools_module = ModuleType('seafile_ai.utils.tools')
    tools_module.BasicTool = object
    spec = importlib.util.spec_from_file_location(
        'test_sdoc_create_module',
        PROJECT_ROOT / 'seafile_ai/chat_manager/skills/sdoc_create.py',
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

    def test_tool_schema_is_closed_and_versioned_by_artifact(self):
        parameters = self.module.CreateSdoc.tool['function']['parameters']

        self.assertFalse(parameters['additionalProperties'])
        self.assertEqual(parameters['properties']['elements']['maxItems'], 200)
        self.assertNotIn('$ref', json.dumps(parameters))
        self.assertNotIn('requested_directory', parameters['properties'])

    def test_accepts_representative_complex_elements(self):
        draft = self.module.validate_sdoc_draft(
            'release-plan',
            {'children': [text('Release ', bold=True), text('plan')]},
            [
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
            ],
            summary='A release plan.',
        )

        self.assertEqual(draft['schema_version'], 1)
        self.assertEqual(len(draft['elements']), 5)

    def test_create_sdoc_waits_for_creation_and_caches_only_file_reference(self):
        class Executor:
            cache = {}

        api = Mock()
        api.create_sdoc.return_value = {
            'type': 'sdoc', 'schema_version': 1, 'status': 'created',
            'relative_path': 'plan (1).sdoc', 'repo_id': 'repo-id',
            'elements': [{'text': 'must not be forwarded'}],
        }
        executor = Executor()
        result = self.module.CreateSdoc().execute(
            'plan',
            {'children': [text('Plan')]},
            [{'type': 'paragraph', 'children': [text('Content')]}],
            context={'sdoc_create_token': 'request-token'}, tool_executor=executor,
            seahub_api=api, summary='Summary',
        )

        api.create_sdoc.assert_called_once()
        draft, token = api.create_sdoc.call_args.args
        self.assertEqual(token, 'request-token')
        self.assertEqual(draft['type'], 'sdoc_create_request')
        self.assertIn('elements', draft)
        self.assertEqual(result['status'], 'created')
        self.assertEqual(result['relative_path'], 'plan (1).sdoc')
        self.assertEqual(Executor.cache['artifacts'][0]['schema_version'], 1)
        self.assertNotIn('elements', Executor.cache['artifacts'][0])
        self.assertNotIn('blocks', Executor.cache['artifacts'][0])
        self.module.CreateSdoc().execute('again', {}, [], {}, executor, api)
        api.create_sdoc.assert_called_once()

    def test_timeout_is_unknown_and_is_not_retried(self):
        executor = Mock(cache={})
        api = Mock()
        api.create_sdoc.side_effect = TimeoutError()
        tool = self.module.CreateSdoc()
        args = ('plan', {'children': [text('Plan')]},
                [{'type': 'paragraph', 'children': [text('Content')]}],
                {'sdoc_create_token': 'token'}, executor, api)
        result = tool.execute(*args)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(tool.execute(*args), result)
        api.create_sdoc.assert_called_once()
        self.assertEqual(executor.cache['artifacts'], [result])

    def test_invalid_content_does_not_call_creation_api(self):
        api = Mock()
        result = self.module.CreateSdoc().execute(
            'plan', {'children': [text('Plan')]}, [{'type': 'image'}],
            {'sdoc_create_token': 'token'}, Mock(cache={}), api,
        )
        self.assertEqual(result['status'], 'failed')
        api.create_sdoc.assert_not_called()

    def test_rejects_deferred_element(self):
        with self.assertRaisesRegex(ValueError, 'unsupported element type'):
            self.module.validate_sdoc_draft(
                'plan', {'children': [text('Plan')]},
                [{'type': 'image'}],
            )

    def test_rejects_internal_reference_token(self):
        with self.assertRaisesRegex(ValueError, 'citation token invalid'):
            self.module.validate_sdoc_draft(
                'plan', {'children': [text('Plan')]},
                [{'type': 'paragraph', 'children': [text('Source <reference_0>')]}],
            )

    def test_rejects_unknown_element_fields(self):
        with self.assertRaisesRegex(ValueError, 'object fields invalid'):
            self.module.validate_sdoc_draft(
                'plan', {'children': [text('Plan')]},
                [{'type': 'paragraph', 'children': [text('Content')], 'unexpected': True}],
            )


if __name__ == '__main__':
    unittest.main()
