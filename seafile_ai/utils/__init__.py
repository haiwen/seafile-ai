import requests
import json
import logging

from urllib.parse import quote as urlquote
from pathlib import Path

from seafile_ai.config import FILE_SERVER
from seafile_ai.utils.sdoc2md import sdoc2md


logger = logging.getLogger(__name__)


def gen_file_get_url(token, filename):
    return '%s/files/%s/%s' % (FILE_SERVER, token, urlquote(filename))


def get_file_by_token(token, filename):
    url = gen_file_get_url(token, filename)
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        raise ConnectionError(response.status_code, response.text)

    return response.content.decode()


def get_image_by_token(token, filename):
    url = gen_file_get_url(token, filename)
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        raise ConnectionError(response.status_code, response.text)

    return response.content


def convert_file_to_md(file_name, download_token):
    doc_content = get_file_by_token(download_token, file_name)
    file_ext = Path(file_name).suffix
    if file_ext == '.sdoc':
        return sdoc2md(json.loads(doc_content))
    elif file_ext == '.md' or '.markdown':
        return doc_content
    else:
        return ''
