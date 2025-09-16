import base64
import os
import re
from seafile_ai import config
from seafile_ai.image_processing.utils import resize_image_binary
from seafile_ai.utils import get_image_by_token
from seafile_ai.utils.constants import LANGUAGE


class ImageProcessingManager:

    def __init__(self, app):
        self.app = app

    def image_caption(self, path, download_token, lang, context, capture_time, address):
        file_name = os.path.basename(path)
        content = get_image_by_token(download_token, file_name)
        if not content:
            return None
        content = resize_image_binary(content)
        base64_image = base64.b64encode(content).decode('utf-8')
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Please describe the contents of this picture in {LANGUAGE[lang]}. Focus solely on the objects and details depicted, without discussing the emotions the picture may evoke. The description should be approximately 100 words."
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

        if capture_time and not address:
            messages[0]["content"][0]["text"] = f"Please describe the contents of this picture in {LANGUAGE[lang]}. This picture was captured on {capture_time}.Focus solely on the objects and details depicted, and combine with the capture time.You can describe the time like morning but don't mention the specific date and time,without discussing the emotions the picture may evoke. The description should be approximately 100 words."
        elif not capture_time and address:
            messages[0]["content"][0]["text"] = f"Please describe the contents of this picture in {LANGUAGE[lang]}. This picture was taken at {address}.Focus solely on the objects, details depicted and combine with the address, without discussing the emotions the picture may evoke. The description should be approximately 100 words."
        elif capture_time and address:
            messages[0]["content"][0]["text"] = f"Please describe the contents of this picture in {LANGUAGE[lang]}. This picture was taken at {address} on {capture_time}.Focus solely on the objects and details depicted,and combine with the capture time and location, and you can describe the time like morning but don't mention the specific date and time, without discussing the emotions the picture may evoke. The description should be approximately 100 words."
        desc = self.app.llm_api.run(messages, context)
        return desc

    def image_tags(self, path, download_token, lang, context):
        file_name = os.path.basename(path.rstrip('/'))
        file = get_image_by_token(download_token, file_name)
        if not file:
            return None
        content = resize_image_binary(file)
        base64_image = base64.b64encode(content).decode('utf-8')
        system_content = f'''
            You are an image tag extractor. Your task is to analyze the provided image and extract relevant tags. Please follow these guidelines:

            1. Keyword extraction:
            Extract up to 10 keyword phrases from the provided images, with no more than 3 words per phrase and no semantic overlap between them. Phrases must be common vocabulary displayed in the image, accurately representing key elements of the image (such as objects, scenes, actions, styles, etc.).

            2. Semantic similarity matching and replacement:
            For each extracted keyword, calculate its semantic similarity with each word in the reference tag. If the similarity exceeds 0.9, replace the keyword with the closest word in the reference tag.

            3. Important rules:
            - NEVER apologize or explain inability to recognize content
            - If you can see ANY content in the image, provide tags for what you can see
            - If the image is completely unreadable, return "unreadable image"
            - Always return at least one tag if any content is visible

            Output format:
            Return ONLY the processed keyword phrases, separated by English commas, without any additional text or explanations.
        '''
        
        messages = [
            {
                "role": "system",
                "content": system_content
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Please analyze this image and extract relevant tags in {LANGUAGE[lang]}."
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
        

        result = self.app.llm_api.run(messages, context)
        tags = re.split(r'[，,]', result)
        return tags

    def ocr(self, path, download_token):
        if config.OCR_SERVICE_TYPE == 'seafile-ocr':
            file_name = os.path.basename(path.rstrip('/'))
            file = get_image_by_token(download_token, file_name)
            if not file:
                return None

            result = self.app.ocr_api.ocr(file)
            return result.get('ocr_result')
        else:
            raise Exception('unknown ocr service type')

    def face_embeddings(self, path, download_token, need_face):
        file_name = os.path.basename(path.rstrip('/'))
        file = get_image_by_token(download_token, file_name)
        if not file:
            return None

        result = self.app.face_embedding_api.face_embeddings(file, need_face)
        return result.get('faces')
