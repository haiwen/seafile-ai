from image_embedding.embedding.embedding_manager import EmbeddingManager
from image_embedding.server.image_embedding_http_server import ImageEmbeddingHttpServer


class ImageEmbeddingApp(object):
    def __init__(self, config):
        self.config = config
        self.face_embedding_manager = EmbeddingManager(config.FACE_EMBEDDING_MODEL_DIR)
        self.face_embedding_http_server = ImageEmbeddingHttpServer(self)

    def serve_forever(self):
        self.face_embedding_http_server.start()
