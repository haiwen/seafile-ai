import json
import re
import uuid
from html import escape
from urllib.parse import urlsplit

from seafile_ai.utils.tools import BasicTool


class MarkdownGenerator(BasicTool):
    tool = {
        'type': 'function',
        'function': {
            'name': 'generate_markdown',
            'description': 'This tool processes requests to generate Markdown files or documents. The output is returned as content wrapped within `<seafile-ai-markdown>` HTML tags.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'file_name': {
                        'type': 'string',
                        'description': """This parameter represents the filename of the generated Markdown file (or document), which must follow these rules:
- Must end with .md
- If the user specifies filename, must use it as the filename without translating, transliterating, or changing its language; append .md if needed
- Otherwise, use a concise filename in the same language as the generated document, unless another document language is explicitly requested""",
                    },
                    'content': {
                        'type': 'string',
                        'description': """This parameter represents the content of the generated Markdown file (or document). This parameter should follow the Markdown standard format.

Here is an example:
# Seafile Docker overview
Seafile docker based installation consist of the following components (docker images):
- Seafile server: Seafile core services, see [Seafile Components](https://manual.seafile.com/latest/introduction/components.md) for the details.
- MySQL: Database stores data related to Seafile and SeaDoc.
- Redis: Cache server.
- Caddy: Caddy server enables user to access the Seafile service (i.e., Seafile server and Sdoc server) externally and handles `SSL` configuration.""",
                    },
                },
                'required': ['file_name', 'content'],
            },
        },
    }

    def execute(self, file_name, content):
        return f"""<seafile-ai-markdown file_name="{file_name}">
{content}
</seafile-ai-markdown>
"""


MAX_CONTENT_LENGTH = 400000
MARKS = {'bold', 'italic', 'strikethrough', 'code'}


