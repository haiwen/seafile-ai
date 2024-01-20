import logging
import time
import jwt
import os
import requests
import json
import hashlib

from urllib.parse import quote as urlquote

from seafile_ai.config import SECRET_KEY, FILE_SERVER
from seafile_ai.utils.commit_differ import CommitDiffer

from seafobj import fs_mgr, commit_mgr
from seafobj.exceptions import GetObjectError


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
    content = requests.get(url, timeout=10).content.decode()

    if content:
        content = json.loads(content)
    return content


def get_library_diff_files(repo_id, old_commit_id, new_commit_id):
    if old_commit_id == new_commit_id:
        return [], [], [], [], []

    old_root = None
    if old_commit_id:
        try:
            old_commit = commit_mgr.load_commit(repo_id, 0, old_commit_id)
            old_root = old_commit.root_id
        except GetObjectError as e:
            logger.debug(e)
            old_root = None

    try:
        new_commit = commit_mgr.load_commit(repo_id, 0, new_commit_id)
    except GetObjectError as e:
        # new commit should exists in the obj store
        logger.warning(e)
        return [], [], [], [], []

    new_root = new_commit.root_id
    version = new_commit.get_version()

    try:
        differ = CommitDiffer(repo_id, version, old_root, new_root)
        added_files, deleted_files, added_dirs, deleted_dirs, modified_files = differ.diff(new_commit.ctime)
    except Exception as e:
        logger.warning('differ error: %s' % e)
        return [], [], [], [], []

    return added_files, deleted_files, modified_files, added_dirs, deleted_dirs


def init_logging(args):
    level = args.loglevel

    if level == 'debug':
        level = logging.DEBUG
    elif level == 'info':
        level = logging.INFO
    elif level == 'warning':
        level = logging.WARNING
    else:
        level = logging.INFO

    try:
        # set boto3 log level
        import boto3
        boto3.set_stream_logger(level=logging.WARNING)
    except:
        pass

    kw = {
        'format': '%(asctime)s [%(levelname)s] %(name)s:%(lineno)s %(funcName)s: %(message)s',
        'datefmt': '%m/%d/%Y %H:%M:%S',
        'level': level,
        'stream': args.logfile
    }

    logging.basicConfig(**kw)
    logging.getLogger('oss_util').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def md5(text):
    return hashlib.md5(text.encode()).hexdigest()
