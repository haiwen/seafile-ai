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

THRESHOLD = 0.01

## seasearch
SEASEARCH_SERVER = 'http://127.0.0.1:4080'
SEASEARCH_TOKEN = ''
VECTOR_M = 1
SHARD_NUM = 1

## sea-embedding
SEA_EMBEDDING_SERVER = ''
SEA_EMBEDDING_KEY = ''
SEA_EMBEDDING_DIMENSION = 768

EMBEDDING_API_TYPE = 'sea-embedding'
if EMBEDDING_API_TYPE == 'sea-embedding':
    DIMENSION = SEA_EMBEDDING_DIMENSION

# seafile-ai config database
DB_HOST = ''
DB_USER = ''
DB_PASSWORD = ''
DB_PORT = 3306
DB_NAME = 'seafile_ai'
DB_UNIX_SOCKET = ''

# seafile config database
MYSQL_HOST = ''
MYSQL_USER = ''
MYSQL_PASSWORD = ''
MYSQL_PORT = 3306
MYSQL_DB = 'seafile'
MYSQL_UNIX_SOCKET = ''

# repo file index support file types
SUPPORT_INDEX_FILE_TYPES = [
    '.sdoc',
    '.md',
    '.markdown',
    '.doc',
    '.docx',
    '.ppt',
    '.pptx',
    '.pdf',
]


CONF_DIR = '/opt/seafile/conf/'

#openai
OPENAI_PROXY_URL = ''

try:
    if os.path.exists('seafile_ai_settings.py'):
        from seafile_ai_settings import *
except:
    pass

try:
    if os.path.exists(CONF_DIR):
        sys.path.insert(0, CONF_DIR)
    from seafile_ai_settings import *
except ImportError as e:
    pass
