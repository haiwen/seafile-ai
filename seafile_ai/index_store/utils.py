# -*- coding: utf-8 -*-
import os
import logging
from seafile_ai.index_store.extract import ExtractorFactory, get_document_add_params

from seafobj import fs_mgr, commit_mgr

logger = logging.getLogger(__name__)


VIRTUAL_PATH_CHILDREN_ID = 'file_path'
SUPPORT_FILE_TYPES = ['.sdoc', '.md', '.markdown']


def parse_file_to_add_params(index_name, file_info, retrieval_model, commit_id):
    path = file_info[0]
    obj_id = file_info[1]
    mtime = file_info[2]
    size = file_info[3]
    repo_id = index_name
    bulk_add_params = []
    path_string, ext = os.path.splitext(path)
    if ext.lower() not in SUPPORT_FILE_TYPES:
        return []
    add_params = get_document_add_params(retrieval_model, path_string, index_name, path, VIRTUAL_PATH_CHILDREN_ID)
    bulk_add_params.extend(add_params)

    if size:
        new_commit = commit_mgr.load_commit(repo_id, 0, commit_id)
        version = new_commit.get_version()

        extractor = ExtractorFactory.get_extractor(os.path.basename(path))
        add_params = extractor.extract(repo_id, version, obj_id, path, retrieval_model) if extractor else []
        if add_params:
            bulk_add_params.extend(add_params)

    return bulk_add_params


def rank_fusion(doc_lists, weights=None, c=60):
    """
    Args:
        doc_lists: A list of rank lists, where each rank list contains unique items.
        weights: A list of weights corresponding to the docs. Defaults to equal
            weighting for all docs.
        c: A constant added to the rank, controlling the balance between the importance
            of high-ranked items and the consideration given to lower-ranked items.
            Default is 60.

    Returns:
        list: The final aggregated list of items sorted by their weighted RRF
                scores in descending order.
    """

    if weights is None:
        weights = [0.6, 0.4]
    if len(doc_lists) != len(weights):
        raise ValueError(
            "Number of rank lists must be equal to the number of weights."
        )

    # Create a union of all unique documents in the input doc_lists
    all_documents = set()
    for doc_list in doc_lists:
        for doc in doc_list:
            all_documents.add(doc.get('_id'))

    # Initialize the RRF score dictionary for each document
    rrf_score_dic = {doc: 0.0 for doc in all_documents}

    # Calculate RRF scores for each document
    for doc_list, weight in zip(doc_lists, weights):
        for rank, doc in enumerate(doc_list, start=1):
            rrf_score = weight * (1 / (rank + c))
            rrf_score_dic[doc.get('_id')] += rrf_score

    # Sort documents by their RRF scores in descending order
    sorted_documents = sorted(
        rrf_score_dic.keys(), key=lambda x: rrf_score_dic[x], reverse=True
    )

    # Map the sorted _id back to the original document
    id_to_doc_map = {
        doc.get('_id'): doc for doc_list in doc_lists for doc in doc_list
    }
    sorted_docs = [
        id_to_doc_map[_id] for _id in sorted_documents
    ]

    return sorted_docs


def filter_hybrid_searched_files(files):
    """
    filter duplicate files
    """

    path_set = set()
    filtered_files = []
    for file in files:
        fullpath = file.get('fullpath')
        if fullpath in path_set:
            continue
        path_set.add(fullpath)
        file.pop('_id', None)
        file.pop('score', None)
        file.pop('max_score', None)
        filtered_files.append(file)
    return filtered_files
