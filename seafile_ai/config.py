import os
import sys
import logging

logger = logging.getLogger(__name__)

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, basedir)


SECRET_KEY = ''

# log
LOG_FILE = None
LOG_LEVEL = 'info'
ENABLE_SYS_LOG = False

APP_NAME = 'seafile-ai'

# LLM
LLM_URL = None
LLM_TYPE = 'openai'
LLM_KEY = None
LLM_MODEL = 'gpt-4o-mini'

# redis
REDIS_HOST = 'redis'
REDIS_PORT = 6379
REDIS_PASSWORD = ''


# Face embedding
FACE_EMBEDDING_SERVICE_URL = ''
FACE_EMBEDDING_SERVICE_KEY = ''

SEAFILE_SERVER_URL = ''

INNER_METADATA_SERVER_URL = 'http://127.0.0.1:8084'

JWT_PRIVATE_KEY = ''

METADATA_FILE_TYPES = {
    '_picture': ('gif', 'jpeg', 'jpg', 'heic', 'png', 'ico', 'bmp', 'tif', 'tiff', 'psd', 'webp', 'jfif', 'mpo', 'jpe', 'xbm',
                 'svg', 'ppm', 'pcx', 'xcf', 'xpm', 'mgn', 'ufo', 'ai'),
    '_document': ('oform', 'ppt', 'pptx', 'odt', 'fodt', 'odp', 'fodp', 'odg', 'pdf', 'xls', 'xlsx', 'ods',
                  'fods', 'xmind', 'ac', 'am', 'bat', 'diff', 'org', 'properties', 'vi', 'vim', 'xml', 'log',
                  'csv', 'rst', 'patch', 'txt', 'text', 'tex', 'markdown', 'md', 'sdoc', 'doc', 'docx', ),
    '_code': ('cc', 'c', 'cmake', 'cpp', 'cs', 'css', 'el', 'h', 'html', 'htm', 'java', 'js', 'less', 'make', 'php', 'pl',
              'py', 'rb', 'scala', 'script', 'sh', 'sql', 'groovy', 'go', 'yml', 'xhtml', 'json', ),
    '_video': ('mp4', 'ogv', 'webm', 'mov', 'avi', 'wmv', 'asf', 'asx', 'rm', 'rmvb', 'mpg', 'mpeg', 'mpe', '3gp',
               'm4v', 'mkv', 'flv', 'vob'),
    '_audio': ('mp3', 'oga', 'ogg', 'wav', 'flac', 'opus', 'aac', 'au', 'm4a', 'aif', 'aiff', 'wma', 'mp1', 'mp2'),
    '_compressed': ('rar', 'zip', '7z', 'tar', 'gz', 'bz2', 'tgz', 'xz', 'lzma'),
    '_diagram': ('draw', 'exdraw'),
}


CONF_DIR = '/opt/seafile/conf/'

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

SEAFILE_SERVER_URL = os.getenv('SEAFILE_SERVER_URL') or SEAFILE_SERVER_URL
JWT_PRIVATE_KEY = os.getenv('JWT_PRIVATE_KEY') or JWT_PRIVATE_KEY
SECRET_KEY = SECRET_KEY or JWT_PRIVATE_KEY

LLM_TYPE = os.getenv('SEAFILE_AI_LLM_TYPE') or LLM_TYPE
LLM_URL = os.getenv('SEAFILE_AI_LLM_URL') or LLM_URL
LLM_KEY = os.getenv('SEAFILE_AI_LLM_KEY') or LLM_KEY
LLM_MODEL = os.getenv('SEAFILE_AI_LLM_MODEL') or LLM_MODEL

FACE_EMBEDDING_SERVICE_URL = os.getenv('FACE_EMBEDDING_SERVICE_URL') or FACE_EMBEDDING_SERVICE_URL
FACE_EMBEDDING_SERVICE_KEY = os.getenv('FACE_EMBEDDING_SERVICE_KEY') or FACE_EMBEDDING_SERVICE_KEY

LOG_LEVEL = os.getenv('SEAFILE_AI_LOG_LEVEL') or LOG_LEVEL

REDIS_HOST = os.getenv('REDIS_HOST') or REDIS_HOST
REDIS_PORT = os.getenv('REDIS_PORT') or REDIS_PORT
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD') or REDIS_PASSWORD

# metadata config
METADATA_SERVER_URL = os.getenv('INNER_METADATA_SERVER_URL') or INNER_METADATA_SERVER_URL


