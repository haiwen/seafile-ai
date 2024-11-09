from seafobj import fs_mgr

from image_embedding.embedding.insightface_model import InsightfaceModel


class EmbeddingManager:

    def __init__(self, model_dir):
        self.insightface_model = InsightfaceModel(model_dir)

    def face_embedding(self, repo_id, obj_ids):
        embeddings = []
        for obj_id in obj_ids:
            f = fs_mgr.load_seafile(repo_id, 1, obj_id)
            content = f.get_content()
            result = self.insightface_model.embedding(content)
            embeddings.append({
                'obj_id': obj_id,
                'faces': result
            })

        return embeddings
