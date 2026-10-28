import importlib.util
import copy
import json
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
        self.module.get_llm_client_by_model_tier.return_value = self.manager.app.llm_api
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

    def _request_plan(self, ordinal=2, kind='rewrite'):
        return {
            'route': 'review', 'instruction': 'Revise only the second paragraph.',
            'scope': {'kind': 'paragraphs', 'ordinals': [ordinal], 'reference': ''},
            'operation': {'kind': kind, 'old_text': '*' if kind == 'remove_text' else '', 'new_text': '',
                          'coverage': 'selective' if kind == 'rewrite' else 'none',
                          'occurrences': 'all' if kind in ('remove_text', 'replace_text') else 'none'},
            'clarification': '',
        }

    def _understand(self, plan, context=None):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': json.dumps(plan), 'finish_reason': 'stop'}
        return self.manager.understand_sdoc_request(
            '移除第二段中的字符“*”', context or self.context, [], {})

    def test_semantic_selector_binds_only_second_paragraph(self):
        result = self._understand(self._request_plan())
        self.assertEqual(result['scope']['allowed_block_ids'], ['current-1'])

    def test_complete_coverage_survives_scope_binding_and_is_required(self):
        plan = self._request_plan()
        plan['operation']['coverage'] = 'complete'
        result = self._understand(plan)
        self.assertEqual(result['scope']['allowed_text_targets'][0]['operation']['coverage'], 'complete')
        for coverage in [None, 'all', 'none']:
            invalid = self._request_plan()
            invalid['operation']['coverage'] = coverage
            with self.subTest(coverage=coverage), self.assertRaises(self.module.ReviewModelResponseInvalidError):
                self._understand(invalid)

    def test_complete_rewrite_covers_all_chunks_and_rejects_omissions(self):
        context = dict(review_scope_frozen=True, outline=[], lists=[],
                       review_operation=dict(kind='rewrite', coverage='complete', old_text='', new_text='', occurrences='none'),
                       blocks=[dict(block_id='p%d' % i, type='paragraph', supported=True,
                                    before_leaf_text='Original %d' % i) for i in range(5)])
        self.manager._generate_revision_brief = Mock(return_value=self._brief())
        plan = self.manager.sdoc_review_plan('Translate every paragraph', context, {})
        self.assertEqual([len(chunk['block_ids']) for chunk in plan['chunks']], [2, 2, 1])
        delivered = []
        for chunk in plan['chunks']:
            items = [dict(kind='replace_block_text', block_id=id, after_text='Translated', rationale='Translate')
                     for id in chunk['block_ids']]
            self._model_items(items)
            result = self.manager.sdoc_review_chunk('Translate every paragraph', context, plan['brief'], chunk['chunk_index'], {})
            delivered.extend(item['block_id'] for item in result['items'])
            self._model_items(items[:-1])
            with self.assertRaises(self.module.ReviewModelResponseInvalidError):
                self.manager.sdoc_review_chunk('Translate every paragraph', context, plan['brief'], chunk['chunk_index'], {})
        self.assertEqual(delivered, ['p%d' % i for i in range(5)])

    def test_selective_rewrite_can_omit_unchanged_targets(self):
        self._model_items([])
        operation = dict(kind='rewrite', coverage='selective', old_text='', new_text='', occurrences='none')
        self.assertEqual(self.manager._generate_items('Suggest improvements', self._operation_blocks(), [], None, {}, operation), [])

    def test_explicit_insert_requires_one_suggestion(self):
        blocks = self._operation_blocks()[:1]
        operation = dict(kind='insert_block', new_text='header2', old_text='', occurrences='none', placement='before')
        self._model_items([])
        with self.assertRaises(self.module.ReviewModelResponseInvalidError):
            self.manager._generate_items('Insert a heading', blocks, [], None, {}, operation)
        self._model_items([dict(kind='insert_block', block_id='p1', after_type='header2', after_text='Heading', placement='before', rationale='Insert')])
        self.assertEqual(len(self.manager._generate_items('Insert a heading', blocks, [], None, {}, operation)), 1)

    def test_fixed_structure_plans_do_not_generate_writing_briefs(self):
        for kind, destination in [('delete_block', ''), ('set_block_type', 'header2'), ('set_list_type', 'ordered_list')]:
            context = self._type_operation_context()
            context['review_operation'].update(kind=kind, new_text=destination)
            if kind == 'set_list_type':
                context['lists'] = [dict(block_id='l%d' % i, type='unordered_list', items=['Text'],
                                         capabilities={'set_list_type': {'allowed_types': ['ordered_list']}}) for i in range(3)]
                context['blocks'] = []
            self.manager._generate_revision_brief = Mock(side_effect=AssertionError('Unneeded model call'))
            with self.subTest(kind=kind):
                plan = self.manager.sdoc_review_plan('Convert or delete', context, {})
                self.assertGreater(len(plan['chunks']), 1)
                self.assertTrue(self.manager._is_valid_revision_brief(plan['brief']))
                self.manager._generate_revision_brief.assert_not_called()

    def test_missing_paragraph_clarifies_instead_of_expanding_scope(self):
        self.manager.app.llm_api.run_with_metadata.side_effect = [
            {'content': json.dumps(self._request_plan(ordinal=99)), 'finish_reason': 'stop'},
            {'content': json.dumps({'clarification': 'The requested paragraph does not exist.'}),
             'finish_reason': 'stop'},
        ]
        result = self._understand(self._request_plan(ordinal=99))
        self.assertEqual(result['route'], 'clarify')
        self.assertNotIn('scope', result)

    def test_paragraph_count_excludes_list_item_paragraphs(self):
        context = copy.deepcopy(self.context)
        context['blocks'][0]['ancestor_path'] = [{'type': 'list_item', 'id': 'item'}]
        result = self._understand(self._request_plan(), context)
        self.assertEqual(result['scope']['allowed_block_ids'], ['current-2'])

    def test_request_understanding_rejects_boolean_ordinal(self):
        with self.assertRaises(self.module.ReviewModelResponseInvalidError):
            self._understand(self._request_plan(ordinal=True))

    def test_literal_removal_preserves_other_characters_without_model_generation(self):
        context = copy.deepcopy(self.context)
        context['blocks'] = context['blocks'][:1]
        context['blocks'][0]['before_leaf_text'] = '**Keep** 2026.\nNext line.'
        context['lists'] = []
        context['review_scope_frozen'] = True
        context['review_operation'] = self._request_plan(kind='remove_text')['operation']
        result = self.manager.sdoc_review_chunk('Remove * from the second paragraph', context, None, 0, {})
        self.assertEqual(result['items'][0]['after_text'], 'Keep 2026.\nNext line.')
        self.manager.app.llm_api.run_with_metadata.assert_not_called()

    def test_frozen_scope_does_not_reinterpret_missing_section(self):
        context = dict(self.context, review_scope_frozen=True)
        blocks, _, _ = self.manager.sdoc_review_chunk_manifest('修改第九章', context)
        self.assertEqual(len(blocks), len(self.context['blocks']))

    @staticmethod
    def _operation_blocks():
        return [
            {'block_id': 'p1', 'text_node_id': 't1', 'type': 'paragraph',
             'supported': True, 'before_leaf_text': 'old * text'},
            {'block_id': 'c1', 'text_node_id': 't2', 'type': 'table_cell',
             'supported': True, 'before_leaf_text': 'old * cell'},
        ]

    def test_text_operations_use_target_specific_kind(self):
        blocks = self._operation_blocks()
        expected_kinds = ['replace_block_text', 'replace_table_cell_text']
        for kind, old, new in [('remove_text', '*', ''), ('replace_text', 'old', 'new')]:
            operation = dict(kind=kind, old_text=old, new_text=new, occurrences='all')
            with self.subTest(kind=kind):
                items = self.manager._generate_items('Edit text', blocks, [], None, {}, operation)
                self.assertEqual([item['kind'] for item in items], expected_kinds)
                self.assertEqual([item['after_text'] for item in items],
                                 [b['before_leaf_text'].replace(old, new) for b in blocks])
                self.assertEqual([item['text_node_id'] for item in items], ['t1', 't2'])
        self.manager.app.llm_api.run_with_metadata.assert_not_called()

    def _model_items(self, items):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': json.dumps({'items': items}), 'finish_reason': 'stop'}

    def test_rewrite_accepts_target_specific_kinds_and_rejects_invalid_targets(self):
        blocks = self._operation_blocks()
        operation = dict(kind='rewrite', old_text='', new_text='', occurrences='none')
        valid = [dict(kind=kind, block_id=b['block_id'], after_text='Rewritten', rationale='Clarify')
                 for b, kind in zip(blocks, ['replace_block_text', 'replace_table_cell_text'])]
        self._model_items(valid)
        result = self.manager._generate_items('Rewrite', blocks, [], None, {}, operation)
        self.assertEqual([item['kind'] for item in result], [item['kind'] for item in valid])
        self.assertEqual([item['block_type'] for item in result], ['paragraph', 'table_cell'])
        invalid = [
            [dict(valid[0], kind='replace_table_cell_text')],
            [dict(valid[1], kind='replace_block_text')],
            [dict(valid[1], block_id='outside')],
            [valid[1], valid[1]],
            [dict(kind='delete_block', block_id='p1', rationale='Delete')],
        ]
        for items in invalid:
            with self.subTest(items=items), self.assertRaises(self.module.ReviewModelResponseInvalidError):
                self._model_items(items)
                self.manager._generate_items('Rewrite', blocks, [], None, {}, operation)

    @staticmethod
    def _type_operation_context():
        return dict(review_scope_frozen=True, outline=[], lists=[],
                    review_operation=dict(kind='set_block_type', old_text='', new_text='header2', occurrences='none'),
                    blocks=[dict(block_id='p%d' % i, type='paragraph', supported=True,
                                 before_leaf_text='Paragraph %d' % i,
                                 capabilities={'set_block_type': {'allowed_types': ['header2']}})
                            for i in range(5)])

    def test_block_type_chunks_fit_suggestion_budget_and_cover_all_targets(self):
        context = self._type_operation_context()
        self.manager._generate_revision_brief = Mock(return_value=self._brief())
        plan = self.manager.sdoc_review_plan('Convert', context, {})
        self.assertEqual([len(chunk['block_ids']) for chunk in plan['chunks']], [2, 2, 1])
        delivered = []
        for chunk in plan['chunks']:
            self._model_items([dict(kind='set_block_type', block_id=block_id,
                                    after_type='header2', rationale='Convert')
                               for block_id in chunk['block_ids']])
            result = self.manager.sdoc_review_chunk('Convert', context, plan['brief'], chunk['chunk_index'], {})
            delivered.extend(item['block_id'] for item in result['items'])
        self.assertEqual(delivered, [block['block_id'] for block in context['blocks']])
        system_prompt = self.manager.app.llm_api.run_with_metadata.call_args.args[0][0]['content']
        self.assertIn('exactly one set_block_type item', system_prompt)

    def test_block_type_requires_complete_conversion_but_allows_noops(self):
        context = self._type_operation_context()
        blocks = context['blocks'][:2]
        operation = context['review_operation']
        valid = [dict(kind='set_block_type', block_id=b['block_id'], after_type='header2', rationale='Convert')
                 for b in blocks]
        for items in ([], valid[:1]):
            with self.subTest(items=items), self.assertRaises(self.module.ReviewModelResponseInvalidError):
                self._model_items(items)
                self.manager._generate_items('Convert', blocks, [], None, {}, operation)
        self._model_items(valid)
        self.assertEqual(len(self.manager._generate_items('Convert', blocks, [], None, {}, operation)), 2)
        blocks = copy.deepcopy(blocks)
        blocks[1].update(type='header2', capabilities={'set_block_type': {'allowed_types': ['paragraph']}})
        self._model_items(valid[:1])
        self.assertEqual(len(self.manager._generate_items('Convert', blocks, [], None, {}, operation)), 1)
        self._model_items([])
        self.assertEqual(self.manager._generate_items('Convert', blocks[1:], [], None, {}, operation), [])

    def test_block_type_keeps_strict_target_and_destination_checks(self):
        context = self._type_operation_context()
        blocks = context['blocks'][:1]
        blocks[0]['capabilities']['set_block_type']['allowed_types'].append('header3')
        valid = dict(kind='set_block_type', block_id='p0', after_type='header2', rationale='Convert')
        self._model_items([valid])
        self.assertEqual(len(self.manager._generate_items('Convert', blocks, [], None, {}, context['review_operation'])), 1)
        for items in ([dict(valid, block_id='p4')], [dict(valid, after_type='header3')],
                      [dict(valid, after_type='paragraph')], [valid, valid],
                      [dict(kind='replace_block_text', block_id='p0', after_text='Changed', rationale='Rewrite')]):
            with self.subTest(items=items), self.assertRaises(self.module.ReviewModelResponseInvalidError):
                self._model_items(items)
                self.manager._generate_items('Convert', blocks, [], None, {}, context['review_operation'])

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

    def test_semantic_section_binding_includes_descendant_body(self):
        plan = self._request_plan()
        plan['scope'] = dict(kind='section', reference='1. 现状分析', ordinals=[])
        result = self._understand(plan)
        self.assertIn('current-child-1', result['scope']['allowed_block_ids'])
        self.assertNotIn('design-1', result['scope']['allowed_block_ids'])

    def test_missing_semantic_section_does_not_expand_scope(self):
        plan = self._request_plan()
        plan['scope'] = dict(kind='section', reference='missing', ordinals=[])
        self.manager.app.llm_api.run_with_metadata.side_effect = [
            dict(content=json.dumps(plan), finish_reason='stop'),
            dict(content='{"clarification":"Which section?"}', finish_reason='stop')]
        result = self.manager.understand_sdoc_request('Edit a missing section', self.context, [], {})
        self.assertEqual(result['route'], 'clarify')
        self.assertNotIn('scope', result)

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
        blocks = [block for block in blocks if block['section_id'] == 'current']
        lists = [node for node in lists if node['section_id'] == 'current']
        chunks = self.manager._chunk_blocks(blocks, lists, max_per_chunk=2)

        self.assertGreater(len(chunks), 1)
        self.assertEqual([item['block_id'] for item in self.manager._lists_for_chunk(lists, chunks, 0)], [
            'current-list',
        ])
        for index in range(1, len(chunks)):
            self.assertEqual(self.manager._lists_for_chunk(lists, chunks, index), [])

    def test_small_scoped_review_plan_does_not_generate_a_brief(self):
        self.manager._generate_revision_brief = Mock()
        context = dict(self.context, blocks=self.context['blocks'][:-1], lists=self.context['lists'][:1])

        plan = self.manager.sdoc_review_plan(
            '改进“现状分析”章节内容', context, {})

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
        context['outline'] = [
            {'block_id': 'current', 'text': '现状分析'},
            {'block_id': 'another-current', 'text': '现状分析'},
        ]
        plan = self._request_plan()
        plan['scope'] = dict(kind='section', reference='现状分析', ordinals=[])
        with self.assertRaisesRegex(self.module.ReviewTargetResolutionError, 'target_ambiguous'):
            self.manager._bind_request_scope(plan, context, context['blocks'])

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

    def test_review_item_generation_rejects_unknown_kind(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': (
                '{"items":[{"kind":"unknown_kind","block_id":"block-1",'
                '"rationale":"Remove it"}]}'),
            'finish_reason': 'stop',
        }
        with self.assertRaisesRegex(self.module.ReviewModelResponseInvalidError, 'unsupported review suggestion'):
            self.manager._generate_items('Improve this', [dict(block_id='block-1', type='paragraph', before_leaf_text='Text')], [], None, {})

    def test_review_item_generation_rejects_out_of_chunk_target(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': (
                '{"items":[{"kind":"replace_block_text","block_id":"outside",'
                '"after_text":"Changed","rationale":"Clearer"}]}'),
            'finish_reason': 'stop',
        }
        blocks = [{
            'block_id': 'inside', 'text_node_id': 'text-1', 'type': 'paragraph',
            'before_leaf_text': 'Original',
        }]
        with self.assertRaises(self.module.ReviewModelResponseInvalidError):
            self.manager._generate_items('Improve this', blocks, [], None, {})

    def test_review_item_generation_rejects_table_kind_for_paragraph(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': (
                '{"items":[{"kind":"replace_table_cell_text","block_id":"block-1",'
                '"after_text":"Changed","rationale":"Clearer"}]}'),
            'finish_reason': 'stop',
        }
        blocks = [{
            'block_id': 'block-1', 'text_node_id': 'text-1', 'type': 'paragraph',
            'before_leaf_text': 'Original',
        }]
        with self.assertRaises(self.module.ReviewModelResponseInvalidError):
            self.manager._generate_items('Improve this', blocks, [], None, {})

    def test_revision_brief_accepts_fenced_json(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': (
                '```json\n{\"goal\":\"clarity\",\"tone\":\"concise\",'
                '\"length\":\"preserve\",\"terminology\":[],\"heading_strategy\":\"preserve\",'
                '\"do_not_modify\":\"facts\"}\n```'),
            'finish_reason': 'stop',
        }

        self.assertEqual(self.manager._generate_revision_brief('改进全文', [], [], {}), {
            'goal': 'clarity', 'tone': 'concise', 'length': 'preserve',
            'terminology': [], 'heading_strategy': 'preserve', 'do_not_modify': 'facts',
        })

    def test_revision_brief_rejects_truncated_completion(self):
        self.manager.app.llm_api.run_with_metadata.return_value = {
            'content': (
                '{\"goal\":\"clarity\",\"tone\":\"concise\",\"length\":\"preserve\",'
                '\"terminology\":[],\"heading_strategy\":\"preserve\",\"do_not_modify\":\"facts\"}'),
            'finish_reason': 'length',
        }

        with self.assertRaises(self.module.ReviewModelOutputTruncatedError):
            self.manager._generate_revision_brief('改进全文', [], [], {})


if __name__ == '__main__':
    unittest.main()
