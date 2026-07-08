import os
import sys
import logging
import json
from urllib.parse import quote_plus
import yaml

logger = logging.getLogger(__name__)

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, basedir)


def _read_yaml(yaml_file_path=None, component_name=None):
    if yaml_file_path:
        if not os.path.isfile(yaml_file_path) or (not yaml_file_path.endswith('yml') and not yaml_file_path.endswith('yaml')):
            logger.warning(f'{yaml_file_path} is not existed or not a valid YAML file')
            return {}

        configs = {}
        with open(yaml_file_path, 'r', encoding='utf-8') as yaml_file:
            current_yaml_config = yaml.safe_load(yaml_file) or {}
            configs = current_yaml_config.get('global', {})
            if component_name:
                component_config = current_yaml_config.get(component_name, {})
                configs.update(component_config)
                if 'from_yaml' in component_config:
                    del configs['from_yaml']
                    configs.update(_read_yaml(component_config['from_yaml']))
        return configs
    return {}


def _check_type(func):
    def wrapper(self, key, default=None, check_type=True):
        result = func(self, key, default)
        if check_type:
            need_type = type(default)
            if need_type in (int, float):
                try:
                    result = need_type(result)
                except:
                    raise ValueError(f'Type of {key} must be a number')
            elif need_type == bool:
                if isinstance(result, str):
                    result = result.lower() in ('true', '1')
                else:
                    result = bool(result)
            elif need_type in (str, list, dict):
                result = need_type(result)
        return result
    return wrapper


class _ConfigParser(object):
    def __init__(self, yaml_file_path, component_name):
        assert yaml_file_path and component_name, "yaml_file_path and component_name must be specified in initilizing ConfigParser"
        self.refresh_yaml_configs(yaml_file_path, component_name)

    def refresh_yaml_configs(self, yaml_file_path=None, component_name=None):
        self.yaml_file_path = yaml_file_path or self.yaml_file_path
        self.component_name = component_name or self.component_name
        try:
            self.yaml_configs = _read_yaml(self.yaml_file_path, self.component_name)
        except Exception as e:
            logger.error(f'Failure to read YAML config file: {e}')
            raise

    @_check_type
    def get(self, key, default=None):
        if key in os.environ:
            value = os.getenv(key)
            try:
                value = json.loads(value)
            except:
                pass
            return value
        return self.yaml_configs.get(key, default)


def check_llm_validated(model):
    if not isinstance(model, dict) or model.get('disable', False):
        return False
    if model.get('type') in ('other', 'hosted_vllm'):
        required_fields = ('model', 'url')
    else:
        required_fields = ('model', 'key')
    return all(field in model for field in required_fields)


def get_llm_models_maps(models):
    if not models or not isinstance(models, list):
        return []
    model_id_models_map = {}
    tier_model_map = {}
    default_model = None

    for model in models:
        if not check_llm_validated(model):
            continue
        model['label'] = model.get('label', model['model'])
        model_id_models_map[model['model']] = model
        if model.get('tier') and model['tier'] not in tier_model_map:
            tier_model_map[model['tier']] = model
        if model.get('default', False) and not default_model:
            default_model = model
    if not model_id_models_map:
        raise ValueError('No valid LLM configurations')
    if not default_model:
        default_model = model_id_models_map[list(model_id_models_map.keys())[0]]

    return model_id_models_map, tier_model_map, default_model


SECRET_KEY = ''

# log
LOG_FILE = None
LOG_LEVEL = 'info'
ENABLE_SYS_LOG = False

APP_NAME = 'seafile-ai'

# LLM
LLM_MODELS = []
LLM_MODEL_ID_MODELS_MAP = {}
LLM_MODEL_TIER_MODELS_MAP = {}
DEFAULT_LLM_MODEL = {}
EMBEDDING_MODEL = {}

# Chat
CONTEXT_WINDOW_LIMIT = 20
CONTEXT_HISTORY_VALID_TIME = 168
MAX_STEPS = 5
COMPLETION_MAX_RETRIES = 2
COMPLETION_RETRY_INTERVAL = 1
TOOL_CALL_MAX_RETRIES = 1
TOOL_CALL_RETRY_INTERVAL = 1

