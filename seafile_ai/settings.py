import importlib.util
import os


CONF_DIR = '/opt/seafile/conf/'


class SeafileAISettings:
    def __init__(self):
        self.SECRET_KEY = ''
        self.LOG_FILE = None
        self.LOG_LEVEL = 'info'
        self.ENABLE_SYS_LOG = False
        self.APP_NAME = 'seafile-ai'
        self.LLM_URL = None
        self.LLM_TYPE = 'openai'
        self.LLM_KEY = None
        self.LLM_MODEL = 'gpt-4o-mini'
        self.REDIS_HOST = 'redis'
        self.REDIS_PORT = 6379
        self.REDIS_PASSWORD = ''
        self.FACE_EMBEDDING_SERVICE_URL = ''
        self.FACE_EMBEDDING_SERVICE_KEY = ''
        self.SEAFILE_SERVER_URL = ''

    def apply_mapping(self, mapping):
        for key, value in mapping.items():
            if key.isupper():
                setattr(self, key, value)


def _load_python_settings(path, module_name):
    if not os.path.exists(path):
        return {}

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return {}

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        key: getattr(module, key)
        for key in dir(module)
        if key.isupper()
    }


def load_settings():
    settings = SeafileAISettings()
    settings.apply_mapping(_load_python_settings('seafile_ai_settings.py', 'seafile_ai_local_settings'))
    settings.apply_mapping(_load_python_settings(os.path.join(CONF_DIR, 'seafile_ai_settings.py'), 'seafile_ai_conf_settings'))

    settings.SEAFILE_SERVER_URL = os.getenv('SEAFILE_SERVER_URL') or settings.SEAFILE_SERVER_URL
    settings.SECRET_KEY = os.getenv('JWT_PRIVATE_KEY') or settings.SECRET_KEY
    settings.LLM_TYPE = os.getenv('SEAFILE_AI_LLM_TYPE') or settings.LLM_TYPE
    settings.LLM_URL = os.getenv('SEAFILE_AI_LLM_URL') or settings.LLM_URL
    settings.LLM_KEY = os.getenv('SEAFILE_AI_LLM_KEY') or settings.LLM_KEY
    settings.LLM_MODEL = os.getenv('SEAFILE_AI_LLM_MODEL') or settings.LLM_MODEL
    settings.FACE_EMBEDDING_SERVICE_URL = os.getenv('FACE_EMBEDDING_SERVICE_URL') or settings.FACE_EMBEDDING_SERVICE_URL
    settings.FACE_EMBEDDING_SERVICE_KEY = os.getenv('FACE_EMBEDDING_SERVICE_KEY') or settings.FACE_EMBEDDING_SERVICE_KEY
    settings.LOG_LEVEL = os.getenv('SEAFILE_AI_LOG_LEVEL') or settings.LOG_LEVEL
    settings.REDIS_HOST = os.getenv('REDIS_HOST') or settings.REDIS_HOST
    settings.REDIS_PORT = int(os.getenv('REDIS_PORT') or settings.REDIS_PORT)
    settings.REDIS_PASSWORD = os.getenv('REDIS_PASSWORD') or settings.REDIS_PASSWORD
    return settings


settings = load_settings()
