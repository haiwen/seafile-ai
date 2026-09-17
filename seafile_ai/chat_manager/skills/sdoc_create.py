import hashlib
import json
import posixpath

from seafile_ai.utils.tools import BasicTool


SDOC_CREATE_PROMPT = """SDoc creation skill:
- The user explicitly requested a new SDoc file. Create one from the current conversation and available sources.
- Use `generate_sdoc` exactly once after gathering any needed information. Do not claim that the file exists until the tool returns success.
- Write the document in the language requested by the user. If none is specified, use the primary language of the latest user request.
- Preserve user-provided filenames, paths, quoted text, product names, and identifiers unless the user asks to translate them.
- Extract `requested_directory` only from the user's current request. Use null if no directory is specified. Never guess a directory from document content, attachments, or search results.
- If the user specifies a complete .sdoc path, split it into `requested_directory` and `file_name`.
- Generate only common text blocks: headings, paragraphs, ordered/unordered lists, task lists, blockquotes, code blocks, dividers, and text tables.
- Do not generate images, attachments, arbitrary JSON, SDoc IDs, Slate operations, version numbers, or HTML.
"""

MAX_BLOCKS = 200
MAX_TEXT_LENGTH = 100000
MAX_TABLE_ROWS = 100
MAX_TABLE_COLUMNS = 20


def _require_string(value, field, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError('%s must be a non-empty string' % field)
    return value.strip()


def validate_sdoc_draft(file_name, requested_directory, title, summary, blocks):
    file_name = _require_string(file_name, 'file_name')
    title = _require_string(title, 'title')
    summary = _require_string(summary, 'summary')
    if requested_directory is not None and not isinstance(requested_directory, str):
        raise ValueError('requested_directory must be a string or null')
    if not isinstance(blocks, list) or not blocks:
        raise ValueError('blocks must be a non-empty array')
    if len(blocks) > MAX_BLOCKS:
        raise ValueError('too many blocks')

    text_length = len(title) + len(summary)
    normalized_blocks = []
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError('block must be an object')
        block_type = block.get('type')
        if block_type in ('heading', 'paragraph', 'blockquote', 'code_block'):
            allowed_keys = {'type', 'text'}
            if block_type == 'heading':
                allowed_keys.add('level')
            if block_type == 'code_block':
                allowed_keys.add('language')
            if set(block) != allowed_keys:
                raise ValueError('block contains unsupported fields')
            text = _require_string(block.get('text'), 'block.text')
            normalized = {'type': block_type, 'text': text}
            if block_type == 'heading':
                level = block.get('level')
                if not isinstance(level, int) or level < 1 or level > 6:
                    raise ValueError('heading.level must be between 1 and 6')
                normalized['level'] = level
            if block_type == 'code_block':
                language = block.get('language', '')
                if language is not None and not isinstance(language, str):
                    raise ValueError('code_block.language must be a string')
                normalized['language'] = language or ''
        elif block_type in ('ordered_list', 'unordered_list', 'task_list'):
            if set(block) != {'type', 'items'}:
                raise ValueError('block contains unsupported fields')
            items = block.get('items')
            if not isinstance(items, list) or not items or not all(isinstance(item, str) and item.strip() for item in items):
                raise ValueError('list.items must be a non-empty string array')
            normalized = {'type': block_type, 'items': [item.strip() for item in items]}
        elif block_type == 'divider':
            if set(block) != {'type'}:
                raise ValueError('block contains unsupported fields')
            normalized = {'type': block_type}
        elif block_type == 'table':
            if set(block) != {'type', 'headers', 'rows'}:
                raise ValueError('block contains unsupported fields')
            headers = block.get('headers')
            rows = block.get('rows')
            if not isinstance(headers, list) or not headers or not all(isinstance(cell, str) for cell in headers):
                raise ValueError('table.headers must be a non-empty string array')
            if len(headers) > MAX_TABLE_COLUMNS or not isinstance(rows, list) or len(rows) > MAX_TABLE_ROWS:
                raise ValueError('table dimensions are invalid')
            if not all(isinstance(row, list) and len(row) == len(headers) and all(isinstance(cell, str) for cell in row) for row in rows):
                raise ValueError('table.rows must match headers')
            normalized = {'type': block_type, 'headers': headers, 'rows': rows}
        else:
            raise ValueError('unsupported block type')
        text_length += len(json.dumps(normalized, ensure_ascii=False))
        normalized_blocks.append(normalized)

    if text_length > MAX_TEXT_LENGTH:
        raise ValueError('document content is too large')
    requested_directory = requested_directory.strip() if isinstance(requested_directory, str) and requested_directory.strip() else None
    normalized_file_name = file_name.replace('\\', '/')
    if requested_directory is None and '/' in normalized_file_name:
        requested_directory = posixpath.dirname(normalized_file_name) or None
        file_name = posixpath.basename(normalized_file_name)
    return {
        'file_name': file_name,
        'requested_directory': requested_directory,
        'title': title,
        'summary': summary,
        'blocks': normalized_blocks,
    }


class GenerateSdoc(BasicTool):
    tool = {
        'type': 'function',
        'function': {
            'name': 'generate_sdoc',
            'description': 'Prepare a new SDoc file from the conversation. Seahub validates the target and creates the file.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'file_name': {'type': 'string'},
                    'requested_directory': {'type': ['string', 'null']},
                    'title': {'type': 'string'},
                    'summary': {'type': 'string'},
                    'blocks': {'type': 'array'},
                },
                'required': ['file_name', 'requested_directory', 'title', 'summary', 'blocks'],
            },
        },
    }

    def execute(self, file_name, requested_directory, title, summary, blocks, context, tool_executor):
        draft = validate_sdoc_draft(file_name, requested_directory, title, summary, blocks)
        action_key = '%s:%s:sdoc-create' % (context.get('session_uuid', ''), context.get('message_id', ''))
        draft['action_id'] = hashlib.sha256(action_key.encode('utf-8')).hexdigest()
        tool_executor.cache['artifacts'] = [{
            'type': 'sdoc_create_request',
            **draft,
        }]
        return {
            'status': 'sdoc draft prepared',
            'file_name': draft['file_name'],
            'requested_directory': draft['requested_directory'],
        }


class SdocCreateSkill:
    name = 'sdoc-create'

    def get_system_prompts(self):
        return [SDOC_CREATE_PROMPT]

    def register_tools(self, tool_executor, context):
        GenerateSdoc().register(tool_executor, context=context)
