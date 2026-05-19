from seafile_ai.image_processing.face_recognition_manager import FaceRecognitionManager
from seafile_ai.image_processing.image_processing_manager import ImageProcessingManager
from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.text_processing.text_processing_manager import TextProcessingManager
from seafile_ai.utils.face_embedding_api import FaceEmbeddingAPI
from seafile_ai.utils.seahub_api import SeahubAPI
from seafile_ai.data_logging.data_logging import DataLogging
from seafile_ai.utils.llm_api import LLMAPI

class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        self.data_logger = DataLogging(config.REDIS_HOST, config.REDIS_PORT, config.REDIS_PASSWORD)
        llm_type = config.LLM_TYPE
        base_url = config.LLM_URL
        api_key = config.LLM_KEY
        model = config.LLM_MODEL
        self.llm_api = LLMAPI(self.data_logger, llm_type, base_url, api_key, model)
        
        self.face_embedding_api = FaceEmbeddingAPI(config.FACE_EMBEDDING_SERVICE_URL, config.FACE_EMBEDDING_SERVICE_KEY)
        self.seahub_api = SeahubAPI(config.SEAFILE_SERVER_URL, config.JWT_PRIVATE_KEY)

        self.text_processing_manager = TextProcessingManager(self, config.LLM_TYPE)
        self.image_processing_manager = ImageProcessingManager(self)
        self.face_recognition_manager = FaceRecognitionManager(self)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

    def serve_forever(self):
        self.seafile_ai_http_server.start()
        self.seafile_ai_http_server.join()
