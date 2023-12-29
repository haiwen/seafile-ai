# -*- coding: utf-8 -*-
import json
import logging
import numpy as np
import re
import uuid

logger = logging.getLogger(__name__)

REPO_FILE_INDEX_CONTENT_LIMIT = 200

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

def parse_docx_to_add_params(content, retrieval_model, index_name, path):
    document_add_params = []
    # Initializes the end position of the previous match
    prev_end = 0
    xml_pattern = re.compile('<(.|\n)*?>')
    end_symbol_pattern = re.compile('。|\.|\?|？|;|；')
    seg_text = ''

    for match in re.finditer(xml_pattern, content):
        # Match text content
        text_between_tags = content[prev_end:match.start()]
        striped_text = text_between_tags.strip()
        # No cutoff punctuation in a line of text
        no_punctuation = True

        if striped_text:
            for seg_symbol in re.finditer(end_symbol_pattern, striped_text):
                # -1 aimed at remove end_symbol
                seg_text = striped_text[0:seg_symbol.end()-1]
                if seg_text:
                    add_params = get_document_add_params(retrieval_model, seg_text,
                                                        index_name, path, str(uuid.uuid4()))
                    document_add_params.extend(add_params)
                
                seg_text = striped_text[seg_symbol.end():]
                no_punctuation = False
            if no_punctuation:
                add_params = get_document_add_params(retrieval_model, striped_text,
                                                    index_name, path, str(uuid.uuid4()))
                document_add_params.extend(add_params)
            # When it doesn't end with a cut-off symbol，seg_text is not empty
            if seg_text:
                add_params = get_document_add_params(retrieval_model, seg_text,
                                                    index_name, path, str(uuid.uuid4()))
                document_add_params.extend(add_params)
        prev_end = match.end()
    
    return document_add_params

def parse_pptx_to_add_params(slides: list, retrieval_model, index_name, path):
    document_add_params = []
    # Initializes the end position of the previous match
    prev_end = 0
    xml_pattern = re.compile('<(.|\n)*?>')
    end_symbol_pattern = re.compile('。|\.|\?|？|;|；')
    seg_text = ''
    
    for slide in slides:
        # Match each text content in slide 
        for match in re.finditer(xml_pattern, slide):
            # Match text content
            text_between_tags = slide[prev_end:match.start()]
            striped_text = text_between_tags.strip()
            # No cutoff punctuation in a line of text
            no_punctuation = True

            if striped_text:
                for seg_symbol in re.finditer(end_symbol_pattern, striped_text):
                    # -1 aimed at remove end_symbol
                    seg_text = striped_text[0:seg_symbol.end()-1]
                    if seg_text:
                        add_params = get_document_add_params(retrieval_model, seg_text,
                                                            index_name, path, str(uuid.uuid4()))
                        document_add_params.extend(add_params)
                    
                    seg_text = striped_text[seg_symbol.end():]
                    no_punctuation = False
                if no_punctuation:
                    add_params = get_document_add_params(retrieval_model, striped_text,
                                                        index_name, path, str(uuid.uuid4()))
                    document_add_params.extend(add_params)
                # When it doesn't end with a cut-off symbol，seg_text is not empty
                if seg_text.strip():
                    add_params = get_document_add_params(retrieval_model, seg_text,
                                                        index_name, path, str(uuid.uuid4()))
                    document_add_params.extend(add_params)
            prev_end = match.end()
    
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
    vector_info = {"path": path, "children_id": children_id, "vec": embeddings[0].tolist(), "content": sentence[:REPO_FILE_INDEX_CONTENT_LIMIT]}
    add_params.append(index_info)
    add_params.append(vector_info)
    return add_params


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
