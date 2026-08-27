import os
import logging
import re
import base64
import json
import unicodedata

from seafile_ai.utils.constants import LLM_INPUT_CHARACTERS_LIMIT, SUMMARY_WORD_LIMIT, WritingType, MODEL_REASONING_TIER
from seafile_ai.utils import InvalidWritingTypeException, get_file_content_by_seafobj, parse_file, FormatNotSupportedException, get_file_ext, \
    resize_image_binary, is_pdf
from seafile_ai.utils.constants import LANGUAGE, EXTRACT_TEXT_SUPPORTED_IMAGES
from seafile_ai.utils.icon_constants import WIKI_ICON_MANIFEST
from seafile_ai.config import AI_UTILS_TIER
from seafile_ai.utils.llm_api import get_llm_client_by_model_tier

logger = logging.getLogger(__name__)


SDOC_REVIEW_MAX_BLOCKS_PER_CHUNK = 10
SDOC_REVIEW_MAX_PAYLOAD_CHARACTERS_PER_CHUNK = 6000
# A review that spans more than one maximum-size chunk needs a global brief
# so terminology and tone remain consistent between chunks.
SDOC_REVIEW_BRIEF_BLOCK_THRESHOLD = SDOC_REVIEW_MAX_BLOCKS_PER_CHUNK
REVISION_BRIEF_REQUIRED_STRING_FIELDS = (
    'goal', 'tone', 'length', 'heading_strategy', 'do_not_modify',
)


class ReviewScopeAmbiguousError(ValueError):
    def __init__(self, candidates):
        super().__init__('review scope is ambiguous')
        self.candidates = candidates


class ReviewPayloadTooLargeError(ValueError):
    pass

SECTION_NUMBER_PREFIX_PATTERNS = (
    r'^\s*\d+(?:\.\d+)*(?:\s*[.、:：\-]\s*|\s+)',
    r'^\s*[（(]?\s*[一二三四五六七八九十百零]+\s*[）)]?\s*[.、:：\-]\s*',
    r'^\s*第\s*[0-9一二三四五六七八九十百零]+\s*[章节篇部分]\s*[.、:：\-]?\s*',
)
SECTION_NUMBER_TOKEN_PATTERNS = (
    r'^\s*(\d+(?:\.\d+)*)(?:\s*[.、:：\-]\s*|\s+)',
    r'^\s*[（(]?\s*([一二三四五六七八九十百零]+)\s*[）)]?\s*[.、:：\-]\s*',
    r'^\s*第\s*([0-9一二三四五六七八九十百零]+)\s*[章节篇部分]',
)
SECTION_QUOTE_PATTERN = re.compile(r'[“"\'「『《]([^”"\'」』》]{2,80})[”"\'」』》]')


