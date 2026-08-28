import logging

from seafile_ai.image_processing.face_recognition_manager import FaceRecognitionManager
from seafile_ai.image_processing.image_processing_manager import ImageProcessingManager
from seafile_ai.chat_manager import StreamingChat
from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.text_processing.text_processing_manager import TextProcessingManager
from seafile_ai.db import init_db_session_class
from seafile_ai.utils.face_embedding_api import FaceEmbeddingAPI
from seafile_ai.utils.seahub_api import SeahubAPI
from seafile_ai.data_logging.data_logging import DataLogging
from seafile_ai.utils.llm_api import LLMAPI
from seafile_ai.utils.embedding_api import EmbeddingAPI

logger = logging.getLogger(__name__)

class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        self.db_session_class = init_db_session_class()
        self.data_logger = DataLogging(config.REDIS_HOST, config.REDIS_PORT, config.REDIS_PASSWORD)
        self.llm_api = LLMAPI(
            self.data_logger,
            config.DEFAULT_LLM_MODEL.get('model'),
            config.DEFAULT_LLM_MODEL.get('type', 'openai'),
            config.DEFAULT_LLM_MODEL.get('url'),
            config.DEFAULT_LLM_MODEL.get('key'),
            timeout=180,
        )
        self.embedding_api = None
        if config.EMBEDDING_MODEL_CONFIGURED:
            self.embedding_api = EmbeddingAPI(
                config.EMBEDDING_MODEL.get('model'),
                config.EMBEDDING_MODEL.get('type', 'openai'),
                config.EMBEDDING_MODEL.get('url'),
                config.EMBEDDING_MODEL.get('key'),
            )
        logger.info(
            'Embedding API %s; document search will use %s',
            'enabled' if self.embedding_api else 'disabled',
            'keyword and vector search' if self.embedding_api else 'keyword search only',
        )
        
        self.face_embedding_api = FaceEmbeddingAPI(config.FACE_EMBEDDING_SERVICE_URL, config.FACE_EMBEDDING_SERVICE_KEY)
        self.seahub_api = SeahubAPI(config.SEAFILE_SERVER_URL, config.SECRET_KEY)

        self.text_processing_manager = TextProcessingManager(self, config.DEFAULT_LLM_MODEL.get('type', 'openai'))
        self.image_processing_manager = ImageProcessingManager(self)
        self.face_recognition_manager = FaceRecognitionManager(self)
        self.streaming_chat = StreamingChat(self)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

    def serve_forever(self):
        self.seafile_ai_http_server.start()
        self.seafile_ai_http_server.join()
