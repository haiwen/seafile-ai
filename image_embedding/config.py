import os
import sys
import logging

logger = logging.getLogger(__name__)

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, basedir)

SECRET_KEY = ''

FACE_EMBEDDING_MODEL_DIR = ''

# log
LOG_FILE = None
LOG_LEVEL = 'info'
ENABLE_SYS_LOG = False


CONF_DIR = '/opt/seafile/conf/'

try:
    if os.path.exists('local_settings.py'):
        from local_settings import *
except:
    pass

try:
    if os.path.exists(CONF_DIR):
        sys.path.insert(0, CONF_DIR)
    from face_embedding_settings import *
except ImportError as e:
    pass
