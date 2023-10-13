import logging
import time
import jwt
import os
import requests

from urllib.parse import quote as urlquote

from seafile_ai.config import SECRET_KEY, FILE_SERVER

logger = logging.getLogger(__name__)


def gen_headers(repo_id, username):
    access_token = get_server_token(repo_id, username)
    return {'Authorization': 'Token ' + access_token}


def get_server_token(repo_id, username):
    token = jwt.encode(
        payload={
            'exp': int(time.time()) + 600,
            'repo_id': repo_id,
            'username': username,
        },
        key=SECRET_KEY
    )
    if isinstance(token, bytes):
        token = token.decode()
    return token


def gen_file_get_url(token, filename):
    return '%s/files/%s/%s' % (FILE_SERVER, token, urlquote(filename))


def get_file_by_token(path, token):
    filename = os.path.basename(path)
    url = gen_file_get_url(token, filename)
    content = requests.get(url, timeout=10).content
    return content
