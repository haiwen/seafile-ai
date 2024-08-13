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

#openai
OPENAI_PROXY_URL = ''

# ocr
OCR_SERVICE_URL = ''
OCR_SERVICE_API_KEY = ''
OCR_SERVICE_SECRET_KEY = ''
OCR_SERVICE_TYPE = 'baidu-ocr'

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
