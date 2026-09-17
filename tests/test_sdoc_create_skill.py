import unittest

from seafile_ai.chat_manager.skills.sdoc_create import GenerateSdoc, validate_sdoc_draft


class SdocCreateSkillTest(unittest.TestCase):
    def test_tool_schema_describes_supported_block_shapes(self):
        parameters = GenerateSdoc.tool['function']['parameters']
        block_schemas = parameters['properties']['blocks']['items']['oneOf']

        self.assertFalse(parameters['additionalProperties'])
        self.assertEqual(parameters['properties']['blocks']['maxItems'], 200)
        self.assertEqual(len(block_schemas), 6)
        self.assertTrue(all(schema['additionalProperties'] is False for schema in block_schemas))

    def test_accepts_common_blocks_and_preserves_directory(self):
        draft = validate_sdoc_draft(
            'release-plan',
            '/Plans/2026',
            'Release plan',
            'A release plan based on the conversation.',
            [
                {'type': 'heading', 'level': 1, 'text': 'Milestones'},
                {'type': 'paragraph', 'text': 'Prepare the release.'},
                {'type': 'task_list', 'items': ['Review', 'Publish']},
                {'type': 'table', 'headers': ['Task'], 'rows': [['Review']]},
            ],
        )

        self.assertEqual(draft['requested_directory'], '/Plans/2026')
        self.assertEqual(draft['file_name'], 'release-plan')
        self.assertEqual(len(draft['blocks']), 4)

    def test_rejects_unsupported_blocks(self):
        with self.assertRaisesRegex(ValueError, 'unsupported block type'):
            validate_sdoc_draft(
                'plan',
                None,
                'Plan',
                'Summary',
                [{'type': 'image', 'url': 'https://example.com/image.png'}],
            )

    def test_rejects_unknown_block_fields(self):
        with self.assertRaisesRegex(ValueError, 'unsupported fields'):
            validate_sdoc_draft(
                'plan',
                None,
                'Plan',
                'Summary',
                [{'type': 'paragraph', 'text': 'Content', 'url': 'https://example.com'}],
            )

    def test_normalizes_missing_directory_to_none(self):
        draft = validate_sdoc_draft(
            'plan',
            '  ',
            'Plan',
            'Summary',
            [{'type': 'paragraph', 'text': 'Content'}],
        )

        self.assertIsNone(draft['requested_directory'])

    def test_splits_a_complete_file_path(self):
        draft = validate_sdoc_draft(
            '/Plans/2026/release-plan.sdoc',
            None,
            'Plan',
            'Summary',
            [{'type': 'paragraph', 'text': 'Content'}],
        )

        self.assertEqual(draft['requested_directory'], '/Plans/2026')
        self.assertEqual(draft['file_name'], 'release-plan.sdoc')
