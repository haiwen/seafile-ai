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
LLM_TYPE = 'open-ai-proxy'
LLM_KEY = ''

# Image tags
IMAGE_TAGS_SERVICE_URL = ''
IMAGE_TAGS_SERVICE_KEY = ''

# Face embedding
FACE_EMBEDDING_SERVICE_URL = ''
FACE_EMBEDDING_SERVICE_KEY = ''

# OCR
OCR_SERVICE_URL = ''
OCR_SERVICE_KEY = ''
OCR_SERVICE_TYPE = 'seafile-ocr'

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

SECRET_KEY = os.getenv('JWT_PRIVATE_KEY') or SECRET_KEY
FACE_EMBEDDING_SERVICE_KEY = os.getenv('FACE_EMBEDDING_SERVICE_KEY') or FACE_EMBEDDING_SERVICE_KEY
IMAGE_TAGS_SERVICE_KEY = os.getenv('IMAGE_TAGS_SERVICE_KEY') or IMAGE_TAGS_SERVICE_KEY
OCR_SERVICE_KEY = os.getenv('OCR_SERVICE_KEY') or OCR_SERVICE_KEY

SEAFILE_SERVER_URL = os.getenv('SEAFILE_SERVER_URL') or SEAFILE_SERVER_URL
