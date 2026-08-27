import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_text_processing_manager():
    seafile_ai_module = ModuleType('seafile_ai')

    utils_module = ModuleType('seafile_ai.utils')
    utils_module.InvalidWritingTypeException = type('InvalidWritingTypeException', (Exception,), {})
    utils_module.FormatNotSupportedException = type('FormatNotSupportedException', (Exception,), {})
    utils_module.get_file_content_by_seafobj = Mock()
    utils_module.parse_file = Mock()
    utils_module.get_file_ext = Mock()
    utils_module.resize_image_binary = Mock()
    utils_module.is_pdf = Mock()

    constants_module = ModuleType('seafile_ai.utils.constants')
    constants_module.LLM_INPUT_CHARACTERS_LIMIT = 10000
    constants_module.SUMMARY_WORD_LIMIT = 100
    constants_module.WritingType = SimpleNamespace(
        ASK='ask', CONTINUE_WRITING='continue', MORE_FLUENT='fluent',
        MORE_DETAILS='details', MORE_CONCISE='concise', MORE_VIVID='vivid')
    constants_module.MODEL_REASONING_TIER = SimpleNamespace(
        LOW=SimpleNamespace(value='low'))
    constants_module.LANGUAGE = {}
    constants_module.EXTRACT_TEXT_SUPPORTED_IMAGES = set()

    config_module = ModuleType('seafile_ai.config')
    config_module.AI_UTILS_TIER = {}

    llm_api_module = ModuleType('seafile_ai.utils.llm_api')
    llm_api_module.get_llm_client_by_model_tier = Mock()

    icon_constants_module = ModuleType('seafile_ai.utils.icon_constants')
    icon_constants_module.WIKI_ICON_MANIFEST = []

    spec = importlib.util.spec_from_file_location(
        'test_sdoc_review_manager_module',
        PROJECT_ROOT / 'seafile_ai/text_processing/text_processing_manager.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
            'seafile_ai': seafile_ai_module,
            'seafile_ai.utils': utils_module,
            'seafile_ai.utils.constants': constants_module,
            'seafile_ai.utils.llm_api': llm_api_module,
            'seafile_ai.utils.icon_constants': icon_constants_module,
            'seafile_ai.config': config_module,
    }):
        spec.loader.exec_module(module)
    return module


class SDocReviewChunkingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_text_processing_manager()

    def setUp(self):
        self.manager = self.module.TextProcessingManager(Mock(), 'other')
        self.context = {
            'outline': [
                {'block_id': 'current', 'text': '1. 现状分析'},
                {'block_id': 'current-child', 'text': '1.1 运行问题'},
                {'block_id': 'design', 'text': '4. 设计原则'},
            ],
            'blocks': [
                {
                    'block_id': f'current-{index}', 'text_node_id': f'text-{index}',
                    'section_id': 'current', 'type': 'paragraph', 'supported': True,
                    'before_leaf_text': f'现状段落 {index}',
                }
                for index in range(8)
            ] + [
                {
                    'block_id': 'current-child-1', 'text_node_id': 'current-child-text-1',
                    'section_id': 'current-child', 'type': 'paragraph', 'supported': True,
                    'before_leaf_text': '子章节正文',
                    'ancestor_path': [
                        {'id': 'current', 'type': 'header1'},
                        {'id': 'current-child', 'type': 'header2'},
                    ],
                },
                {
                    'block_id': 'design-1', 'text_node_id': 'design-text-1',
                    'section_id': 'design', 'type': 'paragraph', 'supported': True,
                    'before_leaf_text': '设计原则正文',
                }
            ],
            'lists': [
                {
                    'block_id': 'current-list', 'type': 'unordered_list', 'items': [],
                    'ancestor_path': [{'id': 'current', 'type': 'header1'}],
                },
                {
                    'block_id': 'design-list', 'type': 'ordered_list', 'items': [],
                    'ancestor_path': [{'id': 'design', 'type': 'header1'}],
                },
            ],
        }

    @staticmethod
    def _brief():
        return {
            'goal': 'Improve clarity',
            'tone': 'concise',
            'length': 'preserve length',
            'terminology': ['SDoc'],
            'heading_strategy': 'preserve headings',
            'do_not_modify': 'facts',
        }

    def test_numbered_heading_matches_quoted_unnumbered_title(self):
        _titles, target_ids, blocks, lists = self.manager._collect_blocks(
            '改进“现状分析”章节内容', self.context)

        self.assertEqual(target_ids, {'current'})
        self.assertEqual(len(blocks), 9)
        self.assertEqual([item['block_id'] for item in lists], ['current-list'])

    def test_numbered_chapter_request_matches_a_numbered_heading(self):
        _titles, target_ids, blocks, lists = self.manager._collect_blocks(
            '改进第1章内容', self.context)

        self.assertEqual(target_ids, {'current'})
        self.assertEqual(len(blocks), 9)
        self.assertEqual([item['block_id'] for item in lists], ['current-list'])

    def test_unknown_numbered_chapter_does_not_fall_back_to_the_whole_document(self):
        with self.assertRaisesRegex(ValueError, 'target section not found'):
            self.manager._collect_blocks('改进第9章内容', self.context)

    def test_explicit_unknown_section_does_not_fall_back_to_full_document(self):
        with self.assertRaisesRegex(ValueError, 'target section not found'):
            self.manager._collect_blocks('改进“未知内容”章节', self.context)

    def test_unquoted_unknown_section_does_not_fall_back_to_full_document(self):
        with self.assertRaisesRegex(ValueError, 'target section not found'):
            self.manager._collect_blocks('改进未知内容章节', self.context)

    def test_unknown_subsection_does_not_fall_back_to_full_document(self):
        with self.assertRaisesRegex(ValueError, 'target section not found'):
            self.manager._collect_blocks('改进“不存在的小节”内容', self.context)

    def test_full_document_request_keeps_all_supported_blocks(self):
        _titles, target_ids, blocks, lists = self.manager._collect_blocks(
            '改进全文', self.context)

        self.assertEqual(target_ids, set())
        self.assertEqual(len(blocks), 10)
        self.assertEqual(len(lists), 2)

    def test_chunks_respect_block_limit(self):
        blocks = [
            {'block_id': str(index), 'section_id': 'current', 'before_leaf_text': 'x' * 10}
            for index in range(7)
        ]

        chunks = self.manager._chunk_blocks(
            blocks, max_per_chunk=3, max_payload_characters=10000)

        self.assertEqual([[block['block_id'] for block in chunk] for chunk in chunks], [
            ['0', '1', '2'], ['3', '4', '5'], ['6'],
        ])

    def test_chunks_include_lists_in_payload_budget(self):
        blocks = [
            {'block_id': str(index), 'section_id': 'current', 'before_leaf_text': 'x' * 20}
            for index in range(3)
        ]
        lists = [{
            'block_id': 'list', 'section_id': 'current', 'type': 'unordered_list',
            'items': [{'text': 'x' * 300}],
        }]

        chunks = self.manager._chunk_blocks(
            blocks, lists, max_per_chunk=10, max_payload_characters=600)

        self.assertGreater(len(chunks), 1)

    def test_default_chunk_payload_budget_is_conservative(self):
        blocks = [
            {'block_id': str(index), 'section_id': 'current', 'before_leaf_text': 'x' * 900}
            for index in range(4)
        ]

        chunks = self.manager._chunk_blocks(blocks)

        self.assertEqual([[block['block_id'] for block in chunk] for chunk in chunks], [
            ['0', '1', '2'], ['3'],
        ])

    def test_adjacent_small_sections_share_a_chunk(self):
        blocks = [
            {'block_id': 'a', 'section_id': 'section-a', 'before_leaf_text': '甲'},
            {'block_id': 'b', 'section_id': 'section-b', 'before_leaf_text': '乙'},
            {'block_id': 'c', 'section_id': 'section-c', 'before_leaf_text': '丙'},
        ]

        chunks = self.manager._chunk_blocks(
            blocks, max_per_chunk=10, max_payload_characters=10000)

        self.assertEqual([[block['block_id'] for block in chunk] for chunk in chunks], [
            ['a', 'b', 'c'],
        ])

    def test_section_lists_are_sent_only_with_first_chunk(self):
        _titles, _target_ids, blocks, lists = self.manager._collect_blocks(
            '改进“现状分析”章节内容', self.context)
        chunks = self.manager._chunk_blocks(blocks, lists)

        self.assertEqual(len(chunks), 1)
        self.assertEqual([item['block_id'] for item in self.manager._lists_for_chunk(lists, chunks, 0)], [
            'current-list',
        ])

    def test_small_scoped_review_plan_does_not_generate_a_brief(self):
        self.manager._generate_revision_brief = Mock()

        plan = self.manager.sdoc_review_plan(
            '改进“现状分析”章节内容', self.context, {})

        self.assertEqual(len(plan['chunks']), 1)
        self.assertEqual(sum(len(chunk['block_ids']) for chunk in plan['chunks']), 9)
        self.assertIsNone(plan['brief'])
        self.manager._generate_revision_brief.assert_not_called()

    def test_character_budget_split_requires_a_brief_even_below_block_threshold(self):
        brief = self._brief()
        self.manager._generate_revision_brief = Mock(return_value=brief)
        context = dict(self.context)
        context['blocks'] = [
            {
                'block_id': 'first', 'text_node_id': 'first-text',
                'section_id': 'current', 'type': 'paragraph', 'supported': True,
                'before_leaf_text': '甲' * 3000,
            },
            {
                'block_id': 'second', 'text_node_id': 'second-text',
                'section_id': 'design', 'type': 'paragraph', 'supported': True,
                'before_leaf_text': '乙' * 3000,
            },
        ]
        context['lists'] = []

        plan = self.manager.sdoc_review_plan('改进全文', context, {})

        self.assertEqual(len(plan['chunks']), 2)
        self.assertEqual(plan['brief'], brief)
        self.manager._generate_revision_brief.assert_called_once()

    def test_review_plan_generates_a_brief_above_chunk_limit(self):
        brief = self._brief()
        self.manager._generate_revision_brief = Mock(return_value=brief)
        context = dict(self.context)
        context['blocks'] = self.context['blocks'] + [{
            'block_id': 'extra-1', 'text_node_id': 'extra-text-1',
            'section_id': 'design', 'type': 'paragraph', 'supported': True,
            'before_leaf_text': '额外正文',
        }]

        plan = self.manager.sdoc_review_plan('改进全文', context, {})

        self.assertEqual(sum(len(chunk['block_ids']) for chunk in plan['chunks']), 11)
        self.assertEqual(plan['brief'], brief)
        self.manager._generate_revision_brief.assert_called_once()

    def test_review_plan_generates_a_brief_for_twelve_blocks(self):
        brief = self._brief()
        self.manager._generate_revision_brief = Mock(return_value=brief)
        context = dict(self.context)
        context['blocks'] = self.context['blocks'] + [{
            'block_id': 'extra-1', 'text_node_id': 'extra-text-1',
            'section_id': 'design', 'type': 'paragraph', 'supported': True,
            'before_leaf_text': '额外正文一',
        }, {
            'block_id': 'extra-2', 'text_node_id': 'extra-text-2',
            'section_id': 'design', 'type': 'paragraph', 'supported': True,
            'before_leaf_text': '额外正文二',
        }]

        plan = self.manager.sdoc_review_plan('改进全文', context, {})

        self.assertEqual(sum(len(chunk['block_ids']) for chunk in plan['chunks']), 12)
        self.assertEqual(len(plan['chunks']), 2)
        self.assertEqual(plan['brief'], brief)
        self.manager._generate_revision_brief.assert_called_once()

    def test_chunk_requires_a_brief_above_chunk_limit(self):
        context = dict(self.context)
        context['blocks'] = self.context['blocks'] + [{
            'block_id': 'extra-1', 'text_node_id': 'extra-text-1',
            'section_id': 'design', 'type': 'paragraph', 'supported': True,
            'before_leaf_text': '额外正文',
        }]

        with self.assertRaisesRegex(ValueError, 'brief invalid'):
            self.manager.sdoc_review_chunk('改进全文', context, None, 0, {})

    def test_long_review_rejects_an_incomplete_brief(self):
        context = dict(self.context)
        context['blocks'] = self.context['blocks'] + [{
            'block_id': 'extra-1', 'text_node_id': 'extra-text-1',
            'section_id': 'design', 'type': 'paragraph', 'supported': True,
            'before_leaf_text': '额外正文',
        }]
        self.manager._generate_revision_brief = Mock(return_value={'tone': 'concise'})

        with self.assertRaisesRegex(ValueError, 'revision brief invalid'):
            self.manager.sdoc_review_plan('改进全文', context, {})

    def test_duplicate_section_title_requires_clarification(self):
        context = dict(self.context)
        context['outline'] = self.context['outline'] + [
            {'block_id': 'another-current', 'text': '2. 现状分析'},
        ]

        with self.assertRaises(self.module.ReviewScopeAmbiguousError):
            self.manager.sdoc_review_scope('润色“现状分析”章节', context)

    def test_oversized_first_block_is_rejected(self):
        blocks = [{
            'block_id': 'large', 'section_id': 'current',
            'before_leaf_text': 'x' * 7000,
        }]

        with self.assertRaises(self.module.ReviewPayloadTooLargeError):
            self.manager._chunk_blocks(blocks)

    def test_oversized_first_section_list_context_is_rejected(self):
        blocks = [{
            'block_id': 'small', 'section_id': 'current', 'before_leaf_text': 'small',
        }]
        lists = [{
            'block_id': 'large-list', 'section_id': 'current', 'type': 'unordered_list',
            'items': [{'text': 'x' * 7000}],
        }]

        with self.assertRaises(self.module.ReviewPayloadTooLargeError):
            self.manager._chunk_blocks(blocks, lists)

    def test_review_item_generation_limits_output_size(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': '{"items": []}',
            'finish_reason': 'stop',
        }

        self.manager._generate_items('改进全文', [], [], None, {})

        kwargs = self.manager.app.llm_api.run_with_metadata.call_args.kwargs
        self.assertNotIn('max_tokens', kwargs)
        self.assertIn(
            'at most %d high-value suggestions' % self.module.SDOC_REVIEW_MAX_SUGGESTIONS_PER_CHUNK,
            self.manager.app.llm_api.run_with_metadata.call_args.args[0][0]['content'])

    def test_review_item_generation_accepts_fenced_json(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': 'Here is the requested review:\n```json\n{\"items\": []}\n```',
            'finish_reason': 'stop',
        }

        self.assertEqual(
            self.manager._generate_items('改进全文', [], [], None, {}), [])

    def test_review_item_generation_rejects_noncanonical_suggestion_alias(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': '{"suggestions": []}',
            'finish_reason': 'stop',
        }

        with self.assertRaises(self.module.ReviewModelResponseInvalidError):
            self.manager._generate_items('改进全文', [], [], None, {})

    def test_review_item_generation_rejects_noncanonical_nested_response(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': '{"review": {"changes": []}}',
            'finish_reason': 'stop',
        }
        with self.assertRaises(self.module.ReviewModelResponseInvalidError):
            self.manager._generate_items('改进全文', [], [], None, {})

    def test_review_item_generation_rejects_top_level_list(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': '[]',
            'finish_reason': 'stop',
        }
        with self.assertRaises(self.module.ReviewModelResponseInvalidError):
            self.manager._generate_items('改进全文', [], [], None, {})

    def test_review_item_generation_rejects_nested_single_suggestion(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': '{"output": {"proposal": {"kind": "replace_block_text"}}}',
            'finish_reason': 'stop',
        }

        with self.assertRaises(self.module.ReviewModelResponseInvalidError):
            self.manager._generate_items('改进全文', [], [], None, {})

    def test_review_item_generation_rejects_truncated_completion(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': '{"items":[{"kind":"replace_block_text"',
            'finish_reason': 'length',
        }

        with self.assertRaises(self.module.ReviewModelOutputTruncatedError):
            self.manager._generate_items('改进全文', [], [], None, {})

    def test_review_item_generation_hydrates_canonical_text_target(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': (
                '{"items":[{"kind":"replace_block_text","block_id":"block-1",'
                '"after_text":"Improved text","rationale":"Clearer"}]}'),
            'finish_reason': 'stop',
        }
        blocks = [{
            'block_id': 'block-1', 'text_node_id': 'text-1', 'type': 'paragraph',
            'before_leaf_text': 'Original text',
        }]

        self.assertEqual(
            self.manager._generate_items('Improve this', blocks, [], None, {}), [{
                'kind': 'replace_block_text', 'block_id': 'block-1',
                'after_text': 'Improved text', 'rationale': 'Clearer',
                'text_node_id': 'text-1', 'block_type': 'paragraph',
                'before_leaf_text': 'Original text',
            }])

    def test_revision_brief_accepts_fenced_json(self):
        self.manager.app.llm_api.run.return_value = (
            '```json\n{\"goal\":\"clarity\",\"tone\":\"concise\",'
            '\"length\":\"preserve\",\"terminology\":[],\"heading_strategy\":\"preserve\",'
            '\"do_not_modify\":\"facts\"}\n```')

        self.assertEqual(self.manager._generate_revision_brief('改进全文', [], [], {}), {
            'goal': 'clarity', 'tone': 'concise', 'length': 'preserve',
            'terminology': [], 'heading_strategy': 'preserve', 'do_not_modify': 'facts',
        })


if __name__ == '__main__':
    unittest.main()
