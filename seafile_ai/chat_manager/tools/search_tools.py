import json
import logging
import os
import re
from pathlib import Path

from seafile_ai import config
from seafile_ai.chat_manager.utils.callbacker import ChatCallBacker
from seafile_ai.repo_metadata.constants import METADATA_TABLE
from seafile_ai.repo_metadata.metadata_server_api import MetadataServerAPI
from seafile_ai.repo_metadata.utils import get_metadata_by_path
from seafile_ai.search.repo_file_search_adapter import RepoFileSearchAdapter
from seafile_ai.search.seasearch_api import SeaSearchAPI
from seafile_ai.utils import get_file_content_by_seafobj, parse_file_content
from seafile_ai.utils.tools import BasicTool

logger = logging.getLogger(__name__)

RERANK_LIMIT = 6
FETCH_CONTENT_LIMIT = 4
SOURCE_CONTENT_LIMIT = 3000
SEARCH_LIMIT_MULTIPLIER = 3
SUPPORTED_FULLTEXT_SUFFIXES = {'.md', '.markdown', '.sdoc', '.docx', '.pdf', '.pptx'}

_SEARCH_TOOLS_RESULT_FORMAT = """
[
    {
        "label": "<reference_0>",
        "type": "seafile",
        "title": "Title",
        "content": "Search result content",
        "modified_time": "Unix timestamp"
        // ... Other useful information, e.g., snippets ...
    }, {
        "label": "<reference_1>",
        "type": "seafile",
        "title": "Title",
        "content": "Search result content",
        "modified_time": "Unix timestamp"
        // ... Other useful information, e.g., snippets ...
    }
]
"""


def strip_mark_tags(content):
    return re.sub(r'</?mark>', '', content or '')


def truncate_text(content, limit):
    content = (content or '').strip()
    if len(content) <= limit:
        return content
    return content[:limit] + '...'


