from seafile_ai.chat_manager.utils.callbacker import ChatCallBacker
from seafile_ai.repo_metadata.constants import METADATA_TABLE
from seafile_ai.repo_metadata.metadata_server_api import MetadataServerAPI
from seafile_ai.repo_metadata.utils import query_metadata_rows
from seafile_ai.utils.tools import BasicTool


class ListFiles(BasicTool):
    tool = {
        'type': 'function',
        'function': {
            'name': 'list_files',
            'description': (
                'List all files and directories in the current library. '
                'Return the complete metadata record for every item as JSON. '
                'This tool returns metadata, not file content.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {},
            },
        },
    }

    def __init__(self):
        self.metadata_server_api = MetadataServerAPI('seafile-ai')

    def execute(self, context, call_back):
        repo_id = context['repo_id']
        sql = f'SELECT * FROM `{METADATA_TABLE.name}`'
        results = query_metadata_rows(repo_id, self.metadata_server_api, sql)
        if isinstance(call_back, ChatCallBacker):
            call_back('update_execution_detail', {
                'Records': len(results),
            })
        return results
