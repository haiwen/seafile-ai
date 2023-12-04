# -*- coding: utf-8 -*-
import logging
import numpy as np

logger = logging.getLogger(__name__)


def retrieval_encode(retrieval_model, string_list, per_limit=1000):
    step = per_limit
    embeddings = np.empty((0, retrieval_model.dimension))
    for pos in range(0, len(string_list), step):
        texts = string_list[pos: pos + step]
        embeddings = np.vstack((embeddings, retrieval_model.encode(texts)))
    return embeddings


def parse_sdoc_to_add_params(content, retrieval_model, index_name, path):
    document_add_params = []
    for children in content.get('children', []):
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


def get_document_add_params(retrieval_model, sentence, index_name, path, children_id):
    add_params = []
    embeddings = retrieval_encode(retrieval_model, [sentence])
    index_info = {"index": {"_index": index_name}}
    vector_info = {"path": path, "children_id": children_id, "vec": embeddings[0].tolist()}
    add_params.append(index_info)
    add_params.append(vector_info)
    return add_params
