import json
import logging
import re
from urllib.parse import urlparse

from seafile_ai.utils.tools import BasicTool

logger = logging.getLogger(__name__)


SDOC_CREATE_PROMPT = """SDoc creation skill:
- The user explicitly requested a new SDoc file. Create one from the current conversation and available sources.
- Use `create_sdoc` after gathering any needed information. It validates and saves a complete SDoc before returning its location.
- Write the document in the requested language, or the primary language of the latest user request.
- Preserve user-provided filenames, paths, quoted text, product names, and identifiers.
- All documents are saved in /AI Generated/ in the current library. Pass a filename, not a directory.
- Use the supported semantic element names and fields exactly. Do not generate IDs, structural nodes, version fields, repository-backed media, or HTML.
- Never place internal `<reference_N>` tokens in SDoc content. If sources are useful, add a normal plain-text Sources section without internal citation tokens.
- Only status `created` means the file exists. Summarize it without repeating its full content; the file card displays its location.
- If status is `unknown`, explain that creation could not be confirmed and ask the user to check /AI Generated/. Never retry creation in this request.
- If status is `failed`, explain that creation failed. Do not claim success.
"""

SCHEMA_VERSION = 1
MAX_ELEMENTS = 200
MAX_TEXT_LENGTH = 100000
MAX_TABLE_ROWS = 100
MAX_TABLE_COLUMNS = 20
MAX_DEPTH = 8
REFERENCE_RE = re.compile(r'<reference_\d+>')
COLOR_RE = re.compile(r'^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$')
MARK_TYPES = {
    'bold': bool, 'italic': bool, 'underline': bool, 'strikethrough': bool,
    'superscript': bool, 'subscript': bool, 'code': bool, 'color': str,
    'highlight_color': str, 'font': str, 'font_size': (int, float),
}
DEFERRED_TYPES = {'image', 'image_block', 'video', 'file_link', 'sdoc_link', 'whiteboard'}
MULTI_COLUMN_TYPES = {
    'paragraph', 'header1', 'header2', 'header3', 'header4', 'header5', 'header6',
    'subtitle', 'blockquote', 'check_list_item', 'code_block', 'ordered_list',
    'unordered_list', 'divider', 'formula',
}


TEXT_SCHEMA = {
    'type': 'object',
    'properties': {
        'type': {'type': 'string', 'enum': ['text']}, 'text': {'type': 'string'},
        'bold': {'type': 'boolean'}, 'italic': {'type': 'boolean'},
        'underline': {'type': 'boolean'}, 'strikethrough': {'type': 'boolean'},
        'superscript': {'type': 'boolean'}, 'subscript': {'type': 'boolean'},
        'code': {'type': 'boolean'}, 'color': {'type': 'string'},
        'highlight_color': {'type': 'string'}, 'font': {'type': 'string'},
        'font_size': {'type': 'number'},
    },
    'required': ['type', 'text'],
    'additionalProperties': False,
}


def _children_schema(text_only=False):
    schemas = [TEXT_SCHEMA]
    if not text_only:
        schemas.append({
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['link']}, 'href': {'type': 'string'},
                'title': {'type': 'string'},
                'children': {'type': 'array', 'items': TEXT_SCHEMA, 'minItems': 1},
            },
            'required': ['type', 'href', 'title', 'children'],
            'additionalProperties': False,
        })
    return {'type': 'array', 'items': {'oneOf': schemas}, 'minItems': 1}


