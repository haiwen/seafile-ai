from face_embedding.embedding.embedding_manager import EmbeddingManager
from face_embedding.server.face_embedding_http_server import FaceEmbeddingHttpServer


class FaceEmbeddingApp(object):
    def __init__(self, config):
        self.config = config
        self.face_embedding_manager = EmbeddingManager(config.FACE_EMBEDDING_MODEL_DIR)
        self.face_embedding_http_server = FaceEmbeddingHttpServer(self)

    def serve_forever(self):
        self.face_embedding_http_server.start()
