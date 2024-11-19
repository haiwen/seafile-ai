from seafobj import fs_mgr

from image_embedding.embedding.insightface_model import InsightfaceModel


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
                faces = self.insightface_model.embedding(content, need_face)

            embeddings.append({
                'obj_id': obj_id,
                'faces': faces
            })

        return embeddings
