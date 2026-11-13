# SeaDoc Authoring Specification

## Introduction

This reference defines the common Markdown-like content supported by `generate_sdoc`.
Read it before constructing the tool's `content` argument.

The organization and terminology follow the official
[SeaDoc Specification](https://haiwen.github.io/seadoc-specification/): document
model, text leaves, block elements and inline elements. However, the examples
here use the application's **simplified authoring format**, not the native
`.sdoc` file format. Use this reference for tool input; do not copy native
examples from the official manual into `content`.

Only semantic content is needed. The application supplies native structural
wrappers, node IDs, document metadata and editor layout. Fonts, colors and
advanced elements are outside this authoring subset.

## Document Model

### Document Format

The document root has exactly two required fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `title` | string | Nonempty, plain-text document title. |
| `elements` | array | Between 1 and 200 block elements, in reading order. |

The application creates the native title element from `title`. Do not repeat
the title as a body heading unless the user requests it.

```json
{
  "title": "Meeting notes",
  "elements": [
    {"type": "paragraph", "children": [{"text": "The team reviewed the release."}]}
  ]
}
```

Examples in this reference show decoded JSON. Serialize the entire document
once and pass the resulting string as `content`. Do not serialize individual
nodes, pass an object argument, or include Markdown code fences in the value.

### Node Hierarchy

- **Document root**: contains block elements in `elements`.
- **Block elements**: paragraphs, headings, quotations, lists, task items,
  code blocks, dividers and tables.
- **Inline elements**: links within supported text containers.
- **Text leaves**: text and optional marks; no `type` or `children`.

An element's `type` determines its fields. Most text containers use `children`,
but lists use `items`, code blocks use `text`, and tables use `rows` and `cells`.
A divider needs only `type`. Every `children` array supplied in this format
must be nonempty; use `{"text": ""}` for blank editable content.

The common hierarchy is:

```text
document -> elements -> block
paragraph / heading / blockquote / task -> children -> text or allowed link
list -> items -> children -> text or link
table -> rows -> cells -> children -> text or link
link -> children -> text
```

## Text

### Properties

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `text` | string | Yes | Displayed text, including spaces and punctuation. May be empty. |
| `bold` | boolean | No | Strong emphasis. |
| `italic` | boolean | No | Emphasis. |
| `strikethrough` | boolean | No | Deleted or superseded text. |
| `code` | boolean | No | Inline code. |

Omit unused marks. A mark is enabled by `true`; `false` leaves it disabled.
Split text into separate leaves when formatting changes, preserving spaces.
These are the only supported marks; do not supply native font or color fields.

### Example

```json
{
  "type": "paragraph",
  "children": [
    {"text": "Run "},
    {"text": "make test", "code": true},
    {"text": " before "},
    {"text": "publishing", "bold": true},
    {"text": "."}
  ]
}
```

## Block Elements

### Paragraph

`paragraph` represents ordinary editable prose.

- Required fields: `type: "paragraph"`, `children` (array).
- Children: text leaves and inline links, not other blocks.

```json
{"type": "paragraph", "children": [{"text": "Record decisions and next steps here."}]}
```

### Heading

`header1` through `header6` represent section headings at levels 1 through 6,
similar to Markdown `#` through `######`. The document title is separate.

- Required fields: `type` (one of those six names), `children` (array).
- Children: text leaves only; no links or nested blocks.

```json
{"type": "header2", "children": [{"text": "Decisions"}]}
```

### Blockquote

`blockquote` represents quoted prose, similar to Markdown `>`.

- Required fields: `type: "blockquote"`, `children` (array).
- Children: text leaves and inline links directly. Unlike the native format,
  do not wrap them in a paragraph; the application adds that wrapper.

```json
{"type": "blockquote", "children": [{"text": "Keep the first release focused."}]}
```

### List

`ordered_list` represents numbered steps; `unordered_list` represents bullets.

- Required fields: `type: "ordered_list"` or `"unordered_list"`, `items` (array
  of 1–200 objects).
- Each item has exactly one field: `children`, containing text leaves and/or links.
- Lists are flat. Nested lists, paragraph objects and other blocks are not
  supported within an item.
- Use `items`, not native `children -> list_item -> paragraph` nodes. The
  application builds those structural nodes.

```json
{
  "type": "ordered_list",
  "items": [
    {"children": [{"text": "Review the proposal."}]},
    {"children": [{"text": "Approve the scope."}]}
  ]
}
```

```json
{
  "type": "unordered_list",
  "items": [
    {"children": [{"text": "Release notes"}]},
    {"children": [{"text": "Test report"}]}
  ]
}
```

### Checklist Item

`check_list_item` represents one task, similar to Markdown `- [ ]` or `- [x]`.

- Required fields: `type: "check_list_item"`, `checked` (boolean), `children` (array).
- `checked: false` means pending; `true` means completed.
- Children: text leaves and inline links.
- Put each task directly in `elements`, not inside a list container.

```json
{"type": "check_list_item", "checked": false, "children": [{"text": "Assign a reviewer."}]}
```

### Code Block

`code_block` represents source code or preformatted text.

- Required fields: `type: "code_block"`, `language` (string), `text` (string).
- Use a language name such as `"python"`, or `""` if unspecified.
- `text` contains the entire source; encode newlines as JSON escapes. Do not
  include Markdown fences, `children`, or native `code_line` elements.

```json
{"type": "code_block", "language": "python", "text": "status = 'ready'\nprint(status)"}
```

### Divider

`divider` separates sections, similar to Markdown `---`.

- Required field: `type: "divider"`. No other fields are accepted.
- It is a void element in native SeaDoc. The application adds its required
  empty text placeholder; do not supply `children` yourself.

```json
{"type": "divider"}
```

### Table

`table` represents rectangular rows and columns.

- Required fields: `type: "table"`, `rows` (array of 1–100 objects).
- Each row has exactly one field: `cells` (array of 1–20 objects). Every row
  must have the same number of cells.
- Each cell has exactly one field: `children` (nonempty array of text leaves
  and/or inline links). Blocks and nested tables are not supported in cells.
- If a header is needed, put its text in the first row. Do not add a Markdown
  separator row or header flags.
- Do not supply native `table_row` or `table_cell` types, widths, styles or
  alignment; the application supplies structural nodes and layout defaults.

```json
{
  "type": "table",
  "rows": [
    {"cells": [
      {"children": [{"text": "Action"}]},
      {"children": [{"text": "Owner"}]}
    ]},
    {"cells": [
      {"children": [{"text": "Review scope"}]},
      {"children": [{"text": "Team"}]}
    ]}
  ]
}
```

## Inline Elements

### Link

`link` represents a clickable reference within text, not a top-level block.

- Required fields: `type: "link"`, `href` (nonempty string), `children` (array).
- `href` must be a complete HTTP or HTTPS URL with a host and no control characters.
- Children: text leaves only; links cannot contain other links.
- Allowed in paragraphs, blockquotes, list items, task items and table cells,
  but not headings.
- Do not supply a `title` field; the application derives it from the displayed text.

```json
{
  "type": "paragraph",
  "children": [
    {"text": "Read the "},
    {"type": "link", "href": "https://example.com/guide", "children": [{"text": "release guide"}]},
    {"text": "."}
  ]
}
```

## Complete Document Example

Serialize this entire object once to obtain `content`. The tool's `file_name`
and short card `description` are separate arguments, not document-root fields.

```json
{
  "title": "Release review",
  "elements": [
    {"type": "paragraph", "children": [
      {"text": "The release is "},
      {"text": "ready for review", "bold": true},
      {"text": "."}
    ]},
    {"type": "header1", "children": [{"text": "Next steps"}]},
    {"type": "unordered_list", "items": [
      {"children": [{"text": "Confirm the release scope."}]},
      {"children": [{"text": "Share the test report."}]}
    ]},
    {"type": "check_list_item", "checked": false, "children": [{"text": "Approve publication."}]}
  ]
}
```

## Constraints and Native-Format Boundary

- Supply every required field and only the fields documented for that object.
- Do not provide `id`, `version`, `format_version`, `last_modify_user`, `cursors`,
  `style`, or other editor/collaboration metadata. These belong to native files
  or runtime data, not tool input.
- Structural objects under `items`, `rows` and `cells` are simplified objects,
  not typed native nodes. The application also creates code lines and void
  placeholders. Do not manually reproduce native structures.
- Only the element types and marks listed here are supported. Express images,
  embeds, formulas, multi-column layouts and other unsupported content as
  ordinary text or HTTP/HTTPS links where appropriate.
- Do not include internal citation tokens such as `<reference_0>` in content;
  use descriptive text or actual HTTP/HTTPS links instead.
- The compact JSON representation of the decoded document, preserving Unicode
  and omitting optional whitespace, must not exceed 400000 characters. The
  input string itself must not exceed 2400002 characters.
- At most 20000 inline nodes are allowed across the document, counting both
  text leaves and links, including text leaves inside links.

For native-format background, see the official [document model](https://haiwen.github.io/seadoc-specification/support-types/)
and its linked node references. Their additional fields and features do not
extend the accepted authoring subset defined here.
