import logging
from io import BytesIO

from PIL import Image
from seafobj import fs_mgr

from image_embedding.embedding.insightface_model import InsightfaceModel

logger = logging.getLogger(__name__)


class EmbeddingManager:

    def __init__(self, model_dir):
        self.insightface_model = InsightfaceModel(model_dir)

    def face_embedding(self, repo_id, obj_ids, need_face):
        embeddings = []
        for obj_id in obj_ids:
            faces = []
            f = fs_mgr.load_seafile(repo_id, 1, obj_id)
            content = f.get_content()
            if content.strip():
                result = self.insightface_model.embedding(content, need_face)
                if result is None:
                    image = Image.open(BytesIO(content))
                    logger.warning('repo_id: %s, obj_id: %s, unsupported image format: %s', repo_id, obj_id, image.format)
                else:
                    faces = result

            embeddings.append({
                'obj_id': obj_id,
                'faces': faces
            })

        return embeddings
