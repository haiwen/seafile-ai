from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.utils.openai_api import OpenAIAPI


class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        self.openai_api = OpenAIAPI(config.OPENAI_PROXY_URL)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

    def serve_forever(self):
        self.seafile_ai_http_server.start()
