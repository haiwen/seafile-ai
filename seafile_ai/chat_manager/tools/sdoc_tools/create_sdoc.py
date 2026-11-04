import json
import logging
import math
import re
import posixpath
from html import escape
from urllib.parse import urlparse

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from seafile_ai.utils.tools import BasicTool

logger = logging.getLogger(__name__)


ELEMENTS_SCHEMA = {
    'type': 'object',
    'properties': {
        'title': {
            'type': 'object',
            'properties': {
                'children': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'enum': ['text']},
                            'text': {'type': 'string'},
                            'bold': {'type': 'boolean'},
                            'italic': {'type': 'boolean'},
                            'underline': {'type': 'boolean'},
                            'strikethrough': {'type': 'boolean'},
                            'superscript': {'type': 'boolean'},
                            'subscript': {'type': 'boolean'},
                            'code': {'type': 'boolean'},
                            'color': {'type': 'string'},
                            'highlight_color': {'type': 'string'},
                            'font': {'type': 'string'},
                            'font_size': {'type': 'number'},
                        },
                        'required': ['type', 'text'],
                        'additionalProperties': False,
                    },
                    'minItems': 1,
                },
            },
            'required': ['children'],
            'additionalProperties': False,
        },
        'elements': {
            'type': 'array',
            'items': {
                'oneOf': [
                    {'$ref': '#/$defs/paragraph'},
                    {'$ref': '#/$defs/heading'},
                    {'$ref': '#/$defs/callout'},
                    {'$ref': '#/$defs/checkListItem'},
                    {'$ref': '#/$defs/codeBlock'},
                    {'$ref': '#/$defs/list'},
                    {'$ref': '#/$defs/divider'},
                    {'$ref': '#/$defs/formula'},
                    {'$ref': '#/$defs/embedLink'},
                    {'$ref': '#/$defs/table'},
                    {'$ref': '#/$defs/multiColumn'},
                ],
            },
            'minItems': 1,
            'maxItems': 200,
        },
    },
    'required': ['title', 'elements'],
    'additionalProperties': False,
    '$defs': {
        'text': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['text']},
                'text': {'type': 'string'},
                'bold': {'type': 'boolean'},
                'italic': {'type': 'boolean'},
                'underline': {'type': 'boolean'},
                'strikethrough': {'type': 'boolean'},
                'superscript': {'type': 'boolean'},
                'subscript': {'type': 'boolean'},
                'code': {'type': 'boolean'},
                'color': {'type': 'string'},
                'highlight_color': {'type': 'string'},
                'font': {'type': 'string'},
                'font_size': {'type': 'number'},
            },
            'required': ['type', 'text'],
            'additionalProperties': False,
        },
        'link': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['link']},
                'href': {'type': 'string'},
                'title': {'type': 'string'},
                'children': {'type': 'array', 'items': {'$ref': '#/$defs/text'}, 'minItems': 1},
            },
            'required': ['type', 'href', 'title', 'children'],
            'additionalProperties': False,
        },
        'inline': {'oneOf': [{'$ref': '#/$defs/text'}, {'$ref': '#/$defs/link'}]},
        'inlineChildren': {'type': 'array', 'items': {'$ref': '#/$defs/inline'}, 'minItems': 1},
        'paragraph': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['paragraph', 'blockquote']},
                'children': {'$ref': '#/$defs/inlineChildren'},
            },
            'required': ['type', 'children'],
            'additionalProperties': False,
        },
        'heading': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['header1', 'header2', 'header3', 'header4', 'header5', 'header6', 'subtitle']},
                'children': {'$ref': '#/$defs/textChildren'},
            },
            'required': ['type', 'children'],
            'additionalProperties': False,
        },
        'textChildren': {'type': 'array', 'items': {'$ref': '#/$defs/text'}, 'minItems': 1},
        'calloutParagraph': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['paragraph']},
                'children': {'$ref': '#/$defs/inlineChildren'},
            },
            'required': ['type', 'children'],
            'additionalProperties': False,
        },
        'callout': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['callout']},
                'style': {
                    'type': 'object',
                    'properties': {'background_color': {'type': 'string'}},
                    'required': ['background_color'],
                    'additionalProperties': False,
                },
                'children': {'type': 'array', 'items': {'$ref': '#/$defs/calloutParagraph'}, 'minItems': 1},
            },
            'required': ['type', 'children'],
            'additionalProperties': False,
        },
        'checkListItem': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['check_list_item']},
                'checked': {'type': 'boolean'},
                'children': {'$ref': '#/$defs/inlineChildren'},
            },
            'required': ['type', 'checked', 'children'],
            'additionalProperties': False,
        },
        'codeBlock': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['code_block']},
                'language': {'type': 'string'},
                'text': {'type': 'string'},
            },
            'required': ['type', 'language', 'text'],
            'additionalProperties': False,
        },
        'listItem': {
            'type': 'object',
            'properties': {'children': {'$ref': '#/$defs/inlineChildren'}},
            'required': ['children'],
            'additionalProperties': False,
        },
        'list': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['ordered_list', 'unordered_list']},
                'items': {'type': 'array', 'items': {'$ref': '#/$defs/listItem'}, 'minItems': 1},
            },
            'required': ['type', 'items'],
            'additionalProperties': False,
        },
        'divider': {
            'type': 'object',
            'properties': {'type': {'type': 'string', 'enum': ['divider']}},
            'required': ['type'],
            'additionalProperties': False,
        },
        'formula': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['formula']},
                'data': {
                    'type': 'object',
                    'properties': {'formula': {'type': 'string'}},
                    'required': ['formula'],
                    'additionalProperties': False,
                },
            },
            'required': ['type', 'data'],
            'additionalProperties': False,
        },
        'embedLink': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['embed_link']},
                'link': {'type': 'string'},
                'link_type': {'type': 'string', 'enum': ['seatable', 'figma']},
                'data': {
                    'type': 'object',
                    'properties': {'height': {'type': 'integer', 'minimum': 200, 'maximum': 1200}},
                    'required': ['height'],
                    'additionalProperties': False,
                },
            },
            'required': ['type', 'link', 'link_type'],
            'additionalProperties': False,
        },
        'tableCell': {
            'type': 'object',
            'properties': {'children': {'$ref': '#/$defs/inlineChildren'}},
            'required': ['children'],
            'additionalProperties': False,
        },
        'tableRow': {
            'type': 'object',
            'properties': {'cells': {'type': 'array', 'items': {'$ref': '#/$defs/tableCell'}, 'minItems': 1, 'maxItems': 20}},
            'required': ['cells'],
            'additionalProperties': False,
        },
        'table': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['table']},
                'rows': {'type': 'array', 'items': {'$ref': '#/$defs/tableRow'}, 'minItems': 1, 'maxItems': 100},
            },
            'required': ['type', 'rows'],
            'additionalProperties': False,
        },
        'multiColumnChild': {
            'oneOf': [
                {'$ref': '#/$defs/paragraph'},
                {'$ref': '#/$defs/heading'},
                {'$ref': '#/$defs/checkListItem'},
                {'$ref': '#/$defs/codeBlock'},
                {'$ref': '#/$defs/list'},
                {'$ref': '#/$defs/divider'},
                {'$ref': '#/$defs/formula'},
            ],
        },
        'column': {
            'type': 'object',
            'properties': {'children': {'type': 'array', 'items': {'$ref': '#/$defs/multiColumnChild'}, 'minItems': 1}},
            'required': ['children'],
            'additionalProperties': False,
        },
        'multiColumn': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': ['multi_column']},
                'columns': {'type': 'array', 'items': {'$ref': '#/$defs/column'}, 'minItems': 2, 'maxItems': 4},
            },
            'required': ['type', 'columns'],
            'additionalProperties': False,
        },
    },
}

