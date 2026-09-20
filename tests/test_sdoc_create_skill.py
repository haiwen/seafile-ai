import json
import unittest

from seafile_ai.chat_manager.skills.sdoc_create import GenerateSdoc, validate_sdoc_draft


def text(value, **marks):
    return {'type': 'text', 'text': value, **marks}


class SdocCreateSkillTest(unittest.TestCase):
    def test_tool_schema_is_closed_and_versioned_by_artifact(self):
        parameters = GenerateSdoc.tool['function']['parameters']

        self.assertFalse(parameters['additionalProperties'])
        self.assertEqual(parameters['properties']['elements']['maxItems'], 200)
        self.assertNotIn('$ref', json.dumps(parameters))

    def test_accepts_representative_complex_elements(self):
        draft = validate_sdoc_draft(
            'release-plan',
            '/Plans/2026',
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
        self.assertEqual(draft['requested_directory'], '/Plans/2026')
        self.assertEqual(len(draft['elements']), 5)

    def test_generate_sdoc_caches_versioned_artifact(self):
        class Executor:
            cache = {}

        result = GenerateSdoc().execute(
            'plan', None,
            {'children': [text('Plan')]},
            [{'type': 'paragraph', 'children': [text('Content')]}],
            context={}, tool_executor=Executor(), summary='Summary',
        )

        self.assertEqual(result['status'], 'sdoc creation request prepared')
        self.assertEqual(Executor.cache['artifacts'][0]['schema_version'], 1)
        self.assertIn('elements', Executor.cache['artifacts'][0])
        self.assertNotIn('blocks', Executor.cache['artifacts'][0])

    def test_rejects_deferred_element(self):
        with self.assertRaisesRegex(ValueError, 'unsupported element type'):
            validate_sdoc_draft(
                'plan', None, {'children': [text('Plan')]},
                [{'type': 'image'}],
            )

    def test_rejects_internal_reference_token(self):
        with self.assertRaisesRegex(ValueError, 'citation token invalid'):
            validate_sdoc_draft(
                'plan', None, {'children': [text('Plan')]},
                [{'type': 'paragraph', 'children': [text('Source <reference_0>')]}],
            )

    def test_rejects_unknown_element_fields(self):
        with self.assertRaisesRegex(ValueError, 'object fields invalid'):
            validate_sdoc_draft(
                'plan', None, {'children': [text('Plan')]},
                [{'type': 'paragraph', 'children': [text('Content')], 'unexpected': True}],
            )


if __name__ == '__main__':
    unittest.main()
