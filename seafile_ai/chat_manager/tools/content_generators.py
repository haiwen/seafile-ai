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
