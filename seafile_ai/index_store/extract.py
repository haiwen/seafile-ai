# coding: UTF-8
import os
import logging
import numpy as np
import re
import markdown
from bs4 import BeautifulSoup

from seafile_ai.utils.constants import ZERO_OBJ_ID, md_suffixes, sdoc_suffixes

from seafobj import fs_mgr

logger = logging.getLogger(__name__)

MD_SIZE_LIMITED = 1024 * 1024
SDOC_SIZE_LIMITED = 1024 * 1024

REPO_FILE_INDEX_CONTENT_LIMIT = 200


def retrieval_encode(retrieval_model, string_list, per_limit=1000):
    step = per_limit
    embeddings = np.empty((0, retrieval_model.dimension))
    for pos in range(0, len(string_list), step):
        texts = string_list[pos: pos + step]
        embeddings = np.vstack((embeddings, retrieval_model.encode(texts)))
    return embeddings


def parse_sdoc_to_add_params(content, retrieval_model, index_name, path):
    import json
    content = json.loads(content)
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
    md_obj = markdown.Markdown(extensions=['extra'])
    html_content = md_obj.convert(content)

    document_add_params = []
    patern = "<.*?>"
    block_content = ''
    is_block_end = True
    for block in html_content.split('\n'):
        label = re.match(patern, block).group()
        soup = BeautifulSoup(block, features="html.parser")
        text = soup.get_text().strip()

        if not is_block_end and block_content:
            if text:
                block_content += ('。' + text)
        else:
            block_content = text

        if label in ['<ul>', '<ol>', '<table>']:
            is_block_end = False

        if label in ['</ul>', '</ol>', '</table>']:
            is_block_end = True

        if is_block_end and block_content:
            header_params = get_document_add_params(retrieval_model, block_content.strip(), index_name, path, '')
            document_add_params.extend(header_params)
            block_content = ''

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


EXTRACT_TEXT_FUNCS = {
    'sdoc': parse_sdoc_to_add_params,
    'md': parse_md_to_add_params,
}


def get_file_suffix(path):
    try:
        name = os.path.basename(path)
        suffix = os.path.splitext(name)[1][1:]
        if suffix:
            return suffix.lower()
        return None
    except:
        return None


class Extractor(object):
    def __init__(self, func, file_size_limit=-1):
        self.func = func
        self.file_size_limit = file_size_limit

    def extract(self, repo_id, version, obj_id, path, retrieval_model):
        if obj_id == ZERO_OBJ_ID:
            return None

        f = fs_mgr.load_seafile(repo_id, version, obj_id)
        if self.file_size_limit < f.size:
            logger.warning("file %s size exceeds limit", path)
            return None
        content = f.get_content(limit=self.file_size_limit)
        if not content:
            # An empty file
            return None

        content = content.decode()
        try:
            logger.info('extracting %s %s...', repo_id, path)
            params = self.func(content, retrieval_model, repo_id, path)
            logger.info('successfully extracted %s', path)
        except Exception as e:
            logger.warning('failed to extract %s: %s', path, e)
            return None

        return params


class ExtractorFactory(object):
    @classmethod
    def get_extractor(cls, filename):

        suffix = get_file_suffix(filename)
        func = EXTRACT_TEXT_FUNCS.get(suffix, None)
        if not func:
            return None
        return Extractor(func, cls.get_file_size_limit(filename))

    @classmethod
    def get_file_size_limit(cls, filename):
        if get_file_suffix(filename) in md_suffixes:
            limit = MD_SIZE_LIMITED
        elif get_file_suffix(filename) in sdoc_suffixes:
            limit = SDOC_SIZE_LIMITED
        else:
            limit = -1
        return limit
