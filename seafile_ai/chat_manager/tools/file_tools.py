import posixpath
from datetime import datetime

from seafile_ai.chat_manager.utils.callbacker import ChatCallBacker
from seafile_ai.repo_metadata.constants import METADATA_TABLE
from seafile_ai.utils.tools import BasicTool


def _is_ai_summary_mtime_valid(ai_summary_mtime):
    if not isinstance(ai_summary_mtime, str) or not ai_summary_mtime:
        return False
    try:
        datetime.fromisoformat(ai_summary_mtime.replace('Z', '+00:00'))
        return True
    except (TypeError, ValueError):
        return False


def _extract_file_summaries(path, records):
    results = []
    uncomparable_files = []
    stats = {
        'requested_path': path,
        'returned_file_count': len(records),
        'valid_summary_count': 0,
        'summary_missing_count': 0,
        'summary_empty_count': 0,
        'summary_mtime_invalid_count': 0,
    }
    for record in records:
        file_id = record.get(METADATA_TABLE.columns.obj_id.name)
        parent_dir = record.get(METADATA_TABLE.columns.parent_dir.name) or ''
        file_name = record.get(METADATA_TABLE.columns.file_name.name) or ''
        if not file_id or not parent_dir.startswith('/') or not file_name:
            continue

        file_info = {
            'file_id': file_id,
            'file_name': file_name,
            'path': posixpath.join(parent_dir, file_name),
        }
        ai_summary = record.get(METADATA_TABLE.columns.ai_summary.name)
        if ai_summary is None:
            stats['summary_missing_count'] += 1
            uncomparable_files.append({**file_info, 'reason': 'ai_summary_missing'})
            continue

        if not isinstance(ai_summary, str) or not ai_summary.strip():
            stats['summary_empty_count'] += 1
            uncomparable_files.append({**file_info, 'reason': 'ai_summary_empty'})
            continue

        ai_summary_mtime = record.get(METADATA_TABLE.columns.ai_summary_mtime.name)
        if not _is_ai_summary_mtime_valid(ai_summary_mtime):
            stats['summary_mtime_invalid_count'] += 1
            uncomparable_files.append({**file_info, 'reason': 'ai_summary_mtime_invalid'})
            continue

        results.append({
            **file_info,
            'ai_summary': ai_summary.strip(),
            'ai_summary_mtime': ai_summary_mtime,
        })
        stats['valid_summary_count'] += 1

    return {
        'files': results,
        'uncomparable_files': uncomparable_files,
        'traversal_stats': stats,
    }


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

        repo_id = context['repo_id']
        path = posixpath.normpath(path)
        if path == '.':
            path = '/'
        response = app.seahub_api.list_metadata_records(
            repo_id, context['username'], path)
        results = _extract_file_summaries(path, response.get('records', []))
        if isinstance(call_back, ChatCallBacker):
            stats = results.get('traversal_stats', {})
            call_back('update_execution_detail', {
                'Path': stats.get('requested_path', path),
                'Files with valid summaries': stats.get('valid_summary_count', 0),
                'Uncomparable files': len(results.get('uncomparable_files', [])),
            })
        return results
