import os
import sys
import logging

logger = logging.getLogger(__name__)

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, basedir)

FILE_SERVER = ''

APP_NAME = 'seafile-ai'

SECRET_KEY = ''
SEAFILE_SERVER = ''

# log
LOG_FILE = None
LOG_LEVEL = 'info'
ENABLE_SYS_LOG = False

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
RETRIEVAL_MODEL_PATH = None

## rerank model settings
RERANK_SOURCE = 'alibaba'
RERANK_MODEL_ID = 'damo/nlp_rom_passage-ranking_chinese-base'
RERANK_MODEL_PATH = None

THRESHOLD = 0.01

## seasearch
SEASEARCH_SERVER = 'http://127.0.0.1:4080'
SEASEARCH_TOKEN = ''
VECTOR_M = 1
SHARD_NUM = 3

# seafile config database
MYSQL_HOST = ''
MYSQL_USER = ''
MYSQL_PASSWORD = ''
MYSQL_PORT = 3306
MYSQL_DB = 'seafile'
MYSQL_UNIX_SOCKET = ''


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


os.makedirs(MODEL_CACHE_DIR, exist_ok=True)
