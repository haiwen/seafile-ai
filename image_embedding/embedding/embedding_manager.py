import logging
from io import BytesIO

from PIL import Image
from seafobj import fs_mgr

from image_embedding.embedding.face_embedding_model import FaceEmbeddingModel

logger = logging.getLogger(__name__)


class EmbeddingManager:

    def __init__(self, model_dir):
        self.face_embedding_model = FaceEmbeddingModel(model_dir)

    def face_embedding(self, repo_id, obj_ids, need_face):
        embeddings = []
        for obj_id in obj_ids:
            faces = []
            f = fs_mgr.load_seafile(repo_id, 1, obj_id)
            content = f.get_content()
            if content.strip():
                result = self.face_embedding_model.embedding(content, need_face)
                if result is None:
                    try:
                        image = Image.open(BytesIO(content))
                        logger.warning('repo_id: %s, obj_id: %s, unsupported image format: %s', repo_id, obj_id, image.format)
                    except Exception as e:
                        logger.warning('repo_id: %s, obj_id: %s, unable to read image', repo_id, obj_id)
                else:
                    faces = result

            embeddings.append({
                'obj_id': obj_id,
                'faces': faces
            })

        return embeddings
