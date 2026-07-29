import json
import logging
import os
import re
from pathlib import Path

from seafile_ai import config
from seafile_ai.chat_manager.utils.callbacker import ChatCallBacker
from seafile_ai.repo_metadata.constants import METADATA_TABLE
from seafile_ai.repo_metadata.metadata_server_api import MetadataServerAPI
from seafile_ai.repo_metadata.utils import get_metadata_by_path, is_ai_summary_enabled
from seafile_ai.search.ai_summary_searcher import AISummarySearcher
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

    def _get_ai_summary_searcher(self, llm_api):
        return AISummarySearcher(self.metadata_server_api, llm_api)

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
                'match_type': item.get('match_type'),  # Include match_type to distinguish result sources
            })
        return candidates

    def _fallback_search_by_ai_summary(self, repo_id, query, remaining_count, app, context, exclude_keys):
        """
        Fallback to ai_summary search when SeaSearch results are insufficient

        Args:
            repo_id: Repository ID
            query: Search keyword/question
            remaining_count: Number of results still needed
            app: Application instance (contains llm_api)
            context: LLM call context
            exclude_keys: Set of (repo_id, path) tuples to exclude from results

        Returns:
            Tuple[List[dict], int, int, int, List[dict]] - (results, rows_scanned, matched_count, matched_details)
        """
        if not app or not app.llm_api:
            logger.warning('Cannot fallback to ai_summary search: llm_api is not available')
            return [], 0, 0, 0, []

        ai_summary_searcher = self._get_ai_summary_searcher(app.llm_api)

        logger.info('Falling back to ai_summary search for query: %s, remaining: %d', query, remaining_count)
        results, rows_scanned, matched_count, matched_details = ai_summary_searcher.search(
            repo_id, query, remaining_count, context
        )

        # Filter out already existing keys
        filtered_results = []
        for result in results:
            key = (result.get('repo_id'), result.get('fullpath'))
            if key not in exclude_keys:
                filtered_results.append(result)

        return filtered_results, rows_scanned, matched_count, matched_details

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

        # ---- Phase 1: SeaSearch (existing logic) ----
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

        # ---- Phase 2: AI Summary fallback ----
        ai_summary_used = False
        ai_summary_rows_scanned = 0
        ai_summary_matched = 0
        ai_summary_matched_details = []

        # Determine if fallback should be triggered based on config mode
        # True (supplementary mode): trigger when results are insufficient
        # False (fallback mode): trigger only when results are 0
        supplementary_mode = config.AI_SUMMARY_FALLBACK_SUPPLEMENTARY_MODE
        remaining = count - len(reranked_candidates)
        
        should_trigger_fallback = False
        if supplementary_mode and remaining > 0:
            # Supplementary mode: trigger when results are insufficient
            should_trigger_fallback = True
        elif not supplementary_mode and len(reranked_candidates) == 0:
            # Fallback mode: trigger only when results are 0
            should_trigger_fallback = True
            remaining = count  # Use full count since no results exist

        if should_trigger_fallback:
            try:
                if is_ai_summary_enabled(repo_id):
                    exclude_keys = existing_source_keys | {
                        (c['repo_id'], c['path']) for c in reranked_candidates
                    }
                    fallback_results, ai_summary_rows_scanned, ai_summary_matched, ai_summary_matched_details = (
                        self._fallback_search_by_ai_summary(
                            repo_id=repo_id,
                            query=query,
                            remaining_count=remaining,
                            app=app,
                            context=context,
                            exclude_keys=exclude_keys,
                        )
                    )
                    fallback_candidates = self._format_candidates(fallback_results)
                    reranked_candidates.extend(fallback_candidates[:remaining])
                    ai_summary_used = True
            except Exception as error:
                logger.warning('ai_summary fallback search failed: %s', error)

        # ---- Build results ----
        # Only load full content for SeaSearch candidates (not ai_summary fallback results)
        seasearch_candidates = [
            c for c in reranked_candidates if c.get('match_type') != 'ai_summary'
        ]
        full_content_map = self._load_full_contents(seasearch_candidates)

        observation_results = []
        cached_sources = sources_results[:]
        reference_offset = len(sources_results)
        for index, candidate in enumerate(reranked_candidates, start=1):
            if candidate.get('match_type') == 'ai_summary':
                content = truncate_text(candidate['snippet'], SOURCE_CONTENT_LIMIT)
                ai_summary = content
            else:
                content = full_content_map.get(candidate['path']) or truncate_text(candidate['snippet'], SOURCE_CONTENT_LIMIT)
                ai_summary = content

            source = {
                'type': 'seafile',
                'repo_id': candidate['repo_id'],
                'path': candidate['path'],
                'title': candidate['title'],
                'ai_summary': ai_summary,
                'modified_time': candidate['modified_time'],
                'content': content,
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
            fallback_mode = 'supplementary' if supplementary_mode else 'fallback'
            # Format matched_details as a readable string to display as a flat node
            if ai_summary_matched_details:
                matched_details_str = ', '.join(
                    f"{item['filepath']} ({item['score']:.2f})"
                    for item in ai_summary_matched_details
                )
            else:
                matched_details_str = '-'
                
            call_back('update_execution_detail', {
                'SeaSearch query': query,
                'Search results': len(search_results),
                'AI summary fallback mode': fallback_mode,
                'AI summary fallback used': ai_summary_used,
                'AI summary rows scanned': ai_summary_rows_scanned,
                'AI summary matched': ai_summary_matched,
                'AI summary matched details': matched_details_str,
                'New references': len(observation_results),
                'Full content fetched': len(full_content_map),
            })

        return observation_results
