# -*- coding: utf-8 -*-
import json
import logging
import os
import numpy as np
from copy import deepcopy

from seafile_ai import config
from seafile_ai.utils import get_file_by_token

logger = logging.getLogger(__name__)


VIRTUAL_PATH_CHILDREN_ID = 'file_path'
ZINC_BULK_OPETATE_LIMIT = 2000
ZINC_QUERY_PATH_DOC_STEP = 20


def retrieval_encode(retrieval_model, string_list, per_limit=1000):
    step = per_limit
    embeddings = np.empty((0, retrieval_model.dimension))
    for pos in range(0, len(string_list), step):
        texts = string_list[pos: pos + step]
        embeddings = np.vstack((embeddings, retrieval_model.encode(texts)))
    return embeddings


def parse_sdoc_to_add_params(file_content, retrieval_model, index_name, path):
    document_add_params = []
    file = json.loads(file_content.decode())
    for children in file.get('children', []):
        if children.get('type') == 'code_block':
            continue

        children_id = children.get('id')
        combined_text_list = parse_children_text(children, [])

        if not combined_text_list:
            continue

        sentence = '。'.join(combined_text_list)
        add_params = get_document_add_params(retrieval_model, sentence, index_name, path, children_id)
        document_add_params.extend(add_params)

    return document_add_params


def parse_children_text(children, text_list=[]):
    text = children.get('text')
    if text:
        text_list.append(text)

    children_list = children.get('children')
    if children_list:
        for children in children_list:
            parse_children_text(children, text_list)

    return text_list


def save_library_sdoc_embedding_to_zinc(context, retrieval_model, zinc_api, is_mapping_exist=False):
    associate_id = context.get('associate_id')
    sdoc_info_list = context.get('sdoc_info_list')

    dimension = retrieval_model.dimension
    index_name = associate_id

    if not is_mapping_exist:
        mapping = {
            "properties": {
                "vec": {
                    "type": "vector",
                    "dims": dimension,
                    "vec_index_type": "flat",
                    "m": 1
                },
                "path": {
                    "type": "keyword"
                },
                "children_id": {
                    "type": "keyword"
                }
            }
        }
        zinc_api.create_mapping(index_name, mapping)

    library_info = {}
    bulk_error_library_info = {}
    bulk_add_params = []
    for sdoc_info in sdoc_info_list:
        path = sdoc_info.get('path')
        download_token = sdoc_info.get('download_token')
        mtime = sdoc_info.get('mtime')
        size = sdoc_info.get('size')
        library_info[path] = mtime

        # add path to index
        path_string = path.strip('/').rstrip('.sdoc')
        add_params = get_document_add_params(retrieval_model, path_string, index_name, path, VIRTUAL_PATH_CHILDREN_ID)
        bulk_add_params.extend(add_params)

        file_content = b''
        if size:
            file_content = get_file_by_token(path, download_token)

        if file_content:
            add_params = parse_sdoc_to_add_params(file_content, retrieval_model, index_name, path)
            bulk_add_params.extend(add_params)

        # bulk add every 2000 params
        if len(bulk_add_params) >= ZINC_BULK_OPETATE_LIMIT:
            zinc_bulk_operate(zinc_api, bulk_error_library_info, bulk_add_params, associate_id)
            bulk_error_library_info = deepcopy(library_info)
            bulk_add_params = []

    if bulk_add_params:
        zinc_bulk_operate(zinc_api, bulk_error_library_info, bulk_add_params, associate_id)

    # save library info to json file
    with open(os.path.join(config.LIBRARY_FILE_INFO_STORAGE_PATH, associate_id + '.json'), 'w') as f:
        f.write(json.dumps(library_info))

    logger.info('library: %s, save library sdoc info to ZincSearch success', associate_id)


def search_children_in_library(query, associate_id, sdoc_files_info, retrieval_model, zinc_api):
    query_embedding = retrieval_model.encode([query])

    data = {
        "query_field": "vec",
        "k": config.RETRIEVAL_NUM,
        "return_fields": ["path", "children_id"],
        "vector": query_embedding[0].tolist()
    }

    result = zinc_api.vector_search(data, associate_id)
    hits = result['hits']['hits']
    searched_result = {}
    for hit in hits:
        score = hit['_score']
        children_id = hit['fields']['children_id'][0]
        path = hit['fields']['path'][0]

        if score < config.THRESHOLD or not sdoc_files_info.get(path):
            continue

        if searched_result.get(path):
            pre_score = searched_result[path]['max_score']
            searched_result[path]['score'] = score + pre_score
            if score > pre_score:
                searched_result[path]['children_id'] = children_id
            continue
        searched_result[path] = {'path': path, 'children_id': children_id, 'score': score, 'max_score': score}

    return list(searched_result.values())


