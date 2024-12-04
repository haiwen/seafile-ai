from image_tags.models.image_tags_manager import ImageTagsManager
from image_tags.server.http_server import HttpServer


class App(object):
    def __init__(self, config):
        self.image_tags_manager = ImageTagsManager(config.IMAGE_TAGS_MODEL_DIR, config.IMAGE_TAGS_MODEL_TYPE)
        self.http_server = HttpServer(self)

    def serve_forever(self):
        self.http_server.start()
