from seafile_ai.image_processing.image_processing_manager import ImageProcessingManager
from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.text_processing.text_processing_manager import TextProcessingManager
from seafile_ai.clients.seafile_client import SeafileFileClient
from seafile_ai.utils.face_embedding_api import FaceEmbeddingAPI
from seafile_ai.data_logging.data_logging import DataLogging
from seafile_ai.utils.llm_api import LLMAPI

class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        self.data_logger = DataLogging(config.REDIS_HOST, config.REDIS_PORT, config.REDIS_PASSWORD)
        self.seafile_file_client = SeafileFileClient(config.SEAFILE_SERVER_URL)
        llm_type = config.LLM_TYPE
        base_url = config.LLM_URL
        api_key = config.LLM_KEY
        model = config.LLM_MODEL
        self.llm_api = LLMAPI(self.data_logger, llm_type, base_url, api_key, model)
        
        self.face_embedding_api = FaceEmbeddingAPI(config.FACE_EMBEDDING_SERVICE_URL, config.FACE_EMBEDDING_SERVICE_KEY)

        self.text_processing_manager = TextProcessingManager(self.llm_api, self.seafile_file_client)
        self.image_processing_manager = ImageProcessingManager(self.llm_api, self.seafile_file_client, self.face_embedding_api)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

    def serve_forever(self):
        self.seafile_ai_http_server.start()
        self.seafile_ai_http_server.join()