ELEMENT_SCHEMAS = [
    {
        'type': 'object', 'properties': {
            'type': {'enum': ['paragraph', 'blockquote']},
            'children': _children_schema(),
        }, 'required': ['type', 'children'], 'additionalProperties': False,
    },
    {
        'type': 'object', 'properties': {
            'type': {'enum': ['header1', 'header2', 'header3', 'header4', 'header5', 'header6', 'subtitle']},
            'children': _children_schema(text_only=True),
        }, 'required': ['type', 'children'], 'additionalProperties': False,
    },
    {
        'type': 'object', 'properties': {
            'type': {'type': 'string', 'enum': ['callout']},
            'style': {'type': 'object', 'properties': {'background_color': {'type': 'string'}}, 'required': ['background_color'], 'additionalProperties': False},
            'children': {'type': 'array', 'items': {
                'type': 'object', 'properties': {'type': {'type': 'string', 'enum': ['paragraph']}, 'children': _children_schema()},
                'required': ['type', 'children'], 'additionalProperties': False,
            }, 'minItems': 1},
        }, 'required': ['type', 'children'], 'additionalProperties': False,
    },
    {
        'type': 'object', 'properties': {
            'type': {'type': 'string', 'enum': ['check_list_item']}, 'checked': {'type': 'boolean'},
            'children': _children_schema(),
        }, 'required': ['type', 'checked', 'children'], 'additionalProperties': False,
    },
    {
        'type': 'object', 'properties': {
            'type': {'type': 'string', 'enum': ['code_block']}, 'language': {'type': 'string'}, 'text': {'type': 'string'},
        }, 'required': ['type', 'language', 'text'], 'additionalProperties': False,
    },
    {
        'type': 'object', 'properties': {
            'type': {'enum': ['ordered_list', 'unordered_list']},
            'items': {'type': 'array', 'items': {
                'type': 'object', 'properties': {'children': _children_schema()},
                'required': ['children'], 'additionalProperties': False,
            }, 'minItems': 1},
        }, 'required': ['type', 'items'], 'additionalProperties': False,
    },
    {'type': 'object', 'properties': {'type': {'type': 'string', 'enum': ['divider']}}, 'required': ['type'], 'additionalProperties': False},
    {
        'type': 'object', 'properties': {
            'type': {'type': 'string', 'enum': ['formula']},
            'data': {'type': 'object', 'properties': {'formula': {'type': 'string'}}, 'required': ['formula'], 'additionalProperties': False},
        }, 'required': ['type', 'data'], 'additionalProperties': False,
    },
    {
        'type': 'object', 'properties': {
            'type': {'type': 'string', 'enum': ['embed_link']}, 'link': {'type': 'string'},
            'link_type': {'enum': ['seatable', 'figma']},
            'data': {'type': 'object', 'properties': {'height': {'type': 'integer', 'minimum': 200, 'maximum': 1200}}, 'required': ['height'], 'additionalProperties': False},
        }, 'required': ['type', 'link', 'link_type'], 'additionalProperties': False,
    },
    {
        'type': 'object', 'properties': {
            'type': {'type': 'string', 'enum': ['table']},
            'rows': {'type': 'array', 'items': {
                'type': 'object', 'properties': {
                    'cells': {'type': 'array', 'items': {
                        'type': 'object', 'properties': {'children': _children_schema()},
                        'required': ['children'], 'additionalProperties': False,
                    }, 'minItems': 1, 'maxItems': MAX_TABLE_COLUMNS},
                }, 'required': ['cells'], 'additionalProperties': False,
            }, 'minItems': 1, 'maxItems': MAX_TABLE_ROWS},
        }, 'required': ['type', 'rows'], 'additionalProperties': False,
    },
]

MULTI_COLUMN_ELEMENT_SCHEMAS = [
    schema for schema in ELEMENT_SCHEMAS
    if schema['properties']['type'].get('const') in MULTI_COLUMN_TYPES
    or any(kind in MULTI_COLUMN_TYPES for kind in schema['properties']['type'].get('enum', []))
]