SDOC_PARAMETERS = {
    'type': 'object',
    'properties': {
        'file_name': {'type': 'string'},
        'description': {'type': 'string', 'description': 'A concise description of the generated document for its file card.'},
        'elements': ELEMENTS_SCHEMA,
    },
    'required': ['file_name', 'description', 'elements'],
    'additionalProperties': False,
    # Local references resolve from the tool parameters root, not the elements property.
    '$defs': ELEMENTS_SCHEMA['$defs'],
}


class SdocValidator:
    SCHEMA_VERSION = 1
    MAX_NODES = 20000
    MAX_TEXT_LENGTH = 100000
    MAX_DEPTH = 32
    REFERENCE_RE = re.compile(r'<reference_\d+>')
    COLOR_RE = re.compile(r'^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$')

    Draft202012Validator.check_schema(SDOC_PARAMETERS)
    _schema_validator = Draft202012Validator(SDOC_PARAMETERS)

    @classmethod
    def validate(cls, file_name, description, elements):
        parameters = {'file_name': file_name, 'description': description, 'elements': elements}
        cls._check_document_budget(parameters)
        try:
            cls._schema_validator.validate(parameters)
        except ValidationError as error:
            path = '.'.join(str(part) for part in error.absolute_path) or 'parameters'
            raise ValueError('Invalid SDoc parameters at %s (%s)' % (path, error.validator)) from error

        file_name = cls._string(file_name, 'file_name').strip()
        if '/' in file_name or '\\' in file_name or any(ord(char) < 32 for char in file_name) or file_name in ('.', '..', '.sdoc'):
            raise ValueError('file_name must be a filename, not a path')
        description = cls._string(description, 'description').strip()
        cls._validate_document_semantics(elements)
        return {
            'schema_version': cls.SCHEMA_VERSION,
            'file_name': file_name,
            'title': elements['title'],
            'elements': elements['elements'],
            'description': description,
        }

    @staticmethod
    def _string(value, name):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('%s must be a string' % name)
        return value

    @classmethod
    def _check_document_budget(cls, document):
        # Bound untrusted input before Schema validation traverses it.
        nodes = text_length = 0
        pending = [(document, 0)]
        while pending:
            value, depth = pending.pop()
            nodes += 1
            if depth > cls.MAX_DEPTH:
                raise ValueError('document hierarchy is too deep')
            if isinstance(value, str):
                text_length += len(value)
            elif isinstance(value, float) and not math.isfinite(value):
                raise ValueError('document numbers must be finite')
            elif isinstance(value, dict):
                text_length += sum(len(key) for key in value if isinstance(key, str))
                pending.extend((child, depth + 1) for child in value.values())
            elif isinstance(value, list):
                pending.extend((child, depth + 1) for child in value)
            if nodes + len(pending) > cls.MAX_NODES or text_length > cls.MAX_TEXT_LENGTH:
                raise ValueError('document content is too large')
        if len(json.dumps(document, ensure_ascii=False, allow_nan=False)) > cls.MAX_TEXT_LENGTH * 4:
            raise ValueError('document content is too large')

    @classmethod
    def _validate_url(cls, value, https_only=False):
        parsed = urlparse(cls._string(value, 'url'))
        schemes = ('https',) if https_only else ('http', 'https')
        if parsed.scheme.lower() not in schemes or not parsed.netloc:
            raise ValueError('url invalid')
        return value

    @classmethod
    def _validate_document_semantics(cls, value):
        """Check only content rules that are not expressed by the supplied Schema."""
        if isinstance(value, list):
            for child in value:
                cls._validate_document_semantics(child)
        elif isinstance(value, dict):
            kind = value.get('type')
            if kind == 'text' and value.get('superscript') and value.get('subscript'):
                raise ValueError('text marks conflict')
            if kind == 'link':
                cls._validate_url(value['href'])
                cls._string(value['title'], 'link.title')
            elif kind == 'embed_link':
                cls._validate_url(value['link'], https_only=True)
            elif kind == 'formula':
                cls._string(value['data']['formula'], 'formula')
            elif kind == 'table':
                if len({len(row['cells']) for row in value['rows']}) != 1:
                    raise ValueError('table rows must have equal numbers of cells')

            children = value.get('children', [])
            if children and all(child.get('type') in ('text', 'link') for child in children):
                if not any(child['type'] == 'link' or child['text'].strip() for child in children):
                    raise ValueError('children must contain visible content')

            for key, child in value.items():
                if key in ('color', 'highlight_color', 'background_color') and not cls.COLOR_RE.fullmatch(child):
                    raise ValueError('text color invalid')
                if isinstance(child, str) and cls.REFERENCE_RE.search(child):
                    raise ValueError('citation token invalid')
                cls._validate_document_semantics(child)


