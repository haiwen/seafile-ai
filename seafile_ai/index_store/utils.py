# -*- coding: utf-8 -*-
import json
import logging
import os
import pandas as pd
import numpy as np

from seafile_ai import config
from seafile_ai.models.constant import METRIC_TO_FAISS, Metric
from seafile_ai.index_store.faiss_operator import faiss_operator as faiss
from seafile_ai.utils.constant import LIBRARY_SDOC_INDEX
from seafile_ai.utils import get_file_by_token

logger = logging.getLogger(__name__)


def retrieval_encode(retrieval_model, string_list, per_limit=1000):
    step = per_limit
    embeddings = np.empty((0, retrieval_model.dimension))
    for pos in range(0, len(string_list), step):
        texts = string_list[pos: pos + step]
        embeddings = np.vstack((embeddings, retrieval_model.encode(texts)))
    return embeddings


def read_faiss_index(faiss_cache, index_path):
    index = faiss_cache.get(index_path)
    if index:
        return index
    index = faiss.read_index(index_path)
    faiss_cache.set(index_path, index)
    return index


def get_max_vector_id(library_info):
    max_vector_id = 0
    for sdoc_info in library_info.values():
        children_list = sdoc_info.get('children_list')
        sdoc_df = pd.DataFrame(children_list)
        max_id = sdoc_df['vector_id'].max()
        if max_id > max_vector_id:
            max_vector_id = max_id
    return max_vector_id


def delete_index(index, children_list, library_info, path):
    need_deleted_df = pd.DataFrame(children_list)
    index.remove_ids(need_deleted_df.vector_id)
    library_info.pop(path)


def add_index(index, children_id_list, retrieval_model, sentence_list, start_vector_id, mtime, library_info, path):
    """
     add sentences to index
     return added number
    """

    df = pd.DataFrame(children_id_list, columns=['children_id'])
    embeddings = retrieval_encode(retrieval_model, sentence_list)

    metric = retrieval_model.metric
    if metric == Metric.COS:
        faiss.normalize_L2(embeddings)

    embedding_n, embedding_d = embeddings.shape
    vector_ids = np.arange(start_vector_id, embedding_n + start_vector_id)
    index.add_with_ids(embeddings, vector_ids)
    df['vector_id'] = vector_ids

    indexed_children_list = df.to_dict(orient='records')
    indexed_file_info = {}
    indexed_file_info['children_list'] = indexed_children_list
    indexed_file_info['mtime'] = mtime
    library_info[path] = indexed_file_info

    return len(df)


def get_file_children_info(file_content):
    children_id_list = []
    sentence_list = []
    for children in file_content.get('children'):
        if children.get('type') == 'code_block':
            continue

        children_id = children.get('id')
        combined_text_list = parse_children_text(children, [])

        if not combined_text_list:
            continue

        children_id_list.append(children_id)
        sentence = '。'.join(combined_text_list)
        sentence_list.append(sentence)

    return children_id_list, sentence_list


def parse_children_text(children, text_list=[]):
    text = children.get('text')
    if text:
        text_list.append(text)

    children_list = children.get('children')
    if children_list:
        for children in children_list:
            parse_children_text(children, text_list)

    return text_list


def save_library_sdoc_embedding_to_faiss(context, retrieval_model):
    associate_id = context.get('associate_id')
    sdoc_info_list = context.get('sdoc_info_list')

    embedding_dir = os.path.join(config.INDEX_STORAGE_PATH, LIBRARY_SDOC_INDEX)
    library_sdoc_index_path = os.path.join(embedding_dir, associate_id + '.index')
    os.makedirs(embedding_dir, exist_ok=True)

    metric = retrieval_model.metric
    dimension = retrieval_model.dimension
    index = faiss.index_factory(dimension, config.FAISS_INDEX_TYPE, METRIC_TO_FAISS.get(metric))

    library_info = {}
    start_vector_id = 0

    for sdoc_info in sdoc_info_list:
        path = sdoc_info.get('path')
        download_token = sdoc_info.get('download_token')
        mtime = sdoc_info.get('mtime')

        file_content = get_file_by_token(path, download_token)
        if not file_content:
            continue

        file_content = json.loads(file_content.decode())
        children_id_list, sentence_list = get_file_children_info(file_content)
        if not sentence_list:
            continue

        added_num = add_index(index, children_id_list, retrieval_model,
                              sentence_list, start_vector_id, mtime, library_info, path)

        start_vector_id += added_num

    faiss.write_index(index, library_sdoc_index_path)
    # save library info to json file
    with open(os.path.join(embedding_dir, associate_id + '.json'), 'w') as f:
        f.write(json.dumps(library_info))

    logger.info('library: %s, save library sdoc embedding to faiss success', associate_id)


