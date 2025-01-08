import requests
import json
import logging

import mammoth

from urllib.parse import quote as urlquote
from pathlib import Path
from io import BytesIO

from pdfminer.high_level import extract_text

from seafile_ai.config import FILE_SERVER
from seafile_ai.utils.sdoc2md import sdoc2md
from seafile_ai.utils.parse_pptx import get_pptx_text

logger = logging.getLogger(__name__)


def parse_response(response):
    if response.status_code >= 400 or response.status_code < 200:
        raise ConnectionError(response.status_code, response.text)
    else:
        try:
            return response.json()
        except:
            pass


class OpenAIInvalidException(Exception):
    pass


class InvalidWritingTypeException(Exception):
    pass


def gen_file_get_url(token, filename):
    return '%s/files/%s/%s' % (FILE_SERVER, token, urlquote(filename))


def gen_file_upload_url(token, op, replace=False):
    url = '%s/%s/%s' % (FILE_SERVER, op, token)
    if replace is True:
        url += '?replace=1'
    return url


def get_file_by_token(token, filename):
    url = gen_file_get_url(token, filename)
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        raise ConnectionError(response.status_code, response.text)

    return response.content


def upload_file(upload_token, file, parent_dir, file_name):
    upload_link = gen_file_upload_url(upload_token, 'upload-api')
    
    data = {
        'parent_dir': parent_dir,
        'replace': '0',
    }
    files = {
        'file': (file_name, file, "application/pdf")
    }
    response = requests.post(upload_link, data=data, files=files)
    return response.status_code


def get_image_by_token(token, filename):
    url = gen_file_get_url(token, filename)
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        raise ConnectionError(response.status_code, response.text)

    return response.content


def parse_file(file_name, download_token):
    doc = get_file_by_token(download_token, file_name)
    file_ext = Path(file_name).suffix.lower()

    parser_mapping = {
        '.sdoc': lambda x: sdoc2md(json.loads(x.decode())),
        '.md': lambda x: x.decode(),
        '.markdown': lambda x: x.decode(),
        '.docx': docx2md,
        '.pdf': get_pdf_text,
        '.pptx': get_pptx_text
    }

    return parser_mapping.get(file_ext, lambda x: '')(doc)


def docx2md(file):
    ignore_images = lambda _: []
    result = mammoth.convert_to_markdown(BytesIO(file), convert_image=ignore_images)
    return result.value.replace('\\', '')


def get_pdf_text(file):
    text = extract_text(BytesIO(file))
    return text
