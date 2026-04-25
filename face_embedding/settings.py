import importlib.util
import os


CONF_DIR = '/opt/seafile/conf/'


class FaceEmbeddingSettings:
    def __init__(self):
        self.SECRET_KEY = ''
        self.FACE_EMBEDDING_MODEL_DIR = ''
        self.LOG_FILE = None
        self.LOG_LEVEL = 'info'
        self.ENABLE_SYS_LOG = False

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
    settings = FaceEmbeddingSettings()
    settings.apply_mapping(_load_python_settings('local_settings.py', 'face_embedding_local_settings'))
    settings.apply_mapping(_load_python_settings(os.path.join(CONF_DIR, 'face_embedding_settings.py'), 'face_embedding_conf_settings'))
    settings.SECRET_KEY = os.getenv('FACE_EMBEDDING_SERVICE_KEY') or settings.SECRET_KEY
    return settings


settings = load_settings()