class DocumentsSearch(BasicTool):
    tool = {
        'type': 'function',
        'function': {
            'name': 'documents_search',
            'description': (
                'This is the default search tool for library documents and document-based knowledge questions. '
                'Use short search keywords or a concise query to find relevant documents. '
                'Preserve important product names, config keys, file names, and error terms from the user request. '
                'The relevance decreases from the beginning to the end. '
                f'Results include labels such as <reference_0>. {_SEARCH_TOOLS_RESULT_FORMAT}. '
                'Do not make random or overly broad searches. '
                'If the search results are insufficient, do not pretend that the library documents answered the question.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': (
                            'The query should stay close to the user wording and usually be short keywords or a concise phrase. '
                            'Keep exact technical terms when they matter, such as product names, file names, config keys, '
                            'feature names, and error messages. For example, use "WebDAV", "LDAP", "seafile.conf", '
                            'or "repo token" directly when they are the important search terms.'
                        ),
                    },
                },
                'required': ['query'],
            },
        },
    }

    MAX_SOURCES_COUNT = 10
    SINGLE_TOOL_MAX_SOURCES_COUNT = 5

    def __init__(self):
        self.seasearch_api = SeaSearchAPI(config.SEASEARCH_URL, config.SEASEARCH_TOKEN)
        self.search_adapter = RepoFileSearchAdapter(self.seasearch_api)
        self.metadata_server_api = MetadataServerAPI('seafile-ai')

    def _search_documents(self, repo_id, query, count):
        return self.search_adapter.search_files(
            [(repo_id, None, None)],
            query,
            size=max(count * SEARCH_LIMIT_MULTIPLIER, 10),
            search_filename_only=False,
        )

    def _rerank_documents(self, query, candidates, context, count, app):
        if len(candidates) <= 1:
            return candidates[:count]

        prompt_items = []
        for index, item in enumerate(candidates[:RERANK_LIMIT], start=1):
            prompt_items.append({
                'index': index,
                'title': item['title'],
                'path': item['path'],
                'snippet': truncate_text(strip_mark_tags(item['snippet']), 400),
            })

        messages = [
            {
                'role': 'system',
                'content': (
                    'Rank the document candidates for the user query. '
                    'Return JSON only with key `indices`, whose value is an ordered array of candidate indices.'
                ),
            },
            {
                'role': 'user',
                'content': json.dumps({
                    'query': query,
                    'count': count,
                    'candidates': prompt_items,
                }, ensure_ascii=False),
            },
        ]

        try:
            response = app.llm_api.run(messages, context, json_mode=True)
            ranked_indices = json.loads(response).get('indices', [])
        except Exception as error:
            logger.warning('documents_search rerank failed: %s', error)
            ranked_indices = []

        ranked = []
        used = set()
        for index in ranked_indices:
            if not isinstance(index, int):
                continue
            if index < 1 or index > len(prompt_items):
                continue
            candidate = candidates[index - 1]
            key = (candidate['repo_id'], candidate['path'])
            if key in used:
                continue
            ranked.append(candidate)
            used.add(key)

        for candidate in candidates:
            key = (candidate['repo_id'], candidate['path'])
            if key in used:
                continue
            ranked.append(candidate)
            used.add(key)
        return ranked[:count]

    def _load_full_contents(self, candidates):
        content_map = {}
        for candidate in candidates[:FETCH_CONTENT_LIMIT]:
            path = candidate.get('path')
            repo_id = candidate.get('repo_id')
            if not path or not repo_id:
                continue
            try:
                row = get_metadata_by_path(repo_id, path, self.metadata_server_api)
            except Exception as error:
                logger.warning('documents_search get metadata failed: %s', error)
                continue
            if not row:
                continue
            obj_id = row.get(METADATA_TABLE.columns.obj_id.name)
            if not obj_id:
                continue
            suffix = Path(path).suffix.lower()
            content = ''
            if suffix in SUPPORTED_FULLTEXT_SUFFIXES:
                try:
                    file_content = get_file_content_by_seafobj(repo_id, obj_id)
                    content = parse_file_content(path, file_content)
                except Exception as error:
                    logger.warning('documents_search parse file failed: %s', error)
            content_map[path] = truncate_text(content, SOURCE_CONTENT_LIMIT) if content else ''
        return content_map

    def _format_candidates(self, search_results):
        candidates = []
        for item in search_results:
            if item.get('is_dir'):
                continue
            path = item.get('fullpath')
            if not path:
                continue
            candidates.append({
                'repo_id': item.get('repo_id'),
                'path': path,
                'title': item.get('name') or os.path.basename(path),
                'snippet': strip_mark_tags(item.get('content', '')),
                'modified_time': item.get('mtime'),
            })
        return candidates

    def execute(self, query, context, app, tool_executor, call_back):
        assert isinstance(query, str), 'Your search query must be a string'
        sources_results = list(tool_executor.cache.get('sources_results', []))
        existing_source_keys = {
            (source.get('repo_id'), source.get('path'))
            for source in sources_results
        }
        if len(sources_results) >= self.MAX_SOURCES_COUNT:
            return []

        count = min(self.MAX_SOURCES_COUNT - len(sources_results), self.SINGLE_TOOL_MAX_SOURCES_COUNT)
        repo_id = context['repo_id']
        query = query.strip()
        if not query:
            return []

        logger.info('documents_search query: %s', query)

        try:
            search_results = self._search_documents(repo_id, query, count)
        except Exception as error:
            logger.warning('documents_search failed: %s', error)
            search_results = []

        candidates = self._format_candidates(search_results)
        reranked_candidates = self._rerank_documents(query, candidates, context, count, app)
        reranked_candidates = [
            candidate
            for candidate in reranked_candidates
            if (candidate.get('repo_id'), candidate.get('path')) not in existing_source_keys
        ]
        full_content_map = self._load_full_contents(reranked_candidates)

        observation_results = []
        cached_sources = sources_results[:]
        reference_offset = len(sources_results)
        for index, candidate in enumerate(reranked_candidates, start=1):
            ai_summary = full_content_map.get(candidate['path']) or truncate_text(candidate['snippet'], SOURCE_CONTENT_LIMIT)
            source = {
                'type': 'seafile',
                'repo_id': candidate['repo_id'],
                'path': candidate['path'],
                'title': candidate['title'],
                'ai_summary': ai_summary,
                'modified_time': candidate['modified_time'],
                'content': ai_summary,
            }
            cached_sources.append(source)
            observation_results.append({
                'label': f'<reference_{reference_offset + index - 1}>',
                'type': source['type'],
                'title': source['title'],
                'content': source['content'],
                'modified_time': source['modified_time'],
            })

        tool_executor.cache['sources_results'] = cached_sources

        if isinstance(call_back, ChatCallBacker):
            call_back('update_execution_detail', {
                'SeaSearch query': query,
                'Search results': len(search_results),
                'New references': len(observation_results),
                'Full content fetched': len(full_content_map),
            })

        return observation_results
