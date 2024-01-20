# coding: UTF-8
import os
import logging
import json
import re 
from seafile_ai import config
from zipfile import ZipFile
from io import BytesIO
from typing import List

from seafile_ai.utils.constants import ZERO_OBJ_ID, sdoc_suffixes, office_suffixes

from seafobj import fs_mgr

logger = logging.getLogger(__name__)

SDOC_SIZE_LIMITED = 1024 * 1024
OFFICE_FILE_SIZE_LIMIT = 10 * 1024 * 1024

class ZipString(ZipFile):
    def __init__(self, content):
        ZipFile.__init__(self, BytesIO(content))

def extract_sdoc_text(content):
    content = content.decode()
    if content:
        content = json.loads(content)
    return content

def extract_docx_text(content):
    doc = ZipString(content)
    content = doc.read('word/document.xml')
    
    return content.decode()

def extract_pptx_text(content) -> List:
    doc = ZipString(content)
    unpacked = doc.infolist()
    slides = []
    for item in unpacked:
        if item.orig_filename.startswith('ppt/slides') or item.orig_filename.startswith('ppt/notesSlides'):
            if item.orig_filename.endswith('xml'):
                slides.append(doc.read(item.orig_filename).decode())

    return slides

EXTRACT_TEXT_FUNCS = {
    'sdoc': extract_sdoc_text,
    'docx': extract_docx_text,
    'pptx': extract_pptx_text,
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
            content = self.func(content)
            logger.info('successfully extracted %s', path)
        except Exception as e:
            logger.warning('failed to extract %s: %s', path, e)
            return None

        return content


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
        if get_file_suffix(filename) in sdoc_suffixes:
            limit = SDOC_SIZE_LIMITED
        elif get_file_suffix(filename) in office_suffixes:
            limit = OFFICE_FILE_SIZE_LIMIT
        else:
            limit = -1
        return limit
