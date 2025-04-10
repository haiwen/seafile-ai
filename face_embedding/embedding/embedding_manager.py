import logging

from face_embedding.embedding.face_embedding_model import FaceEmbeddingModel

logger = logging.getLogger(__name__)


class EmbeddingManager:

    def __init__(self, model_dir):
        self.face_embedding_model = FaceEmbeddingModel(model_dir)

    def face_embedding(self, file, need_face):
        faces = self.face_embedding_model.embedding(file, need_face)

        return faces