class SdocGenerator(BasicTool):
    tool = {
        'type': 'function',
        'function': {
            'name': 'generate_sdoc',
            'description': '''Generate an editable SeaDoc document. SeaDoc is Seafile's rich-text document format, stored in .sdoc files; its content is represented as a tree of element nodes and text leaves.

Before constructing content or calling this tool, call get_sdoc_specification in the current request and read its result. Do not call the two tools in parallel. Follow the returned specification for the supported simplified authoring format, not the native on-disk document envelope. Supply only the document title and necessary Markdown-like content fields; the application generates node IDs, structural child elements, format metadata and editor layout.

The tool validates and caches the document, then returns a self-closing <seafile-ai-seadoc sdoc_create_uuid="..." ... /> reference. Include that reference verbatim in the final answer, outside code fences; do not repeat the JSON content. File persistence occurs after the final answer reaches Seahub, not during this tool call. Do not invent UUIDs, file paths, URLs or creation status.''',
            'parameters': {
                'type': 'object',
                'properties': {
                    'file_name': {
                        'type': 'string',
                        'description': 'The .sdoc filename, not a path. Preserve the user-specified name and language when valid; otherwise choose a concise valid name in the document language. The tool trims surrounding whitespace and appends .sdoc if needed. The final filename, including the extension, must fit within 256 UTF-8 bytes. It must not contain consecutive dots (..), path separators, control characters or emoji in the restricted SeaDoc filename ranges; .sdoc alone is invalid. Invalid names raise an error before caching; correct the filename and retry.',
                    },
                    'description': {
                        'type': 'string',
                        'description': 'A short, nonempty plain-text description for the document card.',
                    },
                    'content': {
                        'type': 'string',
                        'description': (
                            'A JSON-encoded string containing a plain-text title and simplified '
                            'Markdown-like elements, not Markdown source, a fenced code block or an object argument. '
                            'Serialize the entire document once, not individual nodes. '
                            'Before constructing this value, call get_sdoc_specification and read its result. '
                            'Follow that specification and supply only the necessary content fields; '
                            'omit generated IDs, layout and editor metadata.'
                        ),
                    },
                },
                'required': ['file_name', 'description', 'content'],
                'additionalProperties': False,
            },
        },
    }

    @staticmethod
    def _keys(value, required, optional=()):
        if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
            raise ValueError('Invalid SDoc fields; expected %s' % ', '.join(required))

    @staticmethod
    def _string(value, name, nonempty=False):
        if not isinstance(value, str) or (nonempty and not value.strip()):
            raise ValueError('%s must be %sa string' % (name, 'a nonempty ' if nonempty else ''))

    @staticmethod
    def _validate_file_name(file_name):
        """Match Seahub's SDoc boundary, including is_valid_dirent_name rules.

        Keep these ranges in sync with seahub/utils/__init__.py. Do not import
        Seahub here: the content tool must remain service-independent.
        """
        if (file_name.lower() == '.sdoc' or '..' in file_name or
                '/' in file_name or '\\' in file_name or any(ord(char) < 32 for char in file_name)):
            raise ValueError('file_name must be a valid .sdoc filename without paths, consecutive dots or control characters')
        emoji_ranges = (
            (0x1F600, 0x1F64F), (0x1F300, 0x1F5FF), (0x1F680, 0x1F6FF),
            (0x1F1E0, 0x1F1FF), (0x2600, 0x26FF), (0x2700, 0x27BF),
            (0x1F900, 0x1F9FF), (0x1FA00, 0x1FAFF),
        )
        if any(start <= ord(char) <= end for char in file_name for start, end in emoji_ranges):
            raise ValueError('file_name contains a restricted emoji character; use ordinary text instead')
        try:
            encoded = file_name.encode('utf-8')
        except UnicodeEncodeError as error:
            raise ValueError('file_name must be valid UTF-8 text') from error
        if len(encoded) > 256:
            raise ValueError('file_name including .sdoc must not exceed 256 UTF-8 bytes')

    def _validate_sdoc_content(self, content):
        """Parse and validate content before it can become a file-creation tag."""
        self._string(content, 'content', True)
        # Bound parsing separately from the decoded, canonical content limit.
        if len(content) > MAX_CONTENT_LENGTH * 6 + 2:
            raise ValueError('SDoc content is too large')
        if re.search(r'<reference_\d+>', content):
            raise ValueError('SDoc content must not contain internal citation tokens')
        try:
            document = json.loads(content)
        except (ValueError, RecursionError) as error:
            raise ValueError('content must be a JSON object string') from error
        if len(json.dumps(document, ensure_ascii=False, allow_nan=False, separators=(',', ':'))) > MAX_CONTENT_LENGTH:
            raise ValueError('SDoc content is too large')
        self._keys(document, ('title', 'elements'))
        self._string(document['title'], 'title', True)
        if re.search(r'<reference_\d+>', json.dumps(document, ensure_ascii=False)):
            raise ValueError('SDoc content must not contain internal citation tokens')
        if not isinstance(document['elements'], list) or not 1 <= len(document['elements']) <= 200:
            raise ValueError('elements must contain 1 to 200 blocks')
        nodes = 0

        def inline(children, links=True):
            nonlocal nodes
            if not isinstance(children, list) or not children:
                raise ValueError('children must be a nonempty array')
            for child in children:
                nodes += 1
                if nodes > 20000:
                    raise ValueError('Too many SDoc nodes')
                if isinstance(child, dict) and child.get('type') == 'link' and links:
                    self._keys(child, ('type', 'href', 'children'))
                    self._string(child['href'], 'href', True)
                    url = urlsplit(child['href'])
                    if url.scheme.lower() not in ('http', 'https') or not url.netloc or any(ord(c) < 32 for c in child['href']):
                        raise ValueError('href must be an HTTP or HTTPS URL')
                    inline(child['children'], links=False)
                else:
                    self._keys(child, ('text',), MARKS)
                    self._string(child['text'], 'text')
                    if any(type(child[mark]) is not bool for mark in MARKS & child.keys()):
                        raise ValueError('Text marks must be booleans')

        for block in document['elements']:
            if not isinstance(block, dict):
                raise ValueError('Each element must be an object')
            kind = block.get('type')
            if kind in ('paragraph', 'blockquote', 'header1', 'header2', 'header3', 'header4', 'header5', 'header6'):
                self._keys(block, ('type', 'children'))
                inline(block['children'], links=kind in ('paragraph', 'blockquote'))
            elif kind == 'check_list_item':
                self._keys(block, ('type', 'checked', 'children'))
                if type(block['checked']) is not bool:
                    raise ValueError('checked must be a boolean')
                inline(block['children'])
            elif kind == 'code_block':
                self._keys(block, ('type', 'language', 'text'))
                self._string(block['language'], 'language')
                self._string(block['text'], 'text')
            elif kind in ('ordered_list', 'unordered_list'):
                self._keys(block, ('type', 'items'))
                if not isinstance(block['items'], list) or not 1 <= len(block['items']) <= 200:
                    raise ValueError('items must contain 1 to 200 list items')
                for item in block['items']:
                    self._keys(item, ('children',))
                    inline(item['children'])
            elif kind == 'table':
                self._keys(block, ('type', 'rows'))
                if not isinstance(block['rows'], list) or not 1 <= len(block['rows']) <= 100:
                    raise ValueError('rows must contain 1 to 100 rows')
                width = None
                for row in block['rows']:
                    self._keys(row, ('cells',))
                    if not isinstance(row['cells'], list) or not 1 <= len(row['cells']) <= 20:
                        raise ValueError('Each row must contain 1 to 20 cells')
                    if width is not None and len(row['cells']) != width:
                        raise ValueError('Table rows must have equal numbers of cells')
                    width = len(row['cells'])
                    for cell in row['cells']:
                        self._keys(cell, ('children',))
                        inline(cell['children'])
            elif kind == 'divider':
                self._keys(block, ('type',))
            else:
                raise ValueError('Unsupported SDoc element type: %s' % kind)
        return document

    def execute(self, file_name, description, content, tool_executor):
        self._string(file_name, 'file_name', True)
        self._string(description, 'description', True)
        file_name = file_name.strip()
        if not file_name.lower().endswith('.sdoc'):
            file_name += '.sdoc'
        self._validate_file_name(file_name)
        document = self._validate_sdoc_content(content)
        identifier = str(uuid.uuid4())
        tool_executor.cache.setdefault('sdoc_create_results', {})[identifier] = {
            'file_name': file_name,
            'description': description,
            'content': document,
        }
        return '<seafile-ai-seadoc sdoc_create_uuid="%s" file_name="%s" description="%s" />' % (
            identifier, escape(file_name, quote=True), escape(description, quote=True))
