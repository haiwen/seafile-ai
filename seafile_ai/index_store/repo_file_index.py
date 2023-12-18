import os
import logging

from seafile_ai import config
from seafile_ai.utils import get_file_content
from seafile_ai.index_store.utils import get_document_add_params, parse_sdoc_to_add_params
from seafile_ai.utils import get_library_diff_files

logger = logging.getLogger(__name__)


VIRTUAL_PATH_CHILDREN_ID = 'file_path'
SEASEARCH_BULK_OPETATE_LIMIT = 2000
SEASEARCH_QUERY_PATH_DOC_STEP = 20
SUPPORT_FILE_TYPES = ['.sdoc']


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
            "children_id": {
                "type": "keyword"
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

    def search_files(self, index_name, k, model, query):
        vector = model.encode([query])[0].tolist()
        data = {
            "query_field": "vec",
            "k": k,
            "return_fields": ["path", "children_id"],
            "vector": vector
        }

        result = self.seasearch_api.vector_search(index_name, data)
        total = result.get('hits', {}).get('total', {}).get('value', 0)
        hits = result['hits']['hits']
        searched_result = {}
        for hit in hits:
            score = hit['_score']
            children_id = hit['fields']['children_id'][0]
            path = hit['fields']['path'][0]

            if score < config.THRESHOLD:
                continue

            if searched_result.get(path):
                pre_score = searched_result[path]['max_score']
                searched_result[path]['score'] = score + pre_score
                if score > pre_score:
                    searched_result[path]['children_id'] = children_id
                continue
            filename = os.path.basename(path)
            searched_result[path] = {'repo_id': index_name, 'fullpath': path, 'name': filename, 'is_dir': False, 'score': score, 'max_score': score}

        return list(searched_result.values())

    def delete_index_by_index_name(self, index_name):
        self.seasearch_api.delete_index_by_name(index_name)

    def add_files(self, index_name, old_commit_id, new_commit_id, retrieval_model):
        self.update_files(index_name, old_commit_id, new_commit_id, retrieval_model)

    def update_files(self, index_name, old_commit_id, new_commit_id, retrieval_model):
        """
        old_commit_id is ZERO_OBJ_ID that means create repo file index
        """
        added_files, deleted_files, modified_files, _, _ = get_library_diff_files(index_name, old_commit_id, new_commit_id)

        bulk_update_params = []
        step = SEASEARCH_QUERY_PATH_DOC_STEP
        need_deleted_files = deleted_files + modified_files
        for pos in range(0, len(need_deleted_files), step):
            files = need_deleted_files[pos: pos + step]
            paths = [file[0] for file in files]
            delete_params = self.get_doc_delete_params_by_paths(paths, index_name)
            bulk_update_params.extend(delete_params)
            if len(bulk_update_params) >= SEASEARCH_BULK_OPETATE_LIMIT:
                self.seasearch_api.bulk(bulk_update_params)
                bulk_update_params = []

        need_added_files = added_files + modified_files

        for file_info in need_added_files:
            path = file_info[0]
            obj_id = file_info[1]
            mtime = file_info[2]
            size = file_info[3]

            # add path to index
            path_string, ext = os.path.splitext(path)
            if ext.lower() not in SUPPORT_FILE_TYPES:
                continue
            add_params = get_document_add_params(retrieval_model, path_string, index_name, path, VIRTUAL_PATH_CHILDREN_ID)
            bulk_update_params.extend(add_params)

            file_content = b''
            if size:
                file_content = get_file_content(index_name, new_commit_id, obj_id, path)

            if file_content:
                add_params = parse_sdoc_to_add_params(file_content, retrieval_model, index_name, path)
                bulk_update_params.extend(add_params)

            # bulk add every 2000 params
            if len(bulk_update_params) >= SEASEARCH_BULK_OPETATE_LIMIT:
                self.seasearch_api.bulk(bulk_update_params)
                bulk_update_params = []
        if bulk_update_params:
            self.seasearch_api.bulk(bulk_update_params)

    def get_doc_delete_params_by_paths(self, path_list, index_name):
        per_size = 2000
        start = 0
        delete_params = []
        while True:
            data = {
                "query": {
                    "terms": {
                        "path": path_list
                    }
                },
                "from": start,
                "size": per_size,
                "_source": False,
                "sort": ["-@timestamp"],  # sort is for getting data ordered
            }
            doc_item = self.seasearch_api.normal_search(index_name, data)

            total = doc_item['hits']['total']['value']

            hits = doc_item['hits']['hits']
            for hit in hits:
                _id = hit['_id']
                delete_params.append({'delete': {'_id': _id, '_index': index_name}})

            start += per_size
            if len(hits) < per_size or start == total:
                return delete_params
