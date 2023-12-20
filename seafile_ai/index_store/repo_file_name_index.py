import os
import logging

from seafile_ai.utils import get_library_diff_files
from seafile_ai import config

logger = logging.getLogger(__name__)

SEASEARCH_BULK_OPETATE_LIMIT = 2000


class RepoFileNameIndex(object):
    index_name = 'repofilenames'
    mapping = {
        'properties': {
            'repo_id': {
                'type': 'keyword',
            },
            'path': {
                'type': 'keyword'
            },
            'filename': {
                'type': 'text',
                'fields': {
                    'ngram': {
                        'type': 'text',
                        'index': True,
                        'analyzer': 'seafile_file_name_ngram_analyzer',
                    },
                },
            },
            'suffix': {
                'type': 'keyword'
            },
            'is_dir': {
                'type': 'boolean',
            }
        }
    }

    index_settings = {
        'analysis': {
            'analyzer': {
                'seafile_file_name_ngram_analyzer': {
                    'type': 'custom',
                    'tokenizer': 'seafile_file_name_ngram_tokenizer',
                    'filter': [
                        'lowercase',
                    ],
                }
            },
            'tokenizer': {
                'seafile_file_name_ngram_tokenizer': {
                    'type': 'ngram',
                    'min_gram': '3',
                    'max_gram': '4',
                }
            }
        }
    }

    shard_num = config.SHARD_NUM

    def __init__(self, seasearch_api, repo_data):
        self.seasearch_api = seasearch_api
        self.repo_data = repo_data
        self.create_index_if_missing()

    def create_index_if_missing(self):
        if not self.seasearch_api.check_index_mapping(self.index_name).get('is_exist'):
            data = {
                'name': self.index_name,
                'shard_num': self.shard_num,
                'mappings': self.mapping,
                'settings': self.index_settings
            }
            self.seasearch_api.create_index(data)

    def check_index(self, index_name):
        return self.seasearch_api.check_index_mapping(index_name).get('is_exist')

    def _add_repos_filter(self, query_map, repos):
        repo_search_dsl = []
        repo_search_dsl.append({
            'bool': {
                'must': [
                    {'terms': {
                        'repo_id': repos
                    }},
                ]
            }
        })

        repo_filter = repo_search_dsl[0]
        query_map['bool']['filter'].append(repo_filter)

        return query_map

    def _make_query_searches(self, keyword):
        match_query_kwargs = {'minimum_should_match': '-25%'}

        def _make_match_query(field, key_word, **kw):
            q = {'query': key_word}
            q.update(kw)
            return {'match': {field: q}}

        searches = []
        searches.append(_make_match_query('filename', keyword, **match_query_kwargs))
        searches.append({
            'match': {
                'filename.ngram': {
                    'query': keyword,
                    'minimum_should_match': '80%',
                }
            }
        })
        return searches

    def search_files(self, repos_map, keyword, start=0, size=10):
        query_map = {'bool': {'filter': [], 'should': [], 'minimum_should_match': 1}}
        query_map = self._add_repos_filter(query_map, repos_map)

        searches = self._make_query_searches(keyword)
        query_map['bool']['should'] = searches

        data = {
            'query': query_map,
            'from': start,
            'size': size,
            '_source': ['path', 'repo_id', 'filename', 'is_dir'],
            'sort': ['_score']
        }

        results = self.seasearch_api.normal_search(self.index_name, data)
        total = results.get('hits', {}).get('total', {}).get('value', 0)
        hits = results.get('hits', {}).get('hits', [])

        files = []
        for hit in hits:
            source = hit.get('_source')
            score = hit.get('_score')
            r = {
                'repo_id': source['repo_id'],
                'fullpath': source['path'],
                'name': source['filename'],
                'is_dir': source['is_dir'],
                'score': score,
            }
            files.append(r)

        return files, total

    @staticmethod
    def get_file_suffix(path):
        try:
            name = os.path.basename(path)
            suffix = os.path.splitext(name)[1][1:]
            if suffix:
                return suffix.lower()
            return None
        except:
            return None

    def add_files(self, repo_id, files):
        bulk_add_params = []
        for file_info in files:
            path = file_info[0]
            obj_id = file_info[1]
            mtime = file_info[2]
            size = file_info[3]
            filename = os.path.basename(path)
            suffix = self.get_file_suffix(path)

            index_info = {'index': {'_index': self.index_name, '_id': repo_id + path}}
            doc_info = {
                'repo_id': repo_id,
                'path': path,
                'suffix': suffix,
                'filename': filename,
                'is_dir': False,
            }

            bulk_add_params.append(index_info)
            bulk_add_params.append(doc_info)

            # bulk add every 2000 params
            if len(bulk_add_params) >= SEASEARCH_BULK_OPETATE_LIMIT:
                self.seasearch_api.bulk(bulk_add_params)
                bulk_add_params = []
        if bulk_add_params:
            self.seasearch_api.bulk(bulk_add_params)

    def add_dirs(self, repo_id, dirs):
        bulk_add_params = []
        for dir in dirs:
            path = dir[0]
            obj_id = dir[1]
            mtime = dir[2]
            size = dir[3]

            if path == '/':
                repo = self.repo_data.get_repo_name_mtime_size(repo_id)
                if not repo:
                    return

                filename = repo[0]['name']
            else:
                filename = os.path.basename(path)

            path = path + '/' if path != '/' else path
            index_info = {'index': {'_index': self.index_name, '_id': repo_id + path}}
            doc_info = {
                'repo_id': repo_id,
                'path': path,
                'suffix': None,
                'filename': filename,
                'is_dir': True,
            }
            bulk_add_params.append(index_info)
            bulk_add_params.append(doc_info)

            # bulk add every 2000 params
            if len(bulk_add_params) >= SEASEARCH_BULK_OPETATE_LIMIT:
                self.seasearch_api.bulk(bulk_add_params)
                bulk_add_params = []
        if bulk_add_params:
            self.seasearch_api.bulk(bulk_add_params)

    def delete_files(self, repo_id, files):
        delete_params = []
        for file in files:
            path = file[0]
            _id = repo_id + path
            delete_params.append({'delete': {'_id': _id, '_index': self.index_name}})
            # bulk add every 2000 params
            if len(delete_params) >= SEASEARCH_BULK_OPETATE_LIMIT:
                self.seasearch_api.bulk(delete_params)
                delete_params = []
        if delete_params:
            self.seasearch_api.bulk(delete_params)

    def delete_dirs(self, repo_id, dirs):
        delete_params = []
        for dir in dirs:
            path = dir
            _id = repo_id + path
            delete_params.append({'delete': {'_id': _id, '_index': self.index_name}})
            # bulk add every 2000 params
            if len(delete_params) >= SEASEARCH_BULK_OPETATE_LIMIT:
                self.seasearch_api.bulk(delete_params)
                delete_params = []
        if delete_params:
            self.seasearch_api.bulk(delete_params)

    def add(self, repo_id, old_commit_id, new_commit_id):
        self.update(repo_id, old_commit_id, new_commit_id)

    def update(self, repo_id, old_commit_id, new_commit_id):
        added_files, deleted_files, modified_files, added_dirs, deleted_dirs = \
            get_library_diff_files(repo_id, old_commit_id, new_commit_id)

        need_deleted_files = deleted_files
        self.delete_files(repo_id, need_deleted_files)

        self.delete_dirs(repo_id, deleted_dirs)

        need_added_files = added_files + modified_files
        self.add_files(repo_id, need_added_files)

        self.add_dirs(repo_id, added_dirs)

    def delete_documents_by_repo(self, repo_id):
        per_size = 2000
        start = 0
        delete_params = []
        while True:
            data = {
                "query": {
                    "term": {
                        "repo_id": repo_id
                    }
                },
                "from": start,
                "size": per_size,
                "_source": False,
                "sort": ["-@timestamp"],  # sort is for getting data ordered
            }
            doc_item = self.seasearch_api.normal_search(self.index_name, data)

            total = doc_item['hits']['total']['value']

            hits = doc_item['hits']['hits']
            for hit in hits:
                _id = hit['_id']
                delete_params.append({'delete': {'_id': _id, '_index': self.index_name}})

            start += per_size
            if len(hits) < per_size or start == total:
                break

        self.seasearch_api.bulk(delete_params)

    def delete_index_by_index_name(self):
        self.seasearch_api.delete_index_by_name(self.index_name)