# mysql
MYSQL_HOST = 'db'
MYSQL_USER = 'root'
MYSQL_PASSWORD = ''
MYSQL_PORT = 3306
MYSQL_SEAHUB_DB_NAME = 'seahub_db'
MYSQL_SEAFILE_DB_NAME = 'seafile_db'
MYSQL_CCNET_DB_NAME = 'ccnet_db'

# redis
REDIS_HOST = 'redis'
REDIS_PORT = 6379
REDIS_PASSWORD = ''


# Face embedding
FACE_EMBEDDING_SERVICE_URL = ''
FACE_EMBEDDING_SERVICE_KEY = ''

SEAFILE_SERVER_URL = ''
SEASEARCH_URL = ''
SEASEARCH_TOKEN = ''

INNER_METADATA_SERVER_URL = 'http://127.0.0.1:8084'

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


CONF_DIR = os.getenv('CONF_PATH', '/opt/seafile/conf/')

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
SEASEARCH_URL = os.getenv('SEASEARCH_URL') or SEASEARCH_URL
SEASEARCH_TOKEN = os.getenv('SEASEARCH_TOKEN') or SEASEARCH_TOKEN

MYSQL_DB_HOST = os.getenv('SEAFILE_MYSQL_DB_HOST') or MYSQL_HOST
MYSQL_DB_PORT = os.getenv('SEAFILE_MYSQL_DB_PORT') or MYSQL_PORT
MYSQL_DB_USER = os.getenv('SEAFILE_MYSQL_DB_USER') or MYSQL_USER
MYSQL_DB_PWD = os.getenv('SEAFILE_MYSQL_DB_PASSWORD') or MYSQL_PASSWORD
MYSQL_SEAHUB_DB_NAME = os.getenv('SEAFILE_MYSQL_DB_SEAHUB_DB_NAME') or MYSQL_SEAHUB_DB_NAME
MYSQL_SEAFILE_DB_NAME = os.getenv('SEAFILE_MYSQL_DB_SEAFILE_DB_NAME') or MYSQL_SEAFILE_DB_NAME
MYSQL_CCNET_DB_NAME = os.getenv('SEAFILE_MYSQL_DB_CCNET_DB_NAME') or MYSQL_CCNET_DB_NAME

yaml_file_path = os.path.join(CONF_DIR, os.environ.get('SEAFILE_AI_CONFIG_NAME', 'seafile_ai_config.yaml'))
configs = _ConfigParser(yaml_file_path, 'seafile-ai')
LLM_MODELS = configs.get('LLM_MODELS', [])
LLM_MODEL_ID_MODELS_MAP, LLM_MODEL_TIER_MODELS_MAP, DEFAULT_LLM_MODEL = get_llm_models_maps(LLM_MODELS)

EMBEDDING_MODEL = configs.get('EMBEDDING_MODEL', {})
if not check_llm_validated(EMBEDDING_MODEL):
    raise ValueError('EMBEDDING_MODEL is not set or invalid')

FACE_EMBEDDING_SERVICE_URL = os.getenv('FACE_EMBEDDING_SERVICE_URL') or FACE_EMBEDDING_SERVICE_URL
FACE_EMBEDDING_SERVICE_KEY = os.getenv('FACE_EMBEDDING_SERVICE_KEY') or FACE_EMBEDDING_SERVICE_KEY

LOG_LEVEL = os.getenv('SEAFILE_AI_LOG_LEVEL') or LOG_LEVEL

REDIS_HOST = os.getenv('REDIS_HOST') or REDIS_HOST
REDIS_PORT = os.getenv('REDIS_PORT') or REDIS_PORT
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD') or REDIS_PASSWORD

# metadata config
METADATA_SERVER_URL = os.getenv('INNER_METADATA_SERVER_URL') or INNER_METADATA_SERVER_URL
