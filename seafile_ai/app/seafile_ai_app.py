from seafile_ai.image_processing.image_processing_manager import ImageProcessingManager
from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.text_processing.text_processing_manager import TextProcessingManager
from seafile_ai.utils.face_embedding_api import FaceEmbeddingAPI


class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        if config.LLM_TYPE == 'openai-proxy':
            from seafile_ai.utils.openai_api import OpenAIAPI
            self.openai_api = OpenAIAPI(config.LLM_URL)
        elif config.LLM_TYPE == 'openai':
            from seafile_ai.utils.openai_api import OpenAIAPI
            self.openai_api = OpenAIAPI(api_key=config.LLM_KEY)
        else:
            raise Exception('unknown llm type')

        self.face_embedding_api = FaceEmbeddingAPI(config.FACE_EMBEDDING_SERVICE_URL, config.FACE_EMBEDDING_SERVICE_KEY)

        self.text_processing_manager = TextProcessingManager(self, config.LLM_TYPE)
        self.image_processing_manager = ImageProcessingManager(self)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

    def serve_forever(self):
        self.seafile_ai_http_server.start()
