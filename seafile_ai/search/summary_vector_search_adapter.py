import os

from seafile_ai.search.constants import SUMMARY_VECTOR_INDEX_PREFIX


class SummaryVectorSearchAdapter:
    def __init__(self, seasearch_api):
        self.seasearch_api = seasearch_api

    def search(self, repo_id, query_vector, size=10):
        data = {
            'query_field': 'vec',
            'k': size,
            'return_fields': [
                'repo_id', 'path', 'filename', 'obj_id', 'ai_summary',
                'ai_summary_mtime', 'mtime',
            ],
            'vector': query_vector,
            '_source': False,
        }
        response = self.seasearch_api.vector_search(SUMMARY_VECTOR_INDEX_PREFIX + repo_id, data) or {}
        hits = response.get('hits', {}).get('hits', [])
        results = []
        for hit in hits:
            fields = hit.get('fields', {})
            path = self._get_field(fields, 'path')
            if not path:
                continue
            results.append({
                'repo_id': self._get_field(fields, 'repo_id') or repo_id,
                'path': path,
                'title': self._get_field(fields, 'filename') or os.path.basename(path),
                'ai_summary': self._get_field(fields, 'ai_summary') or '',
                'modified_time': self._normalize_mtime(self._get_field(fields, 'mtime')),
                'score': hit.get('_score', 0),
                'source_type': 'summary_vector',
            })
        return results

    @staticmethod
    def _get_field(fields, name):
        value = fields.get(name)
        if isinstance(value, list):
            return value[0] if value else None
        return value

    @staticmethod
    def _normalize_mtime(value):
        if isinstance(value, (int, float)) and value > 100000000000:
            return value / 1000
        return value
