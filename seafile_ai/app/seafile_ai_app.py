from seafile_ai.image_processing.image_processing_manager import ImageProcessingManager
from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.text_processing.text_processing_manager import TextProcessingManager


class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        if config.TEXT_LLM_TYPE == 'open-ai-proxy':
            from seafile_ai.utils.openai_api import OpenAIAPI
            self.text_llm_api = OpenAIAPI(config.TEXT_LLM_URL)
        elif config.TEXT_LLM_TYPE == 'aliyun':
            from seafile_ai.utils.aliyun_llm_api import AliyunLLMAPI
            self.text_llm_api = AliyunLLMAPI(config.TEXT_LLM_URL, config.TEXT_LLM_KEY)
        elif config.TEXT_LLM_TYPE == 'baidu':
            from seafile_ai.utils.baidu_llm_api import BaiduLLMAPI
            self.text_llm_api = BaiduLLMAPI(config.TEXT_LLM_URL, config.TEXT_LLM_KEY, config.TEXT_LLM_SECRET_KET)
        else:
            raise Exception('unknown text llm type')

        if config.IMAGE_LLM_TYPE == 'open-ai-proxy':
            from seafile_ai.utils.openai_api import OpenAIAPI
            self.image_llm_api = OpenAIAPI(config.IMAGE_LLM_URL)
        else:
            raise Exception('unknown image llm type')

        self.text_processing_manager = TextProcessingManager(self, config.TEXT_LLM_TYPE)
        self.image_processing_manager = ImageProcessingManager(self)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

    def serve_forever(self):
        self.seafile_ai_http_server.start()
