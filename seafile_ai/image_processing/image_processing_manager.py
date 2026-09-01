import base64
import logging
import os
import re
from seafile_ai import config
from seafile_ai.image_processing.utils import resize_image_binary
from seafile_ai.utils import get_file_content_by_seafobj
from seafile_ai.utils.constants import LANGUAGE, MODEL_REASONING_TIER
from seafile_ai.config import AI_UTILS_TIER
from seafile_ai.utils.llm_api import get_llm_client_by_model_tier

logger = logging.getLogger(__name__)


class ImageProcessingManager:

    def __init__(self, app):
        self.app = app

    def image_caption(self, repo_id, obj_id, lang, context, capture_time, address):
        content = get_file_content_by_seafobj(repo_id, obj_id)
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
        tier = AI_UTILS_TIER.get('image_caption', MODEL_REASONING_TIER.MEDIUM.value)
        desc = get_llm_client_by_model_tier(self.app.data_logger, tier).run(messages, context)
        return desc

    def image_tags(self, repo_id, obj_id, candidate_tags, context):
        file = get_file_content_by_seafobj(repo_id, obj_id)
        if not file:
            return None
        content = resize_image_binary(file)
        base64_image = base64.b64encode(content).decode('utf-8')
        system_content = f'''
            You are an image classifier. Select the single most relevant tag for the image from the candidate tags below.
            - Only select an exact tag from the candidate tags. Never create, translate, or rewrite a tag.
            - If no candidate tag is relevant, select no tag.
            - Return only the selected tag without any additional text or explanations.
            Candidate tags: {','.join(candidate_tags)}
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
                        "text": "Select the most relevant candidate tag for this image."
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
        

        tier = AI_UTILS_TIER.get('image_tags', MODEL_REASONING_TIER.LOW.value)
        result = get_llm_client_by_model_tier(self.app.data_logger, tier).run(messages, context)
        tags = re.split(r'[，,]', result)
        return tags

    def ocr(self, repo_id, obj_id):
        if config.OCR_SERVICE_TYPE == 'seafile-ocr':
            file = get_file_content_by_seafobj(repo_id, obj_id)
            if not file:
                return None

            result = self.app.ocr_api.ocr(file)
            return result.get('ocr_result')
        else:
            raise Exception('unknown ocr service type')
    def face_embeddings_without_token(self, repo_id, obj_id, need_face):
        # get iamge by seafobj
        file = get_file_content_by_seafobj(repo_id, obj_id)
        if not file:
            return None
        result = self.app.face_embedding_api.face_embeddings(file, need_face)
        return result.get('faces')
