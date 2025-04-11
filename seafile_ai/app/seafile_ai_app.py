import os

from seafile_ai.image_processing.image_processing_manager import ImageProcessingManager
from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.text_processing.text_processing_manager import TextProcessingManager
from seafile_ai.utils.face_embedding_api import FaceEmbeddingAPI
from seafile_ai.utils.image_tags_api import ImageTagsAPI


class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        if config.LLM_TYPE == 'open-ai-proxy':
            from seafile_ai.utils.openai_api import OpenAIAPI
            self.openai_api = OpenAIAPI(config.LLM_URL)
        else:
            raise Exception('unknown llm type')

<<<<<<< HEAD
        self.image_tags_api = ImageTagsAPI(config.IMAGE_TAGS_SERVICE_URL, config.IMAGE_TAGS_SERVICE_KEY)
        self.face_embedding_api = FaceEmbeddingAPI(config.FACE_EMBEDDING_SERVICE_URL, config.FACE_EMBEDDING_SERVICE_KEY)
=======
        self.image_tags_api = ImageTagsAPI(config.IMAGE_TAGS_SERVICE_URL, os.getenv('IMAGE_TAGS_SERVICE_KEY') or config.IMAGE_TAGS_SERVICE_KEY)
        self.image_embedding_api = ImageEmbeddingAPI(config.IMAGE_EMBEDDING_SERVICE_URL, os.getenv('FACE_EMBEDDING_SERVICE_KEY') or config.IMAGE_EMBEDDING_SERVICE_KEY)
>>>>>>> 201a72d (feat: read service key from env)

        if config.OCR_SERVICE_TYPE == 'seafile-ocr':
            from seafile_ai.utils.seafile_ocr_api import SeafileOCRAPI
            self.ocr_api = SeafileOCRAPI(config.OCR_SERVICE_URL, os.getenv('OCR_SERVICE_KEY') or config.OCR_SERVICE_KEY)
        else:
            raise Exception('unknown ocr service type')

        self.text_processing_manager = TextProcessingManager(self, config.LLM_TYPE)
        self.image_processing_manager = ImageProcessingManager(self)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

    def serve_forever(self):
        self.seafile_ai_http_server.start()
