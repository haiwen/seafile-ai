# Builtin chat skills

Invoke a builtin skill using a leading command in the current user message:

```text
/sdoc-create Create a release plan from our discussion
```

`parser.py` recognizes the command; `loader.py` reads the skill document;
`registry.py` defines which tools that skill is allowed to register. Instructions
are stored in `builtin/<name>/SKILL.md`, with YAML metadata separated from the
body by `====================`, matching the SeaQA builtin document format.

Skills are selected before the first model call and expire with that request.
Neither conversation history nor natural-language intent activates a skill.
There is no model-callable skill loader or custom skill support.

To add a builtin, add its document and explicit tool policy in the registry.
Keep tool schemas, input validation and execution in `chat_manager/tools/`, not
in skill documents. The skills endpoint exposes names/descriptions to Seahub's
slash-command selector.

`create_sdoc` takes three required arguments: `file_name`, `description`, and
`elements` (the object containing `title` and body `elements`). It returns a
HTML-escaped `<seadoc ... />` reference to an already executed operation. The
model must include that exact tag in its final answer. SSE and stored chat
messages carry it inside the answer, without a separate artifacts field.

`SdocValidator.validate()` validates SDoc argument structure with `jsonschema` against the same
`SDOC_PARAMETERS` supplied to the model. The Schema is checked and its validator
created once when the class is defined. Validation limits and patterns are class
attributes, and validation helpers are class/static methods. A bounded traversal rejects excessive
depth, node count, total string content and non-finite numbers before Schema
validation. Separate semantic checks cover safe filenames/URLs, visible text,
colors, conflicting text marks, internal citation tokens and rectangular tables.
Validation does not rebuild or modify the document. Seahub independently
validates requests at the file-write boundary.
