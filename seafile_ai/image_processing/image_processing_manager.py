import base64
import io
import os

from PIL import Image
from seafobj import fs_mgr

from seafile_ai.image_processing.CLIP_model import CLIPModel
from seafile_ai.image_processing.utils import resize_image_binary
from seafile_ai.utils import get_image_by_token
from seafile_ai.utils.constants import LANGUAGE


class ImageProcessingManager:

    def __init__(self, app, config):
        self.app = app
        self.clip_model = CLIPModel(config.CLIP_MODEL_PATH)

    def images_embedding(self, repo_id, obj_ids):
        embeddings = []
        for obj_id in obj_ids:
            f = fs_mgr.load_seafile(repo_id, 1, obj_id)
            content = f.get_content()
            image = Image.open(io.BytesIO(content))
            embedding = self.clip_model.embedding(image)
            embeddings.append({
                'obj_id': obj_id,
                'embedding': embedding.tolist()[0]
            })

        return embeddings

    def image_caption(self, path, download_token, lang):
        file_name = os.path.basename(path)
        content = get_image_by_token(download_token, file_name)
        ext = file_name.split('.')[-1]
        content = resize_image_binary(content, ext)
        base64_image = base64.b64encode(content).decode('utf-8')
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Please describe this image in {LANGUAGE[lang]} with a sentence of about 100 words."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]
        desc = self.app.openai_api.chat_completions(messages)
        return desc
