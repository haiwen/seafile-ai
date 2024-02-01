# coding: UTF-8
import os
import json
import logging
from io import BytesIO
from seafile_ai.utils.constants import ZERO_OBJ_ID
from seafile_ai.utils.text_splitter import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from seafobj import fs_mgr

logger = logging.getLogger(__name__)

OFFICE_FILE_SIZE_LIMIT = 1024 * 1024 * 10
TEXT_FILE_SIZE_LIMIT = 1024 * 1024

text_suffixes = [
    'sdoc',
    'md',
    'markdown'
]

office_suffixes = [
    'doc',
    'docx',
    'ppt',
    'pptx'
]


def parse_sdoc_to_spilt_sentences(content):
    content = content.decode()
    content = json.loads(content)
    sentences = []
    for children in content.get('children', []):
        if children.get('type') == 'code_block':
            continue

        combined_text_list = parse_children_text(children, [])

        if not combined_text_list:
            continue

        sentence = '。'.join(combined_text_list)
        sentences.append(sentence)
    return sentences


def parse_children_text(children, text_list=[]):
    text = children.get('text', '')
    if text and text.strip():
        text_list.append(text.strip())

    children_list = children.get('children')
    if children_list:
        for children in children_list:
            parse_children_text(children, text_list)

    return text_list


def parse_md_to_spilt_sentences(content):
    content = content.decode()
    chunk_size = 100
    headers_to_split_on = ["#", "##", "###", "####", "#####", "######"]
    text_splitter = MarkdownHeaderTextSplitter(headers_to_split_on)
    md_header_splits = text_splitter.split_text(content)

    recursive_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=0)

    sentences = []
    for data in md_header_splits:
        text = data.get('content', '')
        if len(text) > chunk_size:
            split_texts = recursive_splitter.split_text(text)
            sentences.extend(split_texts)
        else:
            sentences.append(text)

    return sentences


def parse_office_to_split_sentences(content):
    from unstructured.partition.auto import partition
    from unstructured.staging.base import convert_to_text

    doc_elements = partition(file=BytesIO(content))

    chunk_size = 100
    recursive_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=0)
    doc_text = convert_to_text(doc_elements)
    if len(doc_text) > chunk_size:
        sentences = recursive_splitter.split_text(doc_text)
    else:
        sentences = [doc_text]

    return sentences


EXTRACT_TEXT_FUNCS = {
    'sdoc': parse_sdoc_to_spilt_sentences,
    'md': parse_md_to_spilt_sentences,
    'doc': parse_office_to_split_sentences,
    'docx': parse_office_to_split_sentences,
    'ppt': parse_office_to_split_sentences,
    'pptx': parse_office_to_split_sentences
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

    def extract(self, repo_id, version, obj_id, path):
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

        try:
            logger.info('extracting %s %s...', repo_id, path)
            sentences = self.func(content)
            logger.info('successfully extracted %s', path)
        except Exception as e:
            logger.warning('failed to extract %s: %s', path, e)
            return None

        return sentences


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
        suffix = get_file_suffix(filename)

        if suffix in text_suffixes:
            return TEXT_FILE_SIZE_LIMIT
        elif suffix in office_suffixes:
            return OFFICE_FILE_SIZE_LIMIT
        return -1