def search_children_in_library(query, associate_id, sdoc_files_info, retrieval_model, rerank_model, faiss_cache):
    embedding_dir = os.path.join(config.INDEX_STORAGE_PATH, LIBRARY_SDOC_INDEX)
    library_info_path = os.path.join(embedding_dir, associate_id + '.json')
    faiss_index_path = os.path.join(embedding_dir, associate_id + '.index')

    faiss_index = read_faiss_index(faiss_cache, faiss_index_path)
    query_embedding = retrieval_model.encode([query.strip()]).reshape(1, -1)
    if retrieval_model.metric == Metric.COS:
        faiss.normalize_L2(query_embedding)

    similarities, nearest_vecs = faiss_index.search(query_embedding, config.RETRIEVAL_NUM)
    retrieval_df = pd.DataFrame({'vector_id': nearest_vecs[0]})
    filtered_library_df = pd.DataFrame(columns=['path', 'children_id', 'sentence'])

    with open(library_info_path, 'r') as fp:
        library_json_info = json.load(fp)

    for old_path, file_info in library_json_info.items():
        children_list = file_info.get('children_list')
        sdoc_info = sdoc_files_info.get(old_path)
        file_df = pd.DataFrame(children_list)
        file_retrieval_df = retrieval_df.merge(file_df, on=['vector_id'], how='left').\
            query('vector_id!=-1 and children_id.notna()')

        # file empty or old file has not exist
        if file_retrieval_df.empty or not sdoc_info:
            continue

        file_retrieval_df['path'] = old_path
        download_token = sdoc_info.get('download_token')
        file_content = get_file_by_token(old_path, download_token)
        if not file_content:
            continue

        file_content = json.loads(file_content.decode())
        file_retrieved_children_id_set = \
            {children.get('children_id') for children in file_retrieval_df.to_dict(orient='records')}

        sentence_info_list = []
        for children in file_content.get('children'):
            children_id = children.get('id')
            if children_id not in file_retrieved_children_id_set or children.get('type') == 'code_block':
                continue

            combined_text_list = parse_children_text(children, [])
            if not combined_text_list:
                continue

            sentence = '。'.join(combined_text_list)
            sentence_info = {'path': old_path, 'children_id': children_id, 'sentence': sentence}
            sentence_info_list.append(sentence_info)

        file_sentence_df = pd.DataFrame(sentence_info_list)
        filtered_library_df = pd.concat([filtered_library_df, file_sentence_df], axis=0, ignore_index=True)

    sentences = filtered_library_df['sentence'].to_list()
    scores = rerank_model.rerank(query.strip(), sentences)
    filtered_library_df['similarity'] = scores
    all_filtered_df = filtered_library_df[filtered_library_df.similarity > config.THRESHOLD]

    searched_docs = []
    for group in all_filtered_df.groupby('path'):
        doc_item = group[1]
        grouped_doc = doc_item.groupby(by='path', as_index=False).max()
        increased_score = doc_item.similarity.sum()
        grouped_doc['similarity'] = increased_score
        searched_docs.append(grouped_doc.to_dict(orient='records')[0])

    return searched_docs


def update_library_sdoc_embedding_to_faiss(context, retrieval_model):
    is_updated = False

    associate_id = context.get('associate_id')
    last_modify = context.get('last_modify')
    sdoc_info_list = context.get('sdoc_info_list')

    embedding_dir = os.path.join(config.INDEX_STORAGE_PATH, LIBRARY_SDOC_INDEX)
    library_sdoc_info_path = os.path.join(embedding_dir, associate_id + '.json')
    library_sdoc_index_path = os.path.join(embedding_dir, associate_id + '.index')

    if not os.path.exists(library_sdoc_info_path) or not os.path.exists(library_sdoc_index_path):
        context = {
            'associate_id': associate_id,
            'last_modify': last_modify,
            'sdoc_info_list': sdoc_info_list
        }
        save_library_sdoc_embedding_to_faiss(context, retrieval_model)
        logger.info('library: %s, update embedding to faiss success', associate_id)
        return True

    index = faiss.read_index(library_sdoc_index_path)

    with open(library_sdoc_info_path, 'r') as fp:
        library_info = json.load(fp)

    old_path_set = set()
    for path in library_info:
        old_path_set.add(path)

    new_path_set = set([sdoc.get('path') for sdoc in sdoc_info_list])
    new_file_info = {sdoc.get('path'): sdoc for sdoc in sdoc_info_list}

    need_del_files = old_path_set - new_path_set
    if need_del_files:
        is_updated = True

    for path in need_del_files:
        children_list = library_info.get(path).get('children_list')
        delete_index(index, children_list, library_info, path)

    max_vector_id = get_max_vector_id(library_info)
    start_vector_id = max_vector_id + 1
    for path in new_path_set:
        sdoc_info = new_file_info.get(path)
        download_token = sdoc_info.get('download_token')
        new_mtime = sdoc_info.get('mtime')
        # path may be not in library_info
        old_mtime = library_info.get(path, {}).get('mtime')

        if new_mtime == old_mtime:
            continue

        file_content = get_file_by_token(path, download_token)
        if not file_content:
            # old sdoc has content, new sdoc has no content, delete this sdoc index
            children_list = library_info.get(path, {}).get('children_list')
            if children_list:
                delete_index(index, children_list, library_info, path)
                is_updated = True
            continue

        file_content = json.loads(file_content.decode())
        children_id_list, sentence_list = get_file_children_info(file_content)

        if not sentence_list:
            children_list = library_info.get(path, {}).get('children_list')
            if children_list:
                delete_index(index, children_list, library_info, path)
                is_updated = True
            continue

        added_count = add_index(index, children_id_list, retrieval_model,
                              sentence_list, start_vector_id, new_mtime, library_info, path)

        start_vector_id += added_count
        is_updated = True

    if not is_updated:
        return False

    faiss.write_index(index, library_sdoc_index_path)
    # save library info to json file
    with open(os.path.join(embedding_dir, associate_id + '.json'), 'w') as f:
        f.write(json.dumps(library_info))

    logger.info('library: %s, update library sdoc embedding to faiss success', associate_id)
    return True
