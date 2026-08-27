import json
from pathlib import Path

from seafile_ai import config
from seafile_ai.chat_manager.utils.callbacker import ChatCallBacker
from seafile_ai.repo_metadata.constants import METADATA_TABLE
from seafile_ai.repo_metadata.metadata_server_api import MetadataServerAPI
from seafile_ai.repo_metadata.utils import get_file_id_by_path, get_repo_info, is_repo_metadata_enabled, query_metadata_rows
from seafile_ai.utils import FileSizeLimitExceeded, parse_file
from seafile_ai.utils.tools import BasicTool


SUPPORTED_READ_FILE_SUFFIXES = {'.md', '.markdown', '.sdoc', '.docx', '.pdf', '.pptx'}


class ListFiles(BasicTool):
    tool = {
        'type': 'function',
        'function': {
            'name': 'list_files',
            'description': (
                'List files and directories in the current library. '
                'Return up to the configured maximum number of metadata records as JSON. '
                'This tool returns metadata, not file content. '
                'Set include_dirs to true only when the user asks for directories. '
                'IMPORTANT: Each returned record contains a `path` field wrapped in '
                '<seafile-ai-file>...</seafile-ai-file> tags. When mentioning file paths '
                'in your final answer, you MUST output the `path` field verbatim without '
                'stripping the tags, converting it to Markdown links, or wrapping it in backticks. '
                'Do not apply these tags to search results from documents_search; use <reference_N> labels instead.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'name_contains': {
                        'type': 'string',
                        'description': (
                            'Case-insensitive text contained in the file or directory name. '
                            'Use this when the user asks to find files by name instead of listing the whole library.'
                        ),
                    },
                    'directory': {
                        'type': 'string',
                        'description': (
                            'Absolute directory path whose contents and nested subdirectories should be searched, '
                            'for example "/a/b/c". Omit this to search the whole library.'
                        ),
                    },
                    'include_dirs': {
                        'type': 'boolean',
                        'description': (
                            'Whether to include directories in the results. '
                            'Set to false to return only files. Default is false.'
                        ),
                    },
                    'max_records': {
                        'type': 'integer',
                        'description': (
                            f'Maximum number of records to return, from 1 to {config.DEFAULT_LIST_FILES_MAX_RECORDS}. '
                            'When the user asks for a specific number of files, such as "top 10" or "前10个", '
                            'you MUST set this to that number. Otherwise omit it to use the configured default.'
                        ),
                    },
                },
            },
        },
    }

    def __init__(self):
        self.metadata_server_api = MetadataServerAPI('seafile-ai')

    def execute(self, name_contains=None, directory=None, include_dirs=None, max_records=None, context=None, call_back=None):

        repo_id = context['repo_id'] if context else None
        if not repo_id:
            return {'records': [], 'warning': 'No repository context provided.'}

        include_dirs = include_dirs if include_dirs is not None else False
        max_records = max_records if max_records is not None else config.DEFAULT_LIST_FILES_MAX_RECORDS
        try:
            max_records = int(max_records)
        except (TypeError, ValueError):
            return {'records': [], 'warning': 'max_records must be a positive integer.'}
        if max_records < 1:
            return {'records': [], 'warning': 'max_records must be a positive integer.'}
        max_records = min(max_records, config.DEFAULT_LIST_FILES_MAX_RECORDS)
        if directory is not None:
            if not isinstance(directory, str) or not directory.startswith('/'):
                return {'records': [], 'warning': 'directory must be an absolute path.'}
            directory = directory.rstrip('/') or '/'
        if name_contains is not None:
            if not isinstance(name_contains, str) or not name_contains.strip():
                return {'records': [], 'warning': 'name_contains must be a non-empty string.'}
            name_contains = name_contains.strip()

        metadata_enabled = is_repo_metadata_enabled(repo_id)
        if not metadata_enabled:
            warning = (
                'Cannot list files because metadata is disabled for this library. '
                'Tell the user to enable library metadata before retrying. Do not ask for a directory, '
                'file-name keyword, or an exported file list because those filters are unavailable until metadata is enabled.'
            )
            return self._build_response(
                [], warning, call_back, include_dirs, directory, name_contains,
                {'Mode': 'metadata disabled', 'Limit': max_records},
            )

        is_dir_col = METADATA_TABLE.columns.is_dir.name
        file_name_col = METADATA_TABLE.columns.file_name.name
        file_mtime_col = METADATA_TABLE.columns.file_mtime.name
        parent_dir_col = METADATA_TABLE.columns.parent_dir.name
        sql = f'SELECT * FROM `{METADATA_TABLE.name}`'
        params = []
        conditions = []
        if not include_dirs:
            conditions.append(f'(`{is_dir_col}` = false OR `{is_dir_col}` IS NULL)')
        if directory is not None:
            conditions.append(f'`{parent_dir_col}` ILIKE ?')
            params.append(f'%{directory}%')
        if name_contains is not None:
            conditions.append(f'`{file_name_col}` ILIKE ?')
            params.append(f'%{name_contains}%')
        if conditions:
            sql += ' WHERE ' + ' AND '.join(conditions)
        sql += f' ORDER BY `{file_mtime_col}` DESC'

        results = query_metadata_rows(repo_id, self.metadata_server_api, sql, params=params, limit=max_records + 1)
        is_truncated = len(results) > max_records
        results = results[:max_records]
        for record in results:
            parent_dir = record.get(parent_dir_col)
            file_name = record.get(file_name_col)
            if isinstance(parent_dir, str) and isinstance(file_name, str) and file_name:
                raw_path = f'{parent_dir.rstrip("/")}/{file_name}'
                record['path'] = f'<seafile-ai-file>{raw_path}</seafile-ai-file>'
        warning = None
        if is_truncated:
            warning = (
                f'Results are limited to the first {max_records} records. '
                'Ask for a more specific directory or file name to narrow the result.'
            )

        query_detail = {
            'Mode': 'metadata query',
            'SQL': sql,
            'Parameters': params,
            'Limit': max_records,
        }
        return self._build_response(results, warning, call_back, include_dirs, directory, name_contains, query_detail)

    def _build_response(self, results, warning, call_back, include_dirs, directory, name_contains, query_detail):
        if isinstance(call_back, ChatCallBacker):
            detail = {
                'Records': len(results),
                'Query': json.dumps(query_detail, ensure_ascii=False),
            }
            if warning:
                detail['Warning'] = warning
            if not include_dirs:
                detail['Filter'] = 'files only (directories excluded)'
            if directory is not None:
                detail['Directory'] = directory
            if name_contains is not None:
                detail['Name contains'] = name_contains
            call_back('update_execution_detail', detail)

        response = {'records': results}
        if warning:
            response['warning'] = warning

        return response


