import os
import sys
import logging

from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, basedir)

FILE_SERVER = ''

APP_NAME = 'seafile-ai'

SECRET_KEY = ''
SEAFILE_SERVER = ''

# database
MYSQL_HOST = ''
MYSQL_USER = ''
MYSQL_PASSWORD = ''
MYSQL_PORT = 3306
MYSQL_DB = 'seafile_ai'
MYSQL_UNIX_SOCKET = ''

# log
LOG_FILE = None
LOG_LEVEL = 'info'
ENABLE_SYS_LOG = False

# index path
INDEX_STORAGE_PATH = ''

# faiss index type default IDMap2,Flat
FAISS_INDEX_TYPE = 'IDMap2,Flat'

# sections
## indexManager worker count
INDEX_MANAGER_WORKERS = 2
INDEX_TASK_EXPIRE_TIME = 30 * 60

# model settings
MODEL_CACHE_DIR = ''

## retrieval model settings
RETRIEVAL_SOURCE = 'alibaba'
RETRIEVAL_MODEL_ID = 'damo/nlp_corom_sentence-embedding_chinese-base'
RETRIEVAL_METRIC = 'L2'
DIMENSION = 768
RETRIEVAL_NUM = 10

## rerank model settings
RERANK_SOURCE = 'alibaba'
RERANK_MODEL_ID = 'damo/nlp_rom_passage-ranking_chinese-base'

THRESHOLD = 100

CONF_DIR = '/opt/seafile/conf/'

#openai
OPENAI_PROXY_URL = ''

try:
    if os.path.exists('local_settings.py'):
        from local_settings import *
except:
    pass

try:
    if os.path.exists(CONF_DIR):
        sys.path.insert(0, CONF_DIR)
    from seafile_ai_settings import *
except ImportError as e:
    pass

SQLALCHEMY_DATABASE_URI = "mysql+mysqldb://%s:%s@%s:%s/%s?charset=utf8" % \
            (MYSQL_USER, quote_plus(MYSQL_PASSWORD), MYSQL_HOST, MYSQL_PORT, MYSQL_DB)

if MYSQL_UNIX_SOCKET:
    SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI + '&unix_socket=' + MYSQL_UNIX_SOCKET

os.makedirs(MODEL_CACHE_DIR, exist_ok=True)
