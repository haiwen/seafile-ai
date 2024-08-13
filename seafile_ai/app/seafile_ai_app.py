from seafile_ai.image_processing.image_processing_manager import ImageProcessingManager
from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.utils.openai_api import OpenAIAPI


class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        self.openai_api = OpenAIAPI(config.OPENAI_PROXY_URL)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

        if config.OCR_SERVICE_TYPE == 'baidu-ocr':
            from seafile_ai.utils.baidu_ocr_api import BaiduOCRAPI
            self.baidu_ocr_api = BaiduOCRAPI(config.OCR_SERVICE_URL, config.OCR_SERVICE_API_KEY, config.OCR_SERVICE_SECRET_KEY)
        else:
            raise Exception('unknown ocr service type')
        self.image_processing_manager = ImageProcessingManager(self)

    def serve_forever(self):
        self.seafile_ai_http_server.start()
