# SeaDoc Authoring Specification

## Introduction

This reference describes the document model, node structures and common content
fields of the simplified SeaDoc authoring format.

The organization and terminology follow the official
[SeaDoc Specification](https://haiwen.github.io/seadoc-specification/): document
model, text leaves, block elements and inline elements. However, the examples
here use the application's **simplified authoring format**, not the native
`.sdoc` file format. Native examples from the official manual are not valid
documents in this simplified format.

Only semantic content is needed. The application supplies native structural
wrappers, node IDs, document metadata and editor layout. Fonts, colors and
advanced elements are outside this authoring subset.

## Document Model

### Document Format

The document root has exactly one required field:

| Field | Type | Meaning |
| --- | --- | --- |
| `elements` | array | Between 1 and 200 block elements, in reading order. |

Titles and subtitles are block elements within `elements`, usually at the
beginning of the document. Neither is required, and their positions are not fixed.

```json
{
  "elements": [
    {"type": "title", "children": [{"text": "Meeting notes"}]},
    {"type": "paragraph", "children": [{"text": "The team reviewed the release."}]}
  ]
}
```

Examples in this reference show JSON objects. Nodes remain objects within the
document, not individually serialized strings. Markdown code fences are only
used to display examples and are not part of the document data.

### Node Structure

A SeaDoc document is a tree with three node categories:

1. **Document root**: the document itself, containing top-level element nodes in its `elements` property.
2. **Element nodes**: containers holding other element nodes or text nodes in their `children` property.
3. **Text nodes**: leaf nodes containing text content and optional formatting marks.

Every element and text node requires a non-empty string `id` that is unique within the document. Consumers must not require a particular UUID or slug format.

The ID requirement above applies to the final native document. In the simplified
authoring format, omit IDs; the application generates unique IDs for all element
and text nodes during compilation. Lists use `items` and code blocks use `text`
as shorthand for native child structures; a divider needs only `type`.
Every supplied `children` array must be nonempty; use `{"text": ""}` for blank
editable content.

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

### Title and Subtitle

`title` represents a document title; `subtitle` represents a document subtitle.
They are top-level elements, usually at the beginning of `elements`, rather than
document-root fields. Their presence and position are not mandatory.

- Required fields: `type: "title"` or `"subtitle"`, `children` (array).
- Children: text leaves and supported inline links directly.
- Following content belongs in sibling blocks, not inside the title or subtitle.

```json
{"type": "title", "children": [{"text": "Release review"}]}
```

```json
{"type": "subtitle", "children": [{"text": "Planning notes"}]}
```

### Paragraph

`paragraph` represents ordinary editable prose.

- Required fields: `type: "paragraph"`, `children` (array).
- Children: text leaves and inline links, not other blocks.

```json
{"type": "paragraph", "children": [{"text": "Record decisions and next steps here."}]}
```

### Heading

`header1` through `header6` represent section headings at levels 1 through 6,
similar to Markdown `#` through `######`. Use `title` for a document title,
not a section heading.

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

- Required fields: `type: "table"`, `children` (array of 1–100 `table_row` elements).
- Each row has `type: "table_row"` and `children` (array of 1–20 `table_cell`
  elements). Every row must have the same number of cells.
- Each cell has `type: "table_cell"` and `children` (nonempty array of text leaves
  and/or inline links). Cells directly contain text or links, without paragraph
  wrappers. Blocks and nested tables are not supported in cells.
- The hierarchy is `table -> table_row -> table_cell -> text or inline link`,
  using `children` at each level. Rows and cells cannot appear at the document root.
- If a header is needed, put its text in the first row. Do not add a Markdown
  separator row or header flags.
- Do not supply widths, styles or alignment; the application supplies layout defaults.

```json
{
  "type": "table",
  "children": [
    {"type": "table_row", "children": [
      {"type": "table_cell", "children": [{"text": "Action"}]},
      {"type": "table_cell", "children": [{"text": "Owner"}]}
    ]},
    {"type": "table_row", "children": [
      {"type": "table_cell", "children": [{"text": "Review scope"}]},
      {"type": "table_cell", "children": [{"text": "Team"}]}
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
- Allowed in titles, subtitles, paragraphs, blockquotes, list items and table cells,
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

This example combines a title, a subtitle, a paragraph, a section heading and a list
under one document root.

```json
{
  "elements": [
    {"type": "title", "children": [{"text": "Release review"}]},
    {"type": "subtitle", "children": [{"text": "Planning notes"}]},
    {"type": "paragraph", "children": [
      {"text": "The release is "},
      {"text": "ready for review", "bold": true},
      {"text": "."}
    ]},
    {"type": "header1", "children": [{"text": "Next steps"}]},
    {"type": "unordered_list", "items": [
      {"children": [{"text": "Confirm the release scope."}]},
      {"children": [{"text": "Share the test report."}]}
    ]}
  ]
}
```

## Constraints and Native-Format Boundary

- Supply every required field and only the fields documented for that object.
- Do not provide `id`, `version`, `format_version`, `last_modify_user`, `cursors`,
  `style`, or other editor/collaboration metadata. These belong to native files
  or runtime data, not the simplified authoring format.
- List objects under `items` are simplified objects, not typed native nodes.
  Table rows and cells, in contrast, must be typed elements nested through
  `children`. The application creates native list wrappers, code lines and void
  placeholders.
- Only the element types and marks listed here are supported. Express images,
  embeds, formulas, multi-column layouts and other unsupported content as
  ordinary text or HTTP/HTTPS links where appropriate.
- Do not include internal citation tokens such as `<reference_0>` in content;
  use descriptive text or actual HTTP/HTTPS links instead.
- The compact JSON representation of the decoded document, preserving Unicode
  and omitting optional whitespace, must not exceed 400000 characters. The
  serialized JSON string must not exceed 2400002 characters.
- At most 20000 inline nodes are allowed across the document, counting both
  text leaves and links, including text leaves inside links.

For native-format background, see the official [document model](https://haiwen.github.io/seadoc-specification/support-types/)
and its linked node references. Their additional fields and features do not
extend the accepted authoring subset defined here.