def update_library_sdoc_embedding_to_zinc(context, retrieval_model, zinc_api):
    associate_id = context.get('associate_id')
    last_modify = context.get('last_modify')
    sdoc_info_list = context.get('sdoc_info_list')
    library_sdoc_info_path = os.path.join(config.LIBRARY_FILE_INFO_STORAGE_PATH, associate_id + '.json')

    index_name = associate_id
    if not os.path.exists(library_sdoc_info_path):
        res =  zinc_api.check_index_mapping(index_name)
        context = {
            'associate_id': associate_id,
            'last_modify': last_modify,
            'sdoc_info_list': sdoc_info_list
        }
        save_library_sdoc_embedding_to_zinc(context, retrieval_model, zinc_api, res.get('is_exist'))
        logger.info('library: %s, update embedding to ZincSearch success', associate_id)
        return

    with open(library_sdoc_info_path, 'r') as fp:
        old_library_info = json.load(fp)

    old_path_set = {path for path in old_library_info}
    new_path_set = {sdoc.get('path') for sdoc in sdoc_info_list}
    new_file_info = {sdoc.get('path'): sdoc for sdoc in sdoc_info_list}
    need_del_file_set = old_path_set - new_path_set

    need_del_doc_file_list = list(need_del_file_set)
    bulk_update_params = []
    bulk_error_library_info = deepcopy(old_library_info)
    for path in new_path_set:
        sdoc_info = new_file_info.get(path)
        download_token = sdoc_info.get('download_token')
        new_mtime = sdoc_info.get('mtime')
        size = sdoc_info.get('size')

        # path may be not in library_info
        old_mtime = old_library_info.get(path)
        old_library_info[path] = new_mtime
        if new_mtime == old_mtime:
            continue

        if old_mtime:
            need_del_doc_file_list.append(path)

        file_content = b''
        if size:
            file_content = get_file_by_token(path, download_token)

        # add path to index
        path_string = path.strip('/').rstrip('.sdoc')
        document_add_params = get_document_add_params(retrieval_model, path_string, index_name, path, VIRTUAL_PATH_CHILDREN_ID)
        bulk_update_params.extend(document_add_params)

        if file_content:
            add_params = parse_sdoc_to_add_params(file_content, retrieval_model, index_name, path)
            bulk_update_params.extend(add_params)
            if len(bulk_update_params) >= ZINC_BULK_OPETATE_LIMIT:
                zinc_bulk_operate(zinc_api, bulk_error_library_info, bulk_update_params, associate_id)
                bulk_error_library_info = deepcopy(old_library_info)
                bulk_update_params = []

    step = ZINC_QUERY_PATH_DOC_STEP
    for pos in range(0, len(need_del_doc_file_list), step):
        paths = need_del_doc_file_list[pos: pos + step]
        delete_params = get_doc_delete_params_by_paths(zinc_api, paths, index_name)
        bulk_update_params.extend(delete_params)
        for path in paths:
            # pop that sdoc file has been deleted
            if path in need_del_file_set:
                old_library_info.pop(path)
        if len(bulk_update_params) >= ZINC_BULK_OPETATE_LIMIT:
            zinc_bulk_operate(zinc_api, bulk_error_library_info, bulk_update_params, associate_id)
            bulk_error_library_info = deepcopy(old_library_info)
            bulk_update_params = []

    if bulk_update_params:
        zinc_bulk_operate(zinc_api, bulk_error_library_info, bulk_update_params, associate_id)
    with open(os.path.join(config.LIBRARY_FILE_INFO_STORAGE_PATH, associate_id + '.json'), 'w') as f:
        f.write(json.dumps(old_library_info))

    logger.info('library: %s, update sdoc embedding to ZincSearch success', associate_id)


def get_doc_delete_params_by_paths(zinc_api, path_list, index_name):
    data = {
        "query": {
            "terms": {
                "path": path_list
            }
        },
        "_source": False
    }
    doc_item = zinc_api.normal_search(index_name, data)

    delete_params = []
    for hit in doc_item['hits']['hits']:
        _id = hit['_id']
        delete_params.append({'delete': {'_id': _id, '_index': index_name}})

    return delete_params


def get_document_add_params(retrieval_model, sentence, index_name, path, children_id):
    add_params = []
    embeddings = retrieval_encode(retrieval_model, [sentence])
    index_info = {"index": {"_index": index_name}}
    vector_info = {"path": path, "children_id": children_id, "vec": embeddings[0].tolist()}
    add_params.append(index_info)
    add_params.append(vector_info)
    return add_params


def zinc_bulk_operate(zinc_api, bulk_error_library_info, bulk_params, associate_id):
    try:
        zinc_api.bulk(bulk_params)
    except Exception as e:
        if bulk_error_library_info:
            with open(os.path.join(config.LIBRARY_FILE_INFO_STORAGE_PATH, associate_id + '.json'), 'w') as f:
                f.write(json.dumps(bulk_error_library_info))
        raise Exception(e)
