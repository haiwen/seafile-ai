# coding: UTF-8
import os
import logging
import json
import tempfile
import fitz
from seafile_ai import config  

from seafile_ai.utils.constants import ZERO_OBJ_ID, sdoc_suffixes, pdf_suffixes

from seafobj import fs_mgr

logger = logging.getLogger(__name__)


def extract_sdoc_text(content):
    content = content.decode()
    if content:
        content = json.loads(content)
    return content

def extract_pdf_text(content):
    temp_pdf = tempfile.NamedTemporaryFile(suffix='.pdf')
    try:
        pdf_name = temp_pdf.name
        with open(pdf_name, 'wb') as output:
            output.write(content)

        doc = fitz.open(pdf_name)
        text = ""
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text += page.get_text()
        
        return text
    except Exception as e:
        logging.warning('error when extracting pdf: %s', e)
        return None
    finally:
        temp_pdf.close()

EXTRACT_TEXT_FUNCS = {
    'sdoc': extract_sdoc_text,
    'pdf': extract_pdf_text
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

def is_sdoc_file(path):
    suffix = get_file_suffix(path)
    
    if not suffix:
        return False

    if suffix in sdoc_suffixes:
        return True

    return False

def is_pdf_file(path):
    suffix = get_file_suffix(path)
    if not suffix:
        return False

    if suffix in pdf_suffixes:
        return True

    return False

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
        if not cls.should_extract(filename):
            return None

        suffix = get_file_suffix(filename)
        func = EXTRACT_TEXT_FUNCS.get(suffix, None)
        if not func:
            return None
        return Extractor(func, cls.get_file_size_limit(filename))
    
    @classmethod
    def should_extract(cls, filename):
        if config.INDEX_PDF:
            return is_sdoc_file(filename) or is_pdf_file(filename)
        else:
            return is_sdoc_file(filename)

    @classmethod
    def get_file_size_limit(cls, filename):
        if is_sdoc_file(filename):
            limit = config.SDOC_SIZE_LIMITED
        elif is_pdf_file(filename):
            limit = config.PDF_FILE_SIZE_LIMIT
        else:
            limit = -1
        return limit
