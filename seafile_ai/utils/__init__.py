import requests
import json

from urllib.parse import quote as urlquote

from seafile_ai.config import FILE_SERVER


def gen_file_get_url(token, filename):
    return '%s/files/%s/%s' % (FILE_SERVER, token, urlquote(filename))


def get_file_by_token(token, filename):
    url = gen_file_get_url(token, filename)
    content = requests.get(url, timeout=10).content.decode()

    if content:
        content = json.loads(content)
    return content


def get_image_by_token(token, filename):
    url = gen_file_get_url(token, filename)
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        raise ConnectionError(response.status_code, response.text)

    return response.content