class TextProcessingManager:
    def __init__(self, app, llm_type):
        self.app = app
        self.llm_type = llm_type

    def _generate_summary_text(self, file_name, content, context):
        file_ext = get_file_ext(file_name)
        if file_ext == '.pptx':
            prompt = 'You are a PowerPoint summarizer. You will receive a text version of the PowerPoint slides. Your task is to extract the main points and generate a summary that is concise, clear, and focused on the key elements of the content. - Requirement: **Attention The output language is the same as the input PPT main contentlanguage.(If there are Chinese characters, then it is Chinese.)**'
        else:
            prompt = f'You are a document summarization expert. I need you to generate a concise summary of a document in 2-3 sentences, within {SUMMARY_WORD_LIMIT} words. The summary should capture the main points and themes of the document clearly and effectively. The summary should start with a phrase that introduces the document, such as "This document introduces..." or "The document describes...", in the same language as the input. Do not include any Markdown. The output language is the same as the input language. If it seems there is no content provided for summarization, just output word: None'
        return self._gen_doc_summary(content, prompt, context)

    def generate_summary(self, repo_id, obj_id, path, context):
        file_name = os.path.basename(path)
        content = parse_file(file_name, repo_id, obj_id)

        if content:
            summary_text = self._generate_summary_text(file_name, content[:LLM_INPUT_CHARACTERS_LIMIT], context)
        else:
            summary_text = None

        return summary_text if summary_text not in ['None', 'none', None] else ''

    def _gen_doc_summary(self, content, prompt, context):
        system_prompt = {"role": "system", "content": prompt}
        user_prompt = {"role": "user", "content": 'Summarize the following content' + content}
        messages = [system_prompt, user_prompt]
        tier = AI_UTILS_TIER.get('generate_summary', MODEL_REASONING_TIER.LOW.value)
        llm = get_llm_client_by_model_tier(self.app.data_logger, tier)
        summary = llm.run(messages, context)
        return summary

    def doc_tags(self, repo_id, obj_id, path, candidate_tags, context):
        file_name = os.path.basename(path)
        doc_content = parse_file(file_name, repo_id, obj_id)

        if not doc_content:
            return None

        system_content = f'''
            You are a key phrase extractor. I will provide you with a document in Markdown format and a set of reference phrases. You need to complete two tasks in sequence:
            1、Key Phrase Extraction: Identify a set of up to 10 key phrases from the document. Each key phrase should consist of at most three words, and there should be no semantic overlap between the phrases. The phrases must be common and appear in the document.
            2、Semantic Similarity and Replacement: For each key phrase identified in task 1, calculate its semantic similarity with each reference phrase. If the similarity exceeds 0.9, replace the key phrase with the corresponding reference phrase.
            Finally, output the resulting key phrases, separated by commas. Do not include anything other than the key phrases and commas.
            Reference phrases: {','.join(candidate_tags)}
        '''

        system_prompt = {
            "role": "system",
            "content": system_content
        }
        user_prompt = {
            "role": "user",
            "content": doc_content
        }
        messages = [system_prompt, user_prompt]

        tier = AI_UTILS_TIER.get('doc_tags', MODEL_REASONING_TIER.LOW.value)
        res = get_llm_client_by_model_tier(self.app.data_logger, tier).run(messages, context)
        tags = re.split(r'[，,]', res)
        return [tag.strip() for tag in tags if tag.strip()]

    def translate(self, text, lang, context):
        system_content = f'''
            You are a translation expert who is proficient in multiple languages. Please complete the following translation task: divide the input text into segments according to line breaks, translate each segment into {LANGUAGE[lang]} in turn, concatenate each translated segment using the original line breaks, and finally directly output the concatenated translation result. The format of the translation result, such as line breaks, markdown format, etc., must be exactly the same as the input text. If the input is {LANGUAGE[lang]}, just output it directly. Remember to only translate the input and do not answer any questions.
        '''

        system_prompt = {
            "role": "system",
            "content": system_content
        }
        user_prompt = {
            "role": "user",
            "content": text
        }
        messages = [system_prompt, user_prompt]

        tier = AI_UTILS_TIER.get('translate', MODEL_REASONING_TIER.LOW.value)
        res = get_llm_client_by_model_tier(self.app.data_logger, tier).run(messages, context)
        return res

    def writing_assistant(self, text, custom_prompt, writing_type, context):
        prefix = 'You are an sdoc editor assistant.'
        if custom_prompt:
            system_content = prefix + custom_prompt
        else:
            system_content = self.get_predefined_prompt(prefix, writing_type)

        system_content += 'No need to interact with the user, just output the results directly.'

        system_prompt = {
            "role": "system",
            "content": system_content
        }
        user_prompt = {
            "role": "user",
            "content": text
        }
        messages = [system_prompt, user_prompt]

        tier = AI_UTILS_TIER.get('writing_assistant', MODEL_REASONING_TIER.MEDIUM.value)
        res = get_llm_client_by_model_tier(self.app.data_logger, tier).run(messages, context)
        return res

    def sdoc_review(self, prompt, document_context, context):
        """Generate a structured list of suggestions, chunked for long documents.

        Kept for backward compatibility and for documents that fit a single
        chunk. The progressive flow (Seahub orchestration) uses
        ``sdoc_review_plan`` + ``sdoc_review_chunk`` instead.

        ``document_context`` is the immutable Document Context projection built
        by SDoc Server: an object with ``snapshot_id``, ``file_uuid``,
        ``document_incarnation``, ``exact_sdoc_version``, ``projection_version``,
        ``outline`` and ``blocks``. Each block exposes ``block_id``,
        ``text_node_id``, ``type``, ``ancestor_path``, ``before_leaf_text`` and a
        ``supported`` flag. The model only returns semantic fields; canonical
        hashes and item ids are assigned by Seahub/SDoc Server, never by the model.
        """
        _section_titles, _target_section_ids, blocks, lists = self._collect_blocks(prompt, document_context)
        if not blocks:
            return {'items': []}

        chunks = self._chunk_blocks(blocks, lists)
        brief = None
        if len(chunks) > 1:
            outline = (document_context or {}).get('outline') or []
            brief = self._generate_revision_brief(prompt, outline, blocks, context)
            if not self._is_valid_revision_brief(brief):
                raise ValueError('revision brief invalid')
        items = []
        for chunk_index, chunk in enumerate(chunks):
            chunk_lists = self._lists_for_chunk(lists, chunks, chunk_index)
            items.extend(self._generate_items(prompt, chunk, chunk_lists, brief, context))
        return {'items': self._dedup_items(items)}

    def sdoc_review_plan(self, prompt, document_context, context):
        """Return the revision brief and chunk plan for a progressive review.

        The plan is deterministic: same document context + prompt produce the
        same chunk list. ``chunk_index`` is stable across the plan and each
        subsequent ``sdoc_review_chunk`` call.
        """
        blocks, _lists, chunks = self.sdoc_review_chunk_manifest(prompt, document_context)
        brief = None
        if len(chunks) > 1:
            outline = (document_context or {}).get('outline') or []
            brief = self._generate_revision_brief(prompt, outline, blocks, context)
            if not self._is_valid_revision_brief(brief):
                raise ValueError('revision brief invalid')
        return {
            'brief': brief,
            'chunks': [
                {'chunk_index': index, 'block_ids': [block.get('block_id') for block in chunk]}
                for index, chunk in enumerate(chunks)
            ],
        }

    def sdoc_review_chunk(self, prompt, document_context, brief, chunk_index, context):
        """Generate suggestions for a single chunk of the document.

        ``brief`` is the revision brief produced by ``sdoc_review_plan`` (may be
        None for single-chunk documents). ``chunk_index`` must be a valid index
        from the plan.
        """
        blocks, lists, chunks = self.sdoc_review_chunk_manifest(prompt, document_context)
        if len(chunks) > 1 and not self._is_valid_revision_brief(brief):
            raise ValueError('brief invalid')
        if chunk_index < 0 or chunk_index >= len(chunks):
            raise ValueError('chunk_index out of range')
        chunk_lists = self._lists_for_chunk(lists, chunks, chunk_index)
        return {'items': self._generate_items(
            prompt, chunks[chunk_index], chunk_lists, brief, context)}

    def sdoc_review_chunk_manifest(self, prompt, document_context):
        """Return the deterministic block/list/chunk manifest without invoking a model."""
        _section_titles, _target_section_ids, blocks, lists = self._collect_blocks(prompt, document_context)
        return blocks, lists, self._chunk_blocks(blocks, lists)

    def sdoc_review_scope(self, prompt, document_context):
        """Resolve an immutable, model-independent review scope."""
        section_titles, target_section_ids, blocks, lists = self._collect_blocks(prompt, document_context)
        allowed_block_ids = set(target_section_ids)
        if not target_section_ids:
            allowed_block_ids.update(section_titles.keys())
        allowed_block_ids.update(block.get('block_id') for block in blocks if block.get('block_id'))
        allowed_block_ids.update(list_node.get('block_id') for list_node in lists if list_node.get('block_id'))
        allowed_text_targets = [
            {'block_id': block.get('block_id'), 'text_node_id': block.get('text_node_id')}
            for block in blocks
            if block.get('block_id') and block.get('text_node_id')
        ]
        if target_section_ids:
            scope_summary = ', '.join(
                str(section_titles.get(section_id) or section_id)
                for section_id in sorted(target_section_ids))
        else:
            scope_summary = 'Whole document'
        return {
            'allowed_block_ids': sorted(allowed_block_ids),
            'allowed_text_targets': sorted(
                allowed_text_targets,
                key=lambda target: (target['block_id'], target['text_node_id'])),
            'scope_summary': scope_summary,
        }

    @staticmethod
    def _is_valid_revision_brief(brief):
        if not isinstance(brief, dict):
            return False
        if any(not isinstance(brief.get(field), str) or not brief[field].strip()
               for field in REVISION_BRIEF_REQUIRED_STRING_FIELDS):
            return False
        terminology = brief.get('terminology')
        return isinstance(terminology, list) and all(
            isinstance(term, str) and term.strip() for term in terminology)

    @staticmethod
    def _normalize_section_name(value):
        value = unicodedata.normalize('NFKC', value or '').strip().casefold()
        value = value.strip('“”"\'「」『』《》')
        return re.sub(r'\s+', ' ', value).strip()

    @classmethod
    def _section_aliases(cls, title):
        normalized_title = cls._normalize_section_name(title)
        aliases = {normalized_title} if normalized_title else set()
        unnumbered_title = unicodedata.normalize('NFKC', title or '')
        for pattern in SECTION_NUMBER_PREFIX_PATTERNS:
            updated_title = re.sub(pattern, '', unnumbered_title, count=1)
            if updated_title != unnumbered_title:
                unnumbered_title = updated_title
                break
        normalized_unnumbered_title = cls._normalize_section_name(unnumbered_title)
        if normalized_unnumbered_title:
            aliases.add(normalized_unnumbered_title)
        return aliases

    @staticmethod
    def _section_number_aliases(title):
        normalized_title = unicodedata.normalize('NFKC', title or '').strip().casefold()
        aliases = set()
        for pattern in SECTION_NUMBER_TOKEN_PATTERNS:
            match = re.match(pattern, normalized_title)
            if not match:
                continue
            number = match.group(1).replace(' ', '')
            if number:
                aliases.add(number)
                aliases.add('第%s章' % number)
            break
        return aliases

    @classmethod
    def _prompt_targets_section(cls, prompt, title):
        normalized_prompt = cls._normalize_section_name(prompt)
        aliases = cls._section_aliases(title)
        number_aliases = cls._section_number_aliases(title)
        quoted_names = {
            cls._normalize_section_name(match)
            for match in SECTION_QUOTE_PATTERN.findall(prompt or '')
        }
        if aliases.intersection(quoted_names):
            return True
        for alias in number_aliases:
            if alias.startswith('第') and alias in normalized_prompt:
                return True
            if re.search(r'(?<![\d.])%s(?![\d.])' % re.escape(alias), normalized_prompt):
                return True
        for alias in aliases:
            if len(alias) >= 4 and alias in normalized_prompt:
                return True
            if any(f'{alias}{suffix}' in normalized_prompt for suffix in ('章节', '章', '节', 'section', 'chapter')):
                return True
        return False

    @staticmethod
    def _has_unmatched_explicit_section_scope(prompt):
        normalized_prompt = unicodedata.normalize('NFKC', prompt or '').casefold()
        if any(marker in normalized_prompt for marker in (
                '全文', '整篇', '整个文档', '所有章节', '全部章节', '各章节',
                'whole document', 'entire document', 'all sections')):
            return False
        if any(marker in normalized_prompt for marker in (
                '章节层级', '章节结构', '标题层级',
                'chapter structure', 'section structure', 'heading hierarchy')):
            return False
        has_scope_word = any(marker in normalized_prompt for marker in (
            '章节', '章内', '节内', '小节', '标题下', '标题中', '部分内容',
            'section', 'chapter', 'under the heading',
        ))
        has_numbered_scope = bool(re.search(
            r'第\s*[0-9一二三四五六七八九十百零]+\s*[章节篇部分]', normalized_prompt))
        return has_scope_word or has_numbered_scope

    @staticmethod
    def _is_all_sections_request(prompt):
        normalized_prompt = unicodedata.normalize('NFKC', prompt or '').casefold()
        return any(marker in normalized_prompt for marker in (
            '全文', '整篇', '整个文档', '所有章节', '全部章节', '各章节',
            'whole document', 'entire document', 'all sections',
        ))

    @staticmethod
    def _belongs_to_target_section(node, target_section_ids):
        if not target_section_ids:
            return True
        if node.get('section_id') in target_section_ids:
            return True
        return any(
            isinstance(entry, dict)
            and str(entry.get('type', '')).startswith('header')
            and entry.get('id') in target_section_ids
            for entry in (node.get('ancestor_path') or [])
        )

    @staticmethod
    def _scope_section_id(node, target_section_ids):
        if target_section_ids:
            if node.get('section_id') in target_section_ids:
                return node.get('section_id')
            for entry in node.get('ancestor_path') or []:
                if isinstance(entry, dict) and entry.get('id') in target_section_ids:
                    return entry.get('id')
        return node.get('section_id')

    def _collect_blocks(self, prompt, document_context):
        section_titles = {}
        if isinstance(document_context, dict):
            for header in document_context.get('outline') or []:
                if isinstance(header, dict) and header.get('block_id'):
                    section_titles[header.get('block_id')] = header.get('text')

        # Deterministic scope resolution: only edit blocks whose section header
        # is named in the request. When no header is named, fall back to all
        # supported blocks.
        target_section_ids = set()
        matching_headers = []
        if isinstance(document_context, dict):
            for header in document_context.get('outline') or []:
                text = (header.get('text') or '').strip()
                if len(text) >= 2 and self._prompt_targets_section(prompt, text):
                    target_section_ids.add(header.get('block_id'))

                    matching_headers.append({
                        'block_id': header.get('block_id'),
                        'text': text,
                    })

        if len(matching_headers) > 1 and not self._is_all_sections_request(prompt):
            raise ReviewScopeAmbiguousError(matching_headers)

        if not target_section_ids and self._has_unmatched_explicit_section_scope(prompt):
            raise ValueError('target section not found')

        blocks = []
        if isinstance(document_context, dict):
            for block in document_context.get('blocks') or []:
                if not isinstance(block, dict) or not block.get('supported'):
                    continue
                if not self._belongs_to_target_section(block, target_section_ids):
                    continue
                scope_section_id = self._scope_section_id(block, target_section_ids)
                blocks.append({
                    'block_id': block.get('block_id'),
                    'text_node_id': block.get('text_node_id'),
                    'type': block.get('type'),
                    'section_id': scope_section_id,
                    'section': section_titles.get(block.get('section_id')),
                    'scope_section': section_titles.get(scope_section_id),
                    'before_leaf_text': block.get('before_leaf_text'),
                    'ancestor_path': block.get('ancestor_path') or [],
                })
        lists = []
        if isinstance(document_context, dict):
            for list_node in document_context.get('lists') or []:
                if not isinstance(list_node, dict) or not list_node.get('block_id'):
                    continue
                section_id = None
                for entry in reversed(list_node.get('ancestor_path') or []):
                    if isinstance(entry, dict) and str(entry.get('type', '')).startswith('header'):
                        section_id = entry.get('id')
                        break
                scoped_list_node = dict(list_node)
                scoped_list_node['section_id'] = section_id
                if not self._belongs_to_target_section(scoped_list_node, target_section_ids):
                    continue
                lists.append({
                    'block_id': list_node.get('block_id'),
                    'type': list_node.get('type'),
                    'items': list_node.get('items') or [],
                    'section_id': self._scope_section_id(scoped_list_node, target_section_ids),
                    'section': section_titles.get(section_id),
                })
        return section_titles, target_section_ids, blocks, lists

    @staticmethod
    def _review_block_payload_size(block):
        model_block = {
            'block_id': block.get('block_id'),
            'text_node_id': block.get('text_node_id'),
            'type': block.get('type'),
            'section': block.get('section'),
            'scope_section': block.get('scope_section'),
            'before_leaf_text': block.get('before_leaf_text'),
        }
        return len(json.dumps(model_block, ensure_ascii=False))

    @staticmethod
    def _review_list_payload_size(list_node):
        model_list = {
            'block_id': list_node.get('block_id'),
            'type': list_node.get('type'),
            'items': list_node.get('items') or [],
            'section': list_node.get('section'),
        }
        return len(json.dumps(model_list, ensure_ascii=False))

    def _chunk_blocks(self, blocks, lists=None,
                      max_per_chunk=SDOC_REVIEW_MAX_BLOCKS_PER_CHUNK,
                      max_payload_characters=SDOC_REVIEW_MAX_PAYLOAD_CHARACTERS_PER_CHUNK):
        lists = lists or []
        list_payload_sizes = {}
        for list_node in lists:
            section_id = list_node.get('section_id') or '__none__'
            list_payload_sizes[section_id] = (
                list_payload_sizes.get(section_id, 0)
                + self._review_list_payload_size(list_node)
            )

        # Preserve document order while packing adjacent small sections into the
        # same request. Section metadata remains on each block, so semantic
        # boundaries do not require one model call per heading.
        chunks = []
        chunk = []
        payload_size = 0
        sections_with_lists_sent = set()
        for block in blocks:
            section_id = block.get('section_id') or '__none__'
            first_block_for_section = section_id not in sections_with_lists_sent
            section_list_payload_size = list_payload_sizes.get(section_id, 0) if first_block_for_section else 0
            block_payload_size = self._review_block_payload_size(block)
            if block_payload_size + section_list_payload_size > max_payload_characters:
                raise ReviewPayloadTooLargeError(
                    'review scope contains a block that exceeds the payload limit')
            exceeds_limit = chunk and (
                len(chunk) >= max_per_chunk or
                payload_size + section_list_payload_size + block_payload_size > max_payload_characters
            )
            if exceeds_limit:
                chunks.append(chunk)
                chunk = []
                payload_size = 0
            if first_block_for_section:
                payload_size += section_list_payload_size
                sections_with_lists_sent.add(section_id)
            chunk.append(block)
            payload_size += block_payload_size
        if chunk:
            chunks.append(chunk)
        return chunks

    @staticmethod
    def _lists_for_chunk(lists, chunks, chunk_index):
        if chunk_index < 0 or chunk_index >= len(chunks):
            return []
        section_ids = {block.get('section_id') for block in chunks[chunk_index]}
        previous_section_ids = {
            block.get('section_id')
            for chunk in chunks[:chunk_index]
            for block in chunk
        }
        return [
            list_node for list_node in lists
            if list_node.get('section_id') in section_ids
            and list_node.get('section_id') not in previous_section_ids
        ]

    def _dedup_items(self, items):
        seen = set()
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            key = (item.get('block_id'), item.get('text_node_id'), item.get('kind'))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _generate_revision_brief(self, prompt, outline, blocks, context):
        system_prompt = {
            'role': 'system',
            'content': (
                'You are an SDoc writing review strategist. Return exactly one JSON object and '
                'no Markdown. Produce a concise revision brief to keep edits consistent across '
                'the whole document. The object must be: {"goal":"...","tone":"...","length":"...",'
                '"terminology":["..."],"heading_strategy":"...","do_not_modify":"..."}. '
                'Answer in the same language as the user request.'
            )
        }
        user_prompt = {
            'role': 'user',
            'content': json.dumps({'request': prompt, 'outline': outline, 'block_count': len(blocks)}, ensure_ascii=False),
        }
        content = self.app.llm_api.run([system_prompt, user_prompt], context, response_format={'type': 'json_object'})
        if not isinstance(content, str):
            return None
        try:
            brief = json.loads(content)
        except ValueError:
            return None
        return brief if isinstance(brief, dict) else None

    def _generate_items(self, prompt, blocks, lists, brief, context):
        system_prompt = {
            'role': 'system',
            'content': (
                'You are an SDoc writing reviewer. Return exactly one JSON object and no Markdown. '
                'Suggest edits only for the supplied blocks. Each block has a "section" field naming the '
                'nearest chapter/section and a "scope_section" field naming the resolved requested '
                'ancestor. The supplied blocks are the authoritative edit scope and may include '
                'subsections; never invent or edit blocks outside this input. '
                'Four kinds of edits are supported: '
                '(1) "replace_block_text" for rewriting a block\'s text; '
                '(2) "set_block_type" for changing a paragraph to a heading (header1-header6) or '
                'changing a heading level, only when the request asks for heading-level changes; '
                '(3) "set_list_type" for converting an existing list between ordered_list and '
                'unordered_list, only when the request asks for list conversion; '
                '(4) "replace_table_cell_text" for rewriting a table cell\'s text, using block_type '
                '"table_cell" with the cell\'s block_id and text_node_id. '
                'Use only block_id, text_node_id, type and before_leaf_text supplied in the document. '
                'Do not invent ids. The object must be: {"items":['
                '{"kind":"replace_block_text","block_id":"...","text_node_id":"...","block_type":"...","before_leaf_text":"...","after_text":"...","rationale":"..."} '
                'or {"kind":"set_block_type","block_id":"...","block_type":"...","after_type":"header2","rationale":"..."} '
                'or {"kind":"set_list_type","block_id":"...","block_type":"ordered_list","after_type":"unordered_list","rationale":"..."} '
                'or {"kind":"replace_table_cell_text","block_id":"...","text_node_id":"...","block_type":"table_cell","before_leaf_text":"...","after_text":"...","rationale":"..."}'
                ']}. If no change is needed, omit it. Never output Slate paths or operations.'
            )
        }
        model_blocks = [{
            'block_id': block.get('block_id'),
            'text_node_id': block.get('text_node_id'),
            'type': block.get('type'),
            'section': block.get('section'),
            'scope_section': block.get('scope_section'),
            'before_leaf_text': block.get('before_leaf_text'),
        } for block in blocks]
        user_content = {'request': prompt, 'blocks': model_blocks, 'lists': lists}
        if brief:
            user_content['revision_brief'] = brief
        user_prompt = {
            'role': 'user',
            'content': json.dumps(user_content, ensure_ascii=False),
        }
        content = self.app.llm_api.run([system_prompt, user_prompt], context, response_format={'type': 'json_object'})
        if not isinstance(content, str):
            raise ValueError('The model returned an invalid review suggestion.')
        try:
            result = json.loads(content)
        except ValueError as error:
            raise ValueError('The model returned invalid review JSON.') from error
        if not isinstance(result, dict) or not isinstance(result.get('items'), list):
            raise ValueError('The model returned an invalid review suggestion.')
        return result.get('items') or []

    def sdoc_analyze(self, prompt, document_context, context):
        """Generate a plain-text analysis of the document for mixed-intent requests."""
        section_titles = {}
        if isinstance(document_context, dict):
            for header in document_context.get('outline') or []:
                if isinstance(header, dict) and header.get('block_id'):
                    section_titles[header.get('block_id')] = header.get('text')

        blocks = []
        if isinstance(document_context, dict):
            for block in document_context.get('blocks') or []:
                if not isinstance(block, dict) or not block.get('supported'):
                    continue
                blocks.append({
                    'block_id': block.get('block_id'),
                    'type': block.get('type'),
                    'section': section_titles.get(block.get('section_id')),
                    'before_leaf_text': block.get('before_leaf_text'),
                })

        system_prompt = {
            'role': 'system',
            'content': (
                'You are an SDoc document analyst. Provide a concise plain-text analysis of the '
                'document based on the user request. Do not return JSON, edit suggestions or Slate '
                'operations. Answer in the same language as the user request.'
            )
        }
        user_prompt = {
            'role': 'user',
            'content': json.dumps({'request': prompt, 'blocks': blocks}, ensure_ascii=False),
        }
        content = self.app.llm_api.run([system_prompt, user_prompt], context)
        if not isinstance(content, str) or not content.strip():
            raise ValueError('The model returned no analysis.')
        return content.strip()

    def get_predefined_prompt(self, prefix, writing_type):
        if writing_type == WritingType.ASK:
            predefined_prompt = prefix + 'Please briefly answer the questions asked.'
        else:
            predefined_prompt = prefix + 'You are good at completing various writing auxiliary tasks. Your task is as follows:'
            if writing_type == WritingType.CONTINUE_WRITING:
                predefined_prompt += 'Please continue writing the input sentence. If the input is a complete sentence, please continue writing a sentence based on semantics. If not, please complete the writing of the sentence. The output sentence must start with the input sentence.'
            elif writing_type == WritingType.MORE_FLUENT:
                predefined_prompt += 'Please improve the input sentence to make it more fluent. This improvement cannot change the meaning and tone of the input sentence.'
            elif writing_type == WritingType.MORE_DETAILS:
                predefined_prompt += 'I give you a sentence. Please understand its meaning deeply and expand its content. This expansion cannot change the meaning and tone of the input sentence.'
            elif writing_type == WritingType.MORE_CONCISE:
                predefined_prompt += 'Please refine the input sentence to make it more concise and shorter.'
            elif writing_type == WritingType.MORE_VIVID:
                predefined_prompt += 'Please optimize the input sentence to make it more lively. This optimization cannot change the meaning and tone of the sentence.'
            else:
                raise InvalidWritingTypeException(f'Invalid writing_type: {writing_type}')

            predefined_prompt += 'All input is your writing material, please do not output any answers or responses to the input.'

        return predefined_prompt

    def extract_text(self, repo_id, obj_id, file_name, context):
        if not is_pdf(file_name) and get_file_ext(file_name) not in EXTRACT_TEXT_SUPPORTED_IMAGES:
            raise FormatNotSupportedException

        if is_pdf(file_name):
            return parse_file(file_name, repo_id, obj_id)

        file_content = get_file_content_by_seafobj(repo_id, obj_id)
        image = resize_image_binary(file_content, 'jpeg', 512)
        encode_img = base64.b64encode(image).decode('utf-8')
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract the text information in the image. If there is text information, "
                                "only return the text information. If there is no text information, return an empty string."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{encode_img}"
                        }
                    }
                ],
            }
        ]
        tier = AI_UTILS_TIER.get('ocr', MODEL_REASONING_TIER.LOW.value)
        extracted_text = get_llm_client_by_model_tier(self.app.data_logger, tier).run(messages, context)

        if not extracted_text:
            return ''

        return extracted_text.strip()

    def search_icons(self, query, count, context):
        icons_list_str = ', '.join(WIKI_ICON_MANIFEST)

        system_content = f'''
            You are an icon selection expert. I will provide you with a query term and a list of available icons.
            Your task is to select exactly {count} icons that best match the semantic meaning of the query.
            First, select the most relevant icons. If there aren't enough highly relevant icons,
            also include secondarily related ones to reach the required count.

            Rules:
            1. Return exactly {count} icon names from the list
            2. Only return the icon names, separated by commas
            3. Do not include any explanation or additional text
            4. Must return {count} icons total, even if some are only secondarily related

            Available icons: {icons_list_str}
        '''

        system_prompt = {
            "role": "system",
            "content": system_content
        }
        user_prompt = {
            "role": "user",
            "content": f"Query: {query}\n\nPlease select {count} icons that best match this query. You must return exactly {count} icons."
        }
        messages = [system_prompt, user_prompt]

        try:
            tier = AI_UTILS_TIER.get('search_icons', MODEL_REASONING_TIER.LOW.value)
            res = get_llm_client_by_model_tier(self.app.data_logger, tier).run(messages, context)
            icon_names = [name.strip() for name in re.split(r'[，,]', res) if name.strip()]

            valid_icons = set(WIKI_ICON_MANIFEST)
            seen = set()
            matched_icons = []
            for name in icon_names:
                if name in valid_icons and name not in seen:
                    seen.add(name)
                    matched_icons.append(name)

            if len(matched_icons) < count:
                remaining = [icon for icon in WIKI_ICON_MANIFEST if icon not in seen]
                needed = count - len(matched_icons)
                matched_icons.extend(remaining[:needed])

            return matched_icons[:count]
        except Exception as e:
            logger.exception('Failed to search icons: %s', e)
            return WIKI_ICON_MANIFEST[:count]
