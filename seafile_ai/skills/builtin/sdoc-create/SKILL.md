name: sdoc-create
description: Create and save a rich SDoc document in the current library from the user's request and available sources.
====================

# Create an SDoc

This skill is active only because the current user explicitly invoked
`/sdoc-create task`. It applies to this request only.

1. Gather relevant information from the conversation and, when needed, library
   search or file-reading tools. Do not search unnecessarily.
2. Organize a complete, useful document in the requested language. Preserve
   user-provided names, quoted text, product identifiers and required details.
3. Call `create_sdoc` with `file_name`, a concise `description`, and `elements`.
   `elements` is the document object containing `title` and its body `elements`.
   Follow the tool's schema; do not generate node IDs, editor metadata or version
   fields. Use supported semantic blocks, including tables and columns where useful.
4. All files are saved in `/AI Generated/`. Supply a filename, not a directory.
   Do not include internal `<reference_N>` citation tokens in document contents.
   If useful, write a plain-text Sources section with real source information.
5. Include the exact `<seadoc ... />` string returned by the tool in the final
   answer, on its own line between paragraphs. Never wrap it in backticks or code
   fences, escape it, reconstruct it, or substitute a Markdown link.

Only `status="created"` confirms that a file exists. Explain failures honestly.
For `status="unknown"`, ask the user to check `/AI Generated/`; never retry the
mutation after an unconfirmed write. Do not repeat the entire document in chat.
Do not substitute Markdown generation for this skill's SDoc creation tool.

## Example: tool invocation and successful answer

User request:

```text
/sdoc-create Create a short project plan
```

Call the actual `create_sdoc` tool with arguments like the following. This JSON
is a tool-argument example, not text to print in the chat answer. Notice that
`elements` is an object containing both `title` and the body `elements` array.

```json
{
  "file_name": "Project plan.sdoc",
  "description": "Project goals and execution plan",
  "elements": {
    "title": {
      "children": [{"type": "text", "text": "Project plan"}]
    },
    "elements": [
      {
        "type": "paragraph",
        "children": [{"type": "text", "text": "This project aims to improve team collaboration."}]
      }
    ]
  }
}
```

Suppose the tool returns this exact string:

```text
<seadoc status="created" name="Project plan.sdoc" path="/AI Generated/Project plan.sdoc" doc_uuid="example-doc-uuid" description="Project goals and execution plan" />
```

Then the final answer could be:

```text
Created the project plan with project goals and execution details.

<seadoc status="created" name="Project plan.sdoc" path="/AI Generated/Project plan.sdoc" doc_uuid="example-doc-uuid" description="Project goals and execution plan" />
```

Code fences here only delimit examples in these instructions. In the actual
final answer, output the returned tag as a standalone line without code fences
or backticks. All metadata above is illustrative: never reuse example tags,
UUIDs, paths or descriptions. Copy only the actual tool result from this request,
even if the tool selected a different filename to avoid a conflict. Preserve
attribute order and HTML entities exactly, including `&amp;` and `&quot;`.

## Example: failed creation

If the tool returns:

```text
<seadoc status="failed" error_code="create_failed" />
```

The final answer could be:

```text
Document creation failed. The document was not saved.

<seadoc status="failed" error_code="create_failed" />
```

## Example: unconfirmed creation

If the tool returns:

```text
<seadoc status="unknown" error_code="creation_unconfirmed" />
```

The final answer could be:

```text
Document creation could not be confirmed. Please check the library's /AI Generated/ folder. I will not retry this request to avoid creating a duplicate.

<seadoc status="unknown" error_code="creation_unconfirmed" />
```

If no tool result tag was received, do not invent one or copy one from these
examples or conversation history. Explain that creation was not confirmed.