ELEMENT_SCHEMAS.append({
    'type': 'object', 'properties': {
        'type': {'type': 'string', 'enum': ['multi_column']},
        'columns': {'type': 'array', 'items': {
            'type': 'object', 'properties': {
                'children': {'type': 'array', 'items': {'oneOf': MULTI_COLUMN_ELEMENT_SCHEMAS}, 'minItems': 1},
            }, 'required': ['children'], 'additionalProperties': False,
        }, 'minItems': 2, 'maxItems': 4},
    }, 'required': ['type', 'columns'], 'additionalProperties': False,
})


SDOC_PARAMETERS = {
    'type': 'object',
    'properties': {
        'file_name': {'type': 'string'},
        'title': {'type': 'object', 'properties': {'children': _children_schema(text_only=True)}, 'required': ['children'], 'additionalProperties': False},
        'summary': {'type': 'string'},
        'elements': {'type': 'array', 'items': {'oneOf': ELEMENT_SCHEMAS}, 'minItems': 1, 'maxItems': MAX_ELEMENTS},
    },
    'required': ['file_name', 'title', 'elements'],
    'additionalProperties': False,
}


def _exact(value, required, optional=()):
    if not isinstance(value, dict) or not set(required).issubset(value) or not set(value).issubset(set(required) | set(optional)):
        raise ValueError('object fields invalid')


