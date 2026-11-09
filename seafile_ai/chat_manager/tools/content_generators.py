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

This tool accepts a simplified SeaDoc authoring format, not the native on-disk document envelope. Supply the document title and supported element nodes described by content. The application generates node IDs, structural child elements, format metadata and editor layout when compiling the native .sdoc document.

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
                        'description': '''Simplified SeaDoc authoring format

## 1. Document format
- Pass content as a JSON-encoded string, not an object argument, Markdown source or a fenced JSON example.
- The decoded document has exactly two required properties:
  - title (string): nonempty plain-text document title, without formatting or child nodes.
  - elements (array): 1-200 top-level element nodes in reading order.
- The application converts title into the native title element. Do not repeat it as a body heading unless requested.
- All examples below show decoded JSON. Serialize the complete document once to obtain the content argument; do not serialize individual element nodes.
- Minimal document:
  {
    "title": "Project plan",
    "elements": [
      {
        "type": "paragraph",
        "children": [
          { "text": "Prepare the release." }
        ]
      }
    ]
  }

## 2. Nodes and rich-text marks

### Element nodes
- An element node represents a semantic part of the document and has a required type property.
- Its other required properties depend on its type. Do not assume every element node takes children: lists use items, code_block uses text, table uses rows, and divider has no content property in this authoring format.
- A block-level element belongs in elements. An inline element belongs only in an allowed children array; link is the only supported inline element.

### Text leaves
- A text leaf has text (required, string) and optional rich-text marks. It has no type or children property.
- Example: { "text": "Document content" }.
- An empty text leaf { "text": "" } represents blank editable content.
- Wherever children is specified below, it must be a nonempty array, including for blank content.

### Rich-text marks
- Supported marks: bold, italic, strikethrough and code (optional, boolean).
- Omit unused marks. Split differently formatted text into separate leaves, preserving spaces between them.
- Example for "This is **important**.":
  [
    { "text": "This is " },
    { "text": "important", "bold": true },
    { "text": "." }
  ]
- Other native SeaDoc marks, including underline, colors and fonts, are not supported by this tool.

## 3. Supported element types
- Top-level: paragraph; header1 through header6; blockquote; ordered_list; unordered_list; check_list_item; code_block; divider; table.
- Inline: link, supported in paragraphs, blockquotes, list items, task items and table cells. Heading children and link children accept text leaves only.
- Structural children in native SeaDoc, such as list_item, code_line, table_row and table_cell, are generated by the application. Do not supply them as typed nodes or as top-level element nodes.
- items, rows and cells below contain simplified structural objects, not native typed element nodes.
- This is a supported subset and authoring representation of SeaDoc, not the complete native .sdoc schema.

## 4. Element structures and examples

### Paragraph — paragraph
- Purpose: ordinary editable prose.
- Required properties: type="paragraph"; children (array).
- Child content: text leaves and/or inline link elements.
- Example:
  {
    "type": "paragraph",
    "children": [
      { "text": "Document content." }
    ]
  }

### Heading — header1 through header6
- Purpose: section headings at levels 1-6. The main document title is supplied separately through title.
- Required properties: type="header1" through "header6"; children (array).
- Child content: text leaves only; no links or nested element nodes.
- Example for a level-two heading:
  {
    "type": "header2",
    "children": [
      { "text": "Deployment" }
    ]
  }

### Blockquote — blockquote
- Purpose: quoted content, such as a citation or highlighted quotation.
- Required properties: type="blockquote"; children (array).
- Child content: text leaves and/or inline link elements directly. Do not provide paragraph children; the application adds the native paragraph wrapper.
- Example:
  {
    "type": "blockquote",
    "children": [
      { "text": "A useful quotation." }
    ]
  }

### Link — link (inline)
- Purpose: a clickable HTTP/HTTPS reference within editable text, not a top-level element.
- Required properties: type="link"; href (nonempty string); children (array).
- href must be a complete HTTP or HTTPS URL with a host and no control characters.
- Child content: text leaves only; links cannot contain other links.
- Do not supply a link title property; the application derives it from the displayed text.
- Example inside a paragraph:
  {
    "type": "paragraph",
    "children": [
      { "text": "See " },
      {
        "type": "link",
        "href": "https://example.com/docs",
        "children": [
          { "text": "the documentation" }
        ]
      }
    ]
  }

### Lists — ordered_list and unordered_list
- Purpose: numbered items or bullet-point items.
- Required properties: type="ordered_list" or "unordered_list"; items (array of 1-200 objects).
- Each item has exactly one property: children (array of text leaves and/or inline link elements).
- Lists are flat; no nested lists or other block-level elements. Supply items, not children, on the list element.
- The application generates the native list_item and paragraph wrappers for each item.
- Examples:
  {
    "type": "ordered_list",
    "items": [
      {
        "children": [
          { "text": "Prepare the server" }
        ]
      },
      {
        "children": [
          { "text": "Start the service" }
        ]
      }
    ]
  }

  {
    "type": "unordered_list",
    "items": [
      {
        "children": [
          { "text": "Release notes" }
        ]
      }
    ]
  }

### Task item — check_list_item
- Purpose: an individual task with a completion checkbox.
- Required properties: type="check_list_item"; checked (boolean); children (array).
- checked is false for an incomplete task and true for a completed task.
- Child content: text leaves and/or inline link elements. Each task is a separate top-level element; do not wrap tasks in ordered_list or unordered_list.
- Example:
  {
    "type": "check_list_item",
    "checked": false,
    "children": [
      { "text": "Review the release" }
    ]
  }

### Code — code_block
- Purpose: source code or preformatted text in a selected language.
- Required properties: type="code_block"; language (string); text (string).
- Use a language such as "python", or "" when unspecified. text contains the complete source with JSON-escaped newlines, without Markdown fences.
- Do not supply children or code_line nodes; the application generates the native code-line structure.
- Example:
  {
    "type": "code_block",
    "language": "python",
    "text": "print(1)\\nprint(2)"
  }

### Divider — divider
- Purpose: a horizontal separator; a void element in native SeaDoc.
- Required property: type="divider". No other properties are allowed.
- Do not supply children; the application adds the native empty text-leaf placeholder required by a void element.
- Example:
  {
    "type": "divider"
  }

### Table — table
- Purpose: rectangular tabular content.
- Required properties: type="table"; rows (array of 1-100 objects).
- Each row has exactly one property: cells (array of 1-20 objects). All rows must have the same number of cells.
- Each cell has exactly one property: children (nonempty array of text leaves and/or inline link elements).
- When there is a header, include its values in the first row. Do not include a Markdown separator row or header flags.
- Do not supply table_row/table_cell types, column widths, alignment or styles; the application adds native structural nodes and layout defaults.
- Example with a header row and a data row:
  {
    "type": "table",
    "rows": [
      {
        "cells": [
          {
            "children": [
              { "text": "Name" }
            ]
          },
          {
            "children": [
              { "text": "Value" }
            ]
          }
        ]
      },
      {
        "cells": [
          {
            "children": [
              { "text": "Phase" }
            ]
          },
          {
            "children": [
              { "text": "One" }
            ]
          }
        ]
      }
    ]
  }

## 5. Complete document example
{
  "title": "Project plan",
  "elements": [
    {
      "type": "paragraph",
      "children": [
        { "text": "This is " },
        { "text": "phase one", "bold": true },
        { "text": "." }
      ]
    },
    {
      "type": "header2",
      "children": [
        { "text": "Deployment" }
      ]
    },
    {
      "type": "unordered_list",
      "items": [
        {
          "children": [
            { "text": "Prepare the server" }
          ]
        },
        {
          "children": [
            { "text": "Start the service" }
          ]
        }
      ]
    },
    {
      "type": "check_list_item",
      "checked": false,
      "children": [
        { "text": "Verify the deployment" }
      ]
    }
  ]
}
- Pass the JSON string encoding this entire object as content.

## 6. Constraints and native-format boundary
- Supply only the documented properties, with every required property present.
- Do not provide id, version, format_version, last_modify_user, cursors, style or other editor/collaboration metadata. The application compiles this authoring representation into the native .sdoc format and supplies required metadata.
- Images, embeds, formulas, multi-column layouts and all other unlisted element types are unsupported. Express unsupported content as ordinary text using supported element nodes.
- Do not include internal citation tokens such as <reference_0>; use descriptive text or actual HTTP/HTTPS links instead.
- The compact JSON encoding of the decoded document, preserving Unicode and omitting optional whitespace, must not exceed 400000 characters. The encoded argument is separately limited to 2400002 characters.
- The total inline-node count must not exceed 20000, counting both text leaves and inline link elements, including their text children.
- Terminology and native-format reference: https://haiwen.github.io/seadoc-specification/support-types/ and its linked data-structure pages. Their native examples are reference material, not tool input; the complete accepted input format is defined above.''',
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
