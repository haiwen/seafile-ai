from seafile_ai.image_processing.image_processing_manager import ImageProcessingManager
from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.text_processing.text_processing_manager import TextProcessingManager
from seafile_ai.utils.image_tags_api import ImageTagsAPI
from seafile_ai.pdf_manager import PDFManager, pdf_task_manager


class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        if config.LLM_TYPE == 'open-ai-proxy':
            from seafile_ai.utils.openai_api import OpenAIAPI
            self.openai_api = OpenAIAPI(config.LLM_URL)
        else:
            raise Exception('unknown llm type')

        self.image_tags_api = ImageTagsAPI(config.IMAGE_TAGS_SERVICE_URL, config.IMAGE_TAGS_SERVICE_KEY)

        if config.OCR_SERVICE_TYPE == 'seafile-ocr':
            from seafile_ai.utils.seafile_ocr_api import SeafileOCRAPI
            self.ocr_api = SeafileOCRAPI(config.OCR_SERVICE_URL, config.OCR_SERVICE_KEY)
        else:
            raise Exception('unknown ocr service type')

        self.text_processing_manager = TextProcessingManager(self, config.LLM_TYPE)
        self.image_processing_manager = ImageProcessingManager(self)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)
        self.pdf_manager = PDFManager(self)

        pdf_task_manager.init(self)
        
    def serve_forever(self):
        pdf_task_manager.start_ocr_workers()
        self.seafile_ai_http_server.start()
