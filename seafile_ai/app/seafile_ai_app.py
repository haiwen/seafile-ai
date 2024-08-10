from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.utils.metadata_server_api import MetadataServerAPI
from seafile_ai.metadata_ai_services.metadata_ai_services import MetadataAIServices
class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        if config.LLM_TYPE == 'open-ai-proxy':
            from seafile_ai.utils.openai_api import OpenAIAPI
            self.openai_api = OpenAIAPI(config.LLM_URL)
        else:
            raise Exception('unknown llm type')
        self.metadata_server_api = MetadataServerAPI(
            config.APP_NAME,
            config.METADATA_SERVER_URL,
            config.METADATA_SERVER_SECRET_KEY,
        )
        self.metadata_ai_server = MetadataAIServices(self, config.LLM_TYPE)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

    def serve_forever(self):
        self.seafile_ai_http_server.start()
