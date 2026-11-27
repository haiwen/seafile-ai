from seafile_ai.chat_manager.utils.sdoc import get_sdoc_specification
from seafile_ai.utils.tools import BasicTool


class GetSdocSpecification(BasicTool):
    tool = {
        'type': 'function',
        'function': {
            'name': 'get_sdoc_specification',
            'description': (
                'Read the SeaDoc authoring specification, including supported fields, '
                'node structures, constraints and examples. Call this tool and read its '
                'result before constructing content for generate_sdoc. This only returns '
                'documentation; it does not generate a document or finish the request.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {},
                'required': [],
                'additionalProperties': False,
            },
        },
    }

    def execute(self):
        return get_sdoc_specification()
