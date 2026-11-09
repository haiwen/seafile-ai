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
            'description': 'Generate an editable SeaDoc (.sdoc) document. The validated content is cached internally. Returns a self-closing <seafile-ai-seadoc sdoc_create_uuid="..." ... /> reference; include it verbatim in the final answer, outside code fences. Do not repeat the JSON content. Seahub saves the document after receiving the final answer; do not invent UUIDs, file paths, URLs or creation status.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'file_name': {
                        'type': 'string',
                        'description': 'The .sdoc filename, not a path. Preserve the user-specified filename and language, appending .sdoc if needed. Otherwise choose a concise filename in the document language.',
                    },
                    'description': {
                        'type': 'string',
                        'description': 'A short, nonempty plain-text description for the document card.',
                    },
                    'content': {
                        'type': 'string',
                        'description': '''Generate the document using the following simplified SDoc content format.

## Argument encoding and document structure
- Pass content as a JSON-encoded STRING, not a JSON object, Markdown text, or a fenced code block.
- The decoded JSON object must contain exactly these two required fields:
  - title: a nonempty plain-text string. Do not use a title object, children, or formatting marks.
  - elements: an array of 1-200 body blocks, in reading order.
- Put the document's main title in title. Do not repeat it as the first body heading unless requested.
- The JSON examples below show decoded content. When calling the tool, serialize the whole document object into the content string; do not serialize individual blocks separately.

## Text nodes and inline formatting
- A text node has these fields:
  - text (required): a string.
  - bold, italic, strikethrough, code (optional): boolean formatting marks.
- Do not give text nodes a type field. Omit unused marks instead of setting them to false.
- Split differently formatted spans into separate text nodes and preserve spaces between spans.
- Example for Markdown "This is **important**.":
  [{"text":"This is "},{"text":"important","bold":true},{"text":"."}]
- Empty text is allowed, for example {"text":""} in a blank paragraph or table cell.
- Every children array must contain at least one node, even for blank content.

## Supported body blocks and links
- Paragraph:
  - Required fields: type="paragraph", children.
  - children contains text nodes and/or inline links.
  - Example: {"type":"paragraph","children":[{"text":"Document content."}]}

- Heading:
  - Required fields: type="header1" through "header6", children.
  - children contains text nodes only; links are not supported here.
  - Match the Markdown heading level: "## Deployment" becomes:
    {"type":"header2","children":[{"text":"Deployment"}]}

- Block quote:
  - Required fields: type="blockquote", children.
  - children directly contains text nodes and/or links, NOT paragraph blocks.
  - Example for Markdown "> A useful note":
    {"type":"blockquote","children":[{"text":"A useful note"}]}

- Inline link (not a standalone body block):
  - Required fields: type="link", href, children.
  - href must be a complete HTTP or HTTPS URL.
  - children contains text nodes only; nested links are not supported.
  - Links are supported inside paragraphs, quotes, list items, task items and table cells.
  - Do not add a title field; the application derives it from the link's text.
  - Example for Markdown "[Docs](https://example.com/docs)":
    {"type":"link","href":"https://example.com/docs","children":[{"text":"Docs"}]}

- Ordered or unordered list:
  - Required fields: type="ordered_list" or "unordered_list", items.
  - items contains 1-200 item objects. Each item has exactly one field: children.
  - Each item's children directly contains text nodes and/or links, NOT paragraph blocks.
  - Lists are flat: do not nest lists or other body blocks inside items.
  - Use items for the list container, not children.
  - Example for Markdown "- First item":
    {"type":"unordered_list","items":[{"children":[{"text":"First item"}]}]}

- Task item:
  - Required fields: type="check_list_item", checked, children.
  - checked is a boolean: false for unchecked, true for completed.
  - children contains text nodes and/or links.
  - Each task is a separate body block; do not wrap tasks in a list container.
  - Example for Markdown "- [ ] Review":
    {"type":"check_list_item","checked":false,"children":[{"text":"Review"}]}

- Code block:
  - Required fields: type="code_block", language, text.
  - language is a string such as "python"; use "" when unspecified.
  - text contains the complete code, with JSON-escaped newlines. Do not include Markdown fences.
  - Do not provide children or individual code-line nodes.
  - Example: {"type":"code_block","language":"python","text":"print(1)\\nprint(2)"}

- Horizontal rule:
  - Only field: type="divider". Do not provide children.
  - Example for Markdown "---": {"type":"divider"}

- Table:
  - Required fields: type="table", rows.
  - rows contains 1-100 row objects. Each row has exactly one field: cells.
  - cells contains 1-20 cell objects. Every row must contain the SAME number of cells.
  - Each cell has exactly one field: children, containing text nodes and/or links.
  - Include the header as the first row. Do not include the Markdown separator row.
  - Do not add header flags, alignment, column widths, row heights or styles.
  - Example with a header row and a data row:
    {"type":"table","rows":[{"cells":[{"children":[{"text":"Name"}]},{"children":[{"text":"Value"}]}]},{"cells":[{"children":[{"text":"Phase"}]},{"children":[{"text":"One"}]}]}]}

## Complete Markdown-to-SDoc example
The following Markdown:
# Project plan

This is **phase one**.

## Deployment
- Prepare the server
- Start the service

becomes this decoded document object:
{
  "title": "Project plan",
  "elements": [
    {"type":"paragraph","children":[{"text":"This is "},{"text":"phase one","bold":true},{"text":"."}]},
    {"type":"header2","children":[{"text":"Deployment"}]},
    {"type":"unordered_list","items":[{"children":[{"text":"Prepare the server"}]},{"children":[{"text":"Start the service"}]}]}
  ]
}
- In the actual tool call, content must be the JSON string encoding this object, not the object itself.

## Restrictions
- Supply ONLY the fields documented above. All listed required fields must be present.
- Never generate IDs, format versions, modification users, styles, widths or other editor metadata; the application supplies them.
- Do not use images, embeds, formulas, columns, colors, fonts or unsupported element types.
- Express unsupported formatting as ordinary text using the supported blocks.
- Do not include internal citation tokens such as <reference_0>; use descriptive text or actual HTTP/HTTPS links instead.
- Keep the content string within 400000 characters and the total inline-node count within 20000.''',
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

    def _validate_sdoc_content(self, content):
        """Parse and validate content before it can become a file-creation tag."""
        self._string(content, 'content', True)
        if len(content) > MAX_CONTENT_LENGTH:
            raise ValueError('SDoc content is too large')
        if re.search(r'<reference_\d+>', content):
            raise ValueError('SDoc content must not contain internal citation tokens')
        try:
            document = json.loads(content)
        except (ValueError, RecursionError) as error:
            raise ValueError('content must be a JSON object string') from error
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
        if '/' in file_name or '\\' in file_name or any(ord(c) < 32 for c in file_name) or file_name in ('.', '..', '.sdoc'):
            raise ValueError('file_name must be a filename, not a path')
        if not file_name.lower().endswith('.sdoc'):
            file_name += '.sdoc'
        document = self._validate_sdoc_content(content)
        identifier = str(uuid.uuid4())
        tool_executor.cache.setdefault('sdoc_create_results', {})[identifier] = {
            'file_name': file_name,
            'description': description,
            'content': document,
        }
        return '<seafile-ai-seadoc sdoc_create_uuid="%s" file_name="%s" description="%s" />' % (
            identifier, escape(file_name, quote=True), escape(description, quote=True))