def _string(value, name, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError('%s must be a string' % name)
    return value


class _State:
    def __init__(self):
        self.nodes = 0
        self.text_length = 0

    def add(self, text=''):
        self.nodes += 1
        self.text_length += len(text)
        if self.nodes > MAX_ELEMENTS or self.text_length > MAX_TEXT_LENGTH:
            raise ValueError('document content is too large')


def _validate_text(value, state):
    _exact(value, {'type', 'text'}, MARK_TYPES)
    if value.get('type') != 'text':
        raise ValueError('text type invalid')
    text = _string(value.get('text'), 'text', allow_empty=True)
    if REFERENCE_RE.search(text):
        raise ValueError('citation token invalid')
    for mark, expected in MARK_TYPES.items():
        if mark not in value:
            continue
        mark_value = value[mark]
        if isinstance(mark_value, bool) and expected != bool or not isinstance(mark_value, expected):
            raise ValueError('text mark invalid')
        if mark in ('color', 'highlight_color') and not COLOR_RE.match(mark_value):
            raise ValueError('text color invalid')
    if value.get('superscript') and value.get('subscript'):
        raise ValueError('text marks conflict')
    state.add(text)
    return dict(value)


def _validate_url(value, https_only=False):
    parsed = urlparse(_string(value, 'url'))
    schemes = ('https',) if https_only else ('http', 'https')
    if parsed.scheme.lower() not in schemes or not parsed.netloc:
        raise ValueError('url invalid')
    return value


def _validate_children(value, state, text_only=False):
    if not isinstance(value, list) or not value:
        raise ValueError('children invalid')
    result = []
    for child in value:
        if not isinstance(child, dict):
            raise ValueError('child type invalid')
        if child.get('type') == 'text':
            result.append(_validate_text(child, state))
        elif not text_only and child.get('type') == 'link':
            _exact(child, {'type', 'href', 'title', 'children'})
            result.append({
                'type': 'link', 'href': _validate_url(child['href']),
                'title': _string(child['title'], 'link.title'),
                'children': _validate_children(child['children'], state, text_only=True),
            })
            state.add(child['title'])
        else:
            raise ValueError('child type invalid')
    if not ''.join(child.get('text', '') for child in result if child['type'] == 'text').strip() and not any(child['type'] == 'link' for child in result):
        raise ValueError('children must contain visible content')
    return result


def _validate_element(value, state, depth=1):
    if depth > MAX_DEPTH or not isinstance(value, dict):
        raise ValueError('element hierarchy invalid')
    kind = value.get('type')
    if kind in DEFERRED_TYPES:
        raise ValueError('unsupported element type')
    if kind in ('paragraph', 'blockquote'):
        _exact(value, {'type', 'children'})
        result = {'type': kind, 'children': _validate_children(value['children'], state)}
    elif kind in ('header1', 'header2', 'header3', 'header4', 'header5', 'header6', 'subtitle'):
        _exact(value, {'type', 'children'})
        result = {'type': kind, 'children': _validate_children(value['children'], state, text_only=True)}
    elif kind == 'callout':
        _exact(value, {'type', 'children'}, {'style'})
        if not isinstance(value['children'], list) or not value['children']:
            raise ValueError('callout children invalid')
        result = {'type': kind, 'children': []}
        for child in value['children']:
            if not isinstance(child, dict) or child.get('type') != 'paragraph':
                raise ValueError('callout hierarchy invalid')
            result['children'].append(_validate_element(child, state, depth + 1))
        if 'style' in value:
            _exact(value['style'], {'background_color'})
            color = _string(value['style']['background_color'], 'background_color')
            if not COLOR_RE.match(color):
                raise ValueError('background color invalid')
            result['style'] = {'background_color': color}
    elif kind == 'check_list_item':
        _exact(value, {'type', 'checked', 'children'})
        if not isinstance(value['checked'], bool):
            raise ValueError('checked invalid')
        result = {'type': kind, 'checked': value['checked'], 'children': _validate_children(value['children'], state)}
    elif kind == 'code_block':
        _exact(value, {'type', 'language', 'text'})
        text = _string(value['text'], 'code.text', allow_empty=True)
        if REFERENCE_RE.search(text):
            raise ValueError('citation token invalid')
        state.add(text)
        result = {'type': kind, 'language': _string(value['language'], 'language', allow_empty=True), 'text': text}
    elif kind in ('ordered_list', 'unordered_list'):
        _exact(value, {'type', 'items'})
        if not isinstance(value['items'], list) or not value['items']:
            raise ValueError('list items invalid')
        result = {'type': kind, 'items': []}
        for item in value['items']:
            _exact(item, {'children'})
            state.add()
            result['items'].append({'children': _validate_children(item['children'], state)})
    elif kind == 'divider':
        _exact(value, {'type'})
        result = {'type': kind}
    elif kind == 'formula':
        _exact(value, {'type', 'data'}); _exact(value['data'], {'formula'})
        formula = _string(value['data']['formula'], 'formula'); state.add(formula)
        result = {'type': kind, 'data': {'formula': formula}}
    elif kind == 'embed_link':
        _exact(value, {'type', 'link', 'link_type'}, {'data'})
        if value['link_type'] not in ('seatable', 'figma'):
            raise ValueError('link type invalid')
        result = {'type': kind, 'link': _validate_url(value['link'], https_only=True), 'link_type': value['link_type']}
        if 'data' in value:
            _exact(value['data'], {'height'}); height = value['data']['height']
            if isinstance(height, bool) or not isinstance(height, int) or not 200 <= height <= 1200:
                raise ValueError('embed height invalid')
            result['data'] = {'height': height}
    elif kind == 'table':
        _exact(value, {'type', 'rows'}); rows = value['rows']
        if not isinstance(rows, list) or not rows or len(rows) > MAX_TABLE_ROWS:
            raise ValueError('table rows invalid')
        result = {'type': kind, 'rows': []}; width = None
        for row in rows:
            _exact(row, {'cells'}); cells = row['cells']
            state.add()
            if not isinstance(cells, list) or not cells or len(cells) > MAX_TABLE_COLUMNS or width not in (None, len(cells)):
                raise ValueError('table cells invalid')
            width = len(cells); normalized_cells = []
            for cell in cells:
                state.add()
                _exact(cell, {'children'}); normalized_cells.append({'children': _validate_children(cell['children'], state)})
            result['rows'].append({'cells': normalized_cells})
    elif kind == 'multi_column':
        _exact(value, {'type', 'columns'}); columns = value['columns']
        if not isinstance(columns, list) or not 2 <= len(columns) <= 4:
            raise ValueError('columns invalid')
        result = {'type': kind, 'columns': []}
        for column in columns:
            _exact(column, {'children'}); children = column['children']
            state.add()
            if not isinstance(children, list) or not children:
                raise ValueError('column children invalid')
            normalized_children = []
            for child in children:
                if not isinstance(child, dict) or child.get('type') not in MULTI_COLUMN_TYPES:
                    raise ValueError('column child type invalid')
                normalized_children.append(_validate_element(child, state, depth + 1))
            result['columns'].append({'children': normalized_children})
    else:
        raise ValueError('unsupported element type')
    state.add()
    return result


def validate_sdoc_draft(file_name, title, elements, summary=None):
    file_name = _string(file_name, 'file_name').strip()
    if summary is not None:
        summary = _string(summary, 'summary').strip()
    _exact(title, {'children'})
    state = _State()
    normalized_title = {'children': _validate_children(title['children'], state, text_only=True)}
    if not isinstance(elements, list) or not elements:
        raise ValueError('elements must be a non-empty array')
    normalized_elements = [_validate_element(element, state) for element in elements]
    result = {
        'schema_version': SCHEMA_VERSION,
        'file_name': file_name,
        'title': normalized_title,
        'elements': normalized_elements,
    }
    if summary is not None:
        result['summary'] = summary
    if len(json.dumps(result, ensure_ascii=False)) > MAX_TEXT_LENGTH * 4:
        raise ValueError('document content is too large')
    return result


class CreateSdoc(BasicTool):
    tool = {
        'type': 'function',
        'function': {
            'name': 'create_sdoc',
            'description': 'Validate and create a complete SDoc in /AI Generated/. Return its relative path only after the file has been saved.',
            'parameters': SDOC_PARAMETERS,
        },
    }

    def execute(self, file_name, title, elements, context, tool_executor, seahub_api, summary=None):
        cached = tool_executor.cache.get('sdoc_create_result')
        if cached:
            return cached
        try:
            draft = validate_sdoc_draft(file_name, title, elements, summary=summary)
        except (TypeError, ValueError) as error:
            result = {'type': 'sdoc', 'status': 'failed', 'error_code': 'invalid_artifact'}
            tool_executor.cache['artifacts'] = [result]
            return {**result, 'error': str(error)}
        token = context.get('sdoc_create_token')
        if not token:
            result = {'type': 'sdoc', 'status': 'failed', 'error_code': 'create_failed'}
            tool_executor.cache['artifacts'] = [result]
            return result
        # A lost response can follow a successful write. Never retry this mutation.
        result = {'type': 'sdoc', 'status': 'unknown', 'error_code': 'creation_unconfirmed'}
        tool_executor.cache['sdoc_create_result'] = result
        tool_executor.cache['artifacts'] = [result]
        try:
            response = seahub_api.create_sdoc({'type': 'sdoc_create_request', **draft}, token)
            if response.get('status') == 'created':
                path = response.get('relative_path')
                if not isinstance(path, str) or not path or '/' in path or '\\' in path or '\x00' in path:
                    raise ValueError('Invalid created file path')
            elif response.get('status') != 'failed':
                raise ValueError('Invalid creation result')
            result = {key: response[key] for key in (
                'type', 'schema_version', 'status', 'name', 'relative_path', 'repo_id',
                'doc_uuid', 'title', 'summary', 'error_code',
            ) if key in response}
            result['type'] = 'sdoc'
        except Exception:
            logger.warning('SDoc creation result could not be confirmed')
        tool_executor.cache['sdoc_create_result'] = result
        tool_executor.cache['artifacts'] = [result]
        return result


class SdocCreateSkill:
    name = 'sdoc-create'

    def get_system_prompts(self):
        return [SDOC_CREATE_PROMPT]

    def register_tools(self, tool_executor, context, seahub_api):
        CreateSdoc().register(tool_executor, context=context, seahub_api=seahub_api)
