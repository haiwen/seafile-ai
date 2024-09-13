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

# text LLM
TEXT_LLM_URL = ''
TEXT_LLM_TYPE = 'open-ai-proxy'
TEXT_LLM_KEY = ''
TEXT_LLM_SECRET_KEY = ''

# image LLM
IMAGE_LLM_URL = ''
IMAGE_LLM_TYPE = 'open-ai-proxy'
IMAGE_LLM_KEY = ''

FILE_SERVER = ''

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
