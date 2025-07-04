from seafile_ai.image_processing.image_processing_manager import ImageProcessingManager
from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.text_processing.text_processing_manager import TextProcessingManager
from seafile_ai.utils.face_embedding_api import FaceEmbeddingAPI
from seafile_ai.data_logging.data_logging import DataLogging
from seafile_ai.utils.openai_api import OpenAIAPI

class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        self.data_logger = DataLogging(config.REDIS_HOST, config.REDIS_PORT, config.REDIS_PASSWORD)
        llm_type = config.LLM_TYPE
        base_url = config.LLM_URL
        api_key = config.LLM_KEY
        model = config.LLM_MODEL
        if llm_type not in ['openai-proxy', 'openai', 'other']:
            raise Exception('unknown llm type')
        self.openai_api = OpenAIAPI(llm_type, base_url, api_key, model)
        self.openai_api.init(self.data_logger)
        
        self.face_embedding_api = FaceEmbeddingAPI(config.FACE_EMBEDDING_SERVICE_URL, config.FACE_EMBEDDING_SERVICE_KEY)

        self.text_processing_manager = TextProcessingManager(self, config.LLM_TYPE)
        self.image_processing_manager = ImageProcessingManager(self)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

    def serve_forever(self):
        self.seafile_ai_http_server.start()
