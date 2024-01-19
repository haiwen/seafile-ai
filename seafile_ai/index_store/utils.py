# -*- coding: utf-8 -*-
import logging
import numpy as np
import uuid
import re
import markdown
from bs4 import BeautifulSoup

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

def parse_md_to_add_params(content, retrieval_model, index_name, path):
    document_add_params = []
    modified_content = re.sub(r'\n{2,}', '\n\n', content)
    modified_content = re.sub(r'\u3000', '', modified_content)

    paragraphs = modified_content.split("\n\n")
    headers_to_split_on = ["#", "##", "###", "####", "#####", "######"]

    for paragraph in paragraphs:
        stripped_paragraph = paragraph.strip()

        if stripped_paragraph.startswith("```"):
                continue
 
        # Check each line against each of the header types (e.g., #, ##)
        for sep in headers_to_split_on:
            if stripped_paragraph.startswith(sep) and (
                # Make sure the tag is followed by a space
                len(stripped_paragraph) == len(sep) or stripped_paragraph[len(sep)] == ' '
                ):
                header_content = stripped_paragraph[len(sep):]
                if header_content.strip():
                    header_params = get_document_add_params(retrieval_model, header_content.strip(), index_name, path, str(uuid.uuid4()))
                    document_add_params.extend(header_params)
                
                break
        else:
            if stripped_paragraph:
                html = markdown.markdown(stripped_paragraph)
                soup = BeautifulSoup(html, features="html.parser")
                text = soup.get_text()

                sentences = re.split('([。；;])', text)
                sentences = [sentences[i] + sentences[i+1] for i in range(0, len(sentences) - 1, 2) if sentences[i]]

                for sentence in sentences:
                    if sentence: 
                        add_params = get_document_add_params(retrieval_model, sentence,
                                                        index_name, path, str(uuid.uuid4()))
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
