from seafile_ai.chat_manager.utils.callbacker import ChatCallBacker
from seafile_ai.utils.tools import BasicTool


class ListFiles(BasicTool):
    tool = {
        'type': 'function',
        'function': {
            'name': 'list_files',
            'description': (
                'List all visible files in a directory and its subdirectories with their current AI summaries. '
                'Use this to inspect a directory for duplicate or semantically similar documents. '
                'Do not use it for ordinary document search questions.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {
                        'type': 'string',
                        'description': 'An absolute directory path in the current library.',
                    },
                },
                'required': ['path'],
            },
        },
    }

    def execute(self, path, context, app, call_back):
        assert isinstance(path, str) and path.startswith('/'), 'Your path must be an absolute directory path'

        results = app.seahub_api.list_file_summaries(
            context['repo_id'], context['username'], path)
        if isinstance(call_back, ChatCallBacker):
            stats = results.get('traversal_stats', {})
            call_back('update_execution_detail', {
                'Path': stats.get('requested_path', path),
                'Files with valid summaries': stats.get('valid_summary_count', 0),
                'Uncomparable files': len(results.get('uncomparable_files', [])),
            })
        return results
