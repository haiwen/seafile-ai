import os
import logging

from seafile_ai import config
from seafile_ai.utils import get_library_diff_files
from seafile_ai.index_store.utils import parse_file_to_add_params

logger = logging.getLogger(__name__)


SEASEARCH_BULK_OPETATE_LIMIT = 2000
SEASEARCH_QUERY_PATH_DOC_STEP = 20


class RepoFileIndex(object):
    """
        index name is repo id
    """
    mapping = {
        "properties": {
            "vec": {
                "type": "vector",
                "dims": config.DIMENSION,
                "vec_index_type": "flat",
                "m": config.VECTOR_M
            },
            "path": {
                "type": "keyword"
            },
            'content': {
                'type': 'text'
            }
        }
    }

    shard_num = config.SHARD_NUM

    def __init__(self, seasearch_api):
        self.seasearch_api = seasearch_api

    def create_index(self, index_name):
        data = {
            'name': index_name,
            'shard_num': self.shard_num,
            'mappings': self.mapping,
        }
        self.seasearch_api.create_index(data)

    def check_index(self, index_name):
        return self.seasearch_api.check_index_mapping(index_name).get('is_exist')

    def search_files(self, repo, k, model, query):
        repo_id = repo[0]
        origin_repo_id = repo[1]
        origin_path = repo[2]

        if origin_repo_id:
            repo_id = origin_repo_id

        vector = model.encode([query])[0].tolist()
        data = {
            "query_field": "vec",
            "k": k,
            "return_fields": ["path", "content"],
            "_source": False,
            "vector": vector
        }

        result = self.seasearch_api.vector_search(repo_id, data)
        total = result.get('hits', {}).get('total', {}).get('value', 0)
        if result.get('error'):
            logger.info('search in repo_file_index error: %s .', result.get('error'))
            return []

        hits = result['hits']['hits']
        if not hits:
            return []
        searched_result = {}
        for hit in hits:
            score = hit['_score']
            _id = hit['_id']
            path = hit['fields']['path'][0]
            content = hit['fields']['content'][0]

            if origin_path and not path.startswith(origin_path):
                continue

            if score < config.THRESHOLD:
                continue

            if searched_result.get(path):
                pre_score = searched_result[path]['max_score']
                searched_result[path]['score'] = score + pre_score
                continue
            filename = os.path.basename(path)
            searched_result[path] = {'repo_id': repo_id,
                                     'fullpath': path,
                                     'name': filename,
                                     'is_dir': False,
                                     'score': score,
                                     'max_score': score,
                                     'content': content,
                                     '_id': _id
                                     }

        return list(searched_result.values())

    def delete_index_by_index_name(self, index_name):
        self.seasearch_api.delete_index_by_name(index_name)

    def add(self, index_name, old_commit_id, new_commit_id, retrieval_model):
        self.update(index_name, old_commit_id, new_commit_id, retrieval_model)

    def update(self, index_name, old_commit_id, new_commit_id, retrieval_model):
        """
        old_commit_id is ZERO_OBJ_ID that means create repo file index
        """
        added_files, deleted_files, modified_files, _, deleted_dirs = get_library_diff_files(index_name, old_commit_id, new_commit_id)

        need_deleted_files = deleted_files + modified_files
        self.delete_files(index_name, need_deleted_files)

        self.delete_files_by_deleted_dirs(index_name, deleted_dirs)

        need_added_files = added_files + modified_files
        self.add_files(index_name, need_added_files, retrieval_model, new_commit_id)

    def query_data_by_paths(self, index_name, path_list, start, size):
        dsl = {
            "query": {
                "terms": {
                    "path": path_list
                }
            },
            "from": start,
            "size": size,
            "_source": False,
            "sort": ["-@timestamp"],  # sort is for getting data ordered
        }
        hits, total = self.normal_search(index_name, dsl)
        return hits, total

    def query_data_by_dir(self, index_name, directory, start, size):
        dsl = {
            "query": {
                "bool": {
                    "must": [
                        {"prefix": {"path": directory}}
                    ]
                }
            },
            "from": start,
            "size": size,
            "_source": False,
            "sort": ["-@timestamp"],  # sort is for getting data ordered
        }

        hits, total = self.normal_search(index_name, dsl)
        return hits, total

    def normal_search(self, index_name, dsl):
        doc_item = self.seasearch_api.normal_search(index_name, dsl)
        total = doc_item['hits']['total']['value']

        return doc_item['hits']['hits'], total

    def delete_files(self, index_name, files):
        step = SEASEARCH_QUERY_PATH_DOC_STEP
        for pos in range(0, len(files), step):
            paths = [file[0] for file in files[pos: pos + step]]
            per_size = SEASEARCH_BULK_OPETATE_LIMIT
            start = 0
            delete_params = []
            while True:
                hits, total = self.query_data_by_paths(index_name, paths, start, per_size)
                for hit in hits:
                    _id = hit['_id']
                    delete_params.append({'delete': {'_id': _id, '_index': index_name}})

                if delete_params:
                    self.seasearch_api.bulk(delete_params)
                if len(hits) < per_size:
                    break

    def delete_files_by_deleted_dirs(self, index_name, dirs):
        for directory in dirs:
            per_size = SEASEARCH_BULK_OPETATE_LIMIT
            start = 0
            delete_params = []
            while True:
                hits, total = self.query_data_by_dir(index_name, directory, start, per_size)
                for hit in hits:
                    _id = hit['_id']
                    delete_params.append({'delete': {'_id': _id, '_index': index_name}})

                if delete_params:
                    self.seasearch_api.bulk(delete_params)
                if len(hits) < per_size:
                    break

    def add_files(self, index_name, files, retrieval_model, commit_id):
        bulk_add_params = []
        for file_info in files:
            add_params = parse_file_to_add_params(index_name, file_info, retrieval_model, commit_id)
            bulk_add_params.extend(add_params)

            # bulk add every 2000 params
            if len(bulk_add_params) >= SEASEARCH_BULK_OPETATE_LIMIT:
                self.seasearch_api.bulk(bulk_add_params)
                bulk_add_params = []
        if bulk_add_params:
            self.seasearch_api.bulk(bulk_add_params)
