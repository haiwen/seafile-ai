import json
import os

from seafile_ai.search.constants import REPO_FILE_INDEX_PREFIX


class RepoFileSearchAdapter:
    def __init__(self, seasearch_api):
        self.seasearch_api = seasearch_api

    def _make_query_searches(self, keyword, search_filename_only):
        match_query_kwargs = {'minimum_should_match': '-25%'}

        def _make_match_query(field, query, **kwargs):
            payload = {'query': query}
            payload.update(kwargs)
            return {'match': {field: payload}}

        searches = [
            _make_match_query('filename', keyword, **match_query_kwargs),
            {
                'match': {
                    'filename.ngram': {
                        'query': keyword,
                        'minimum_should_match': '80%',
                    }
                }
            },
        ]
        if not search_filename_only:
            searches.append(_make_match_query('content', keyword, **match_query_kwargs))
            searches.append(_make_match_query('description', keyword, **match_query_kwargs))
        return searches

    def _ensure_filter_exists(self, query_map):
        if 'filter' not in query_map['bool']:
            query_map['bool']['filter'] = []
        return query_map

    def _add_path_filter(self, query_map, search_path):
        if search_path is None:
            return query_map
        query_map = self._ensure_filter_exists(query_map)
        query_map['bool']['filter'].append({'prefix': {'path': search_path}})
        return query_map

    def _add_suffix_filter(self, query_map, suffixes):
        if suffixes is None:
            return query_map
        query_map = self._ensure_filter_exists(query_map)
        if isinstance(suffixes, list):
            query_map['bool']['filter'].append({'terms': {'suffix': [suffix.lower() for suffix in suffixes]}})
        else:
            query_map['bool']['filter'].append({'term': {'suffix': suffixes.lower()}})
        return query_map

    def _add_obj_type_filter(self, query_map, obj_type):
        if obj_type is None:
            return query_map
        query_map = self._ensure_filter_exists(query_map)
        query_map['bool']['filter'].append({'term': {'is_dir': obj_type == 'dir'}})
        return query_map

    def _is_valid_range(self, data_range):
        return isinstance(data_range, list) and len(data_range) == 2 and not all(value is None for value in data_range)

    def _add_time_range_filter(self, query_map, time_range):
        if not self._is_valid_range(time_range):
            return query_map
        search_content = {}
        time_from = time_range[0] * 1000 if time_range[0] else None
        time_to = time_range[1] * 1000 if time_range[1] else None
        if time_from:
            search_content['gte'] = time_from
        if time_to:
            search_content['lte'] = time_to
        query_map = self._ensure_filter_exists(query_map)
        query_map['bool']['filter'].append({'range': {'mtime': search_content}})
        return query_map

    def _add_size_range_filter(self, query_map, size_range):
        if not self._is_valid_range(size_range):
            return query_map
        search_content = {}
        if size_range[0]:
            search_content['gte'] = size_range[0]
        if size_range[1]:
            search_content['lte'] = size_range[1]
        query_map = self._ensure_filter_exists(query_map)
        query_map['bool']['filter'].append({'range': {'size': search_content}})
        return query_map

    def search_files(self, repos, keyword, start=0, size=10, suffixes=None, search_path=None, obj_type=None,
                     time_range=None, size_range=None, search_filename_only=None):
        bulk_search_params = []
        current_search_path = search_path
        for repo_id, origin_repo_id, origin_path in repos:
            query_map = {'bool': {}}
            target_repo_id = origin_repo_id or repo_id
            target_search_path = current_search_path

            if keyword:
                query_map['bool']['should'] = self._make_query_searches(keyword, search_filename_only)
            if origin_repo_id:
                if current_search_path:
                    target_search_path = os.path.join(origin_path, current_search_path.strip('/'))
                else:
                    target_search_path = origin_path

            query_map = self._add_suffix_filter(query_map, suffixes)
            query_map = self._add_path_filter(query_map, target_search_path)
            query_map = self._add_obj_type_filter(query_map, obj_type)
            query_map = self._add_time_range_filter(query_map, time_range)
            query_map = self._add_size_range_filter(query_map, size_range)

            data = {
                'from': start,
                'size': size,
                '_source': ['path', 'repo_id', 'filename', 'is_dir', 'mtime', 'size'],
                'sort': ['_score'],
                'highlight': {
                    'pre_tags': ['<mark>'],
                    'post_tags': ['</mark>'],
                    'fields': {'content': {}},
                }
            }
            if query_map.get('bool'):
                query_map['bool']['minimum_should_match'] = 1
                data['query'] = query_map

            bulk_search_params.append({
                'index': REPO_FILE_INDEX_PREFIX + target_repo_id,
                'query': data,
            })
            current_search_path = None

        response = self.seasearch_api.unified_search(json.dumps({'index_queries': bulk_search_params}))
        hits = response.get('hits', {}).get('hits', []) if response else []
        files = []
        for hit in hits:
            source = hit.get('_source', {})
            result = {
                'repo_id': source.get('repo_id'),
                'fullpath': source.get('path'),
                'name': os.path.basename(source.get('path') or ''),
                'is_dir': source.get('is_dir'),
                'score': hit.get('_score'),
                '_id': hit.get('_id'),
                'mtime': source.get('mtime') / 1000 if source.get('mtime') is not None else 0,
                'size': source.get('size'),
            }
            highlight_content = hit.get('highlight', {}).get('content', [None])[0]
            if highlight_content:
                result['snippet'] = highlight_content
            files.append(result)
        return files
