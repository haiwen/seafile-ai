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
LLM_URL = ''
LLM_TYPE = 'openai-proxy'
LLM_KEY = ''

# Face embedding
FACE_EMBEDDING_SERVICE_URL = ''
FACE_EMBEDDING_SERVICE_KEY = ''

SEAFILE_SERVER_URL = ''

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
SECRET_KEY = os.getenv('JWT_PRIVATE_KEY') or SECRET_KEY

LLM_URL = os.getenv('SEAFILE_AI_LLM_URL') or LLM_URL
LLM_KEY = os.getenv('SEAFILE_AI_LLM_KEY') or LLM_KEY

FACE_EMBEDDING_SERVICE_URL = os.getenv('FACE_EMBEDDING_SERVICE_URL') or FACE_EMBEDDING_SERVICE_URL
FACE_EMBEDDING_SERVICE_KEY = os.getenv('FACE_EMBEDDING_SERVICE_KEY') or FACE_EMBEDDING_SERVICE_KEY

LOG_LEVEL = os.getenv('SEAFILE_AI_LOG_LEVEL') or LOG_LEVEL