class CreateSdoc(BasicTool):
    tool = {
        'type': 'function',
        'function': {
            'name': 'create_sdoc',
            'description': 'Create a complete SDoc in /AI Generated/. Available only for the explicitly selected /sdoc-create skill. Returns a <seadoc ... /> result tag. You MUST include the returned tag verbatim in the final answer, outside code fences, whether creation succeeded, failed, or is unconfirmed. Never invent or edit its metadata.',
            'parameters': SDOC_PARAMETERS,
        },
    }

    def execute(self, file_name, description, elements, context, tool_executor, seahub_api):
        if context.get('selected_skill_id') != 'sdoc-create':
            raise ValueError('create_sdoc requires the explicit /sdoc-create command')
        cached = tool_executor.cache.get('sdoc_create_result')
        if cached:
            return cached
        try:
            draft = SdocValidator.validate(file_name, description, elements)
        except (TypeError, ValueError) as error:
            logger.info('Invalid SDoc parameters: %s', error)
            return self.seadoc_tag({'status': 'failed', 'error_code': 'invalid_artifact'})
        token = context.get('sdoc_create_token')
        if not token:
            return self.seadoc_tag({'status': 'failed', 'error_code': 'create_failed'})
        # A lost response can follow a successful write. Never retry this mutation.
        result = self.seadoc_tag({'status': 'unknown', 'error_code': 'creation_unconfirmed'})
        tool_executor.cache['sdoc_create_result'] = result
        try:
            response = seahub_api.create_sdoc({'type': 'sdoc_create_request', **draft}, token)
            if response.get('status') == 'created':
                path = response.get('path')
                if (not isinstance(path, str) or not path.startswith('/AI Generated/') or
                        posixpath.normpath(path) != path or '\\' in path or
                        any(ord(char) < 32 for char in path) or not path.lower().endswith('.sdoc') or
                        not isinstance(response.get('name'), str) or response['name'] != posixpath.basename(path) or
                        not isinstance(response.get('doc_uuid'), str) or not response['doc_uuid']):
                    raise ValueError('Invalid created file path')
            elif response.get('status') != 'failed':
                raise ValueError('Invalid creation result')
            result = self.seadoc_tag(response)
        except Exception:
            logger.warning('SDoc creation result could not be confirmed')
        tool_executor.cache['sdoc_create_result'] = result
        return result

    @staticmethod
    def seadoc_tag(result):
        fields = ('status', 'name', 'path', 'doc_uuid', 'description', 'error_code')
        attributes = ' '.join(f'{key}="{escape(str(result[key]), quote=True)}"' for key in fields if key in result)
        return f'<seadoc {attributes} />'