class ReadFiles(BasicTool):
    tool = {
        'type': 'function',
        'function': {
            'name': 'read_files',
            'description': (
                'Read the content of specific files in the current library. '
                'This tool reads file content, not metadata. '
                f'Read at most {config.READ_FILES_MAX_FILES} files in one call.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'file_paths': {
                        'type': 'array',
                        'description': 'Exact file paths in the current library.',
                        'items': {
                            'type': 'string',
                        },
                        'minItems': 1,
                        'maxItems': config.READ_FILES_MAX_FILES,
                    },
                },
                'required': ['file_paths'],
            },
        },
    }

    def execute(self, file_paths, context, call_back):
        assert isinstance(file_paths, list), 'file_paths must be a list'

        repo_id = context['repo_id']
        repo = get_repo_info(repo_id)
        results = []
        total_chars = 0
        for index, file_path in enumerate(file_paths):
            if index >= config.READ_FILES_MAX_FILES:
                results.append({
                    'path': file_path,
                    'error': f'File limit exceeded (maximum {config.READ_FILES_MAX_FILES} files)',
                })
                continue

            if total_chars >= config.READ_FILES_MAX_TOTAL_CHARS:
                results.append({
                    'path': file_path,
                    'error': f'Content limit reached (maximum {config.READ_FILES_MAX_TOTAL_CHARS} characters)',
                })
                continue

            if isinstance(file_path, str) and file_path.startswith('<seafile-ai-file>') and file_path.endswith('</seafile-ai-file>'):
                file_path = file_path[len('<seafile-ai-file>'):-len('</seafile-ai-file>')]

            if (
                not isinstance(file_path, str)
                or not file_path.startswith('/')
                or any(part in ('.', '..') for part in Path(file_path).parts)
            ):
                results.append({'path': file_path, 'error': 'Invalid file path'})
                continue

            if Path(file_path).suffix.lower() not in SUPPORTED_READ_FILE_SUFFIXES:
                results.append({'path': file_path, 'error': 'Unsupported file type'})
                continue

            obj_id = get_file_id_by_path(repo, file_path) if repo else None
            if not obj_id:
                results.append({'path': file_path, 'error': 'File not found'})
                continue

            try:
                content = parse_file(file_path, repo_id, obj_id, config.READ_FILES_MAX_FILE_SIZE)
            except FileSizeLimitExceeded:
                results.append({
                    'path': file_path,
                    'error': f'File size exceeds {config.READ_FILES_MAX_FILE_SIZE} bytes limit',
                })
                continue
            except Exception as error:
                results.append({'path': file_path, 'error': str(error)})
                continue

            remaining_chars = config.READ_FILES_MAX_TOTAL_CHARS - total_chars
            if len(content) > remaining_chars:
                results.append({
                    'path': f'<seafile-ai-file>{file_path}</seafile-ai-file>',
                    'content': content[:remaining_chars],
                    'truncated': True,
                })
                total_chars = config.READ_FILES_MAX_TOTAL_CHARS
                continue

            results.append({
                'path': f'<seafile-ai-file>{file_path}</seafile-ai-file>',
                'content': content,
            })
            total_chars += len(content)

        if isinstance(call_back, ChatCallBacker):
            call_back('update_execution_detail', {
                'Files read': sum('content' in item for item in results),
            })
        return results
