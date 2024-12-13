import base64
import os

from seafile_ai.image_processing.utils import resize_image_binary
from seafile_ai.utils import get_image_by_token
from seafile_ai.utils.constants import LANGUAGE


class ImageProcessingManager:

    def __init__(self, app):
        self.app = app

    def image_caption(self, path, download_token, lang):
        file_name = os.path.basename(path)
        content = get_image_by_token(download_token, file_name)
        content = resize_image_binary(content)
        base64_image = base64.b64encode(content).decode('utf-8')
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Please describe the contents of this picture in Chinese. Focus solely on the objects and details depicted, without discussing the emotions the picture may evoke. The description should be approximately 100 words."
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

    def image_tags(self, path, download_token, lang):
        result = self.app.image_tags_api.image_tags(path, download_token, lang)
        return result.get('tags')
