import base64
import os
import sys

from seafobj import fs_mgr

from seafile_ai.image_processing.utils import resize_image_binary, resize_text_box
from seafile_ai.utils import ImageSizeException


class OCR:
    def __init__(self, app):
        self.app = app

    def get_box_and_text(self, repo_id, file_path, obj_id):
        f = fs_mgr.load_seafile(repo_id, 1, obj_id)
        content = f.get_content()

        file_name = os.path.basename(file_path.rstrip('/'))
        ext = file_name.split('.')[-1].lower()
        img_binary, ratio = resize_image_binary(content, ext, max_size=8192)
        image_size = sys.getsizeof(img_binary)
        if image_size // (1024 * 1024) > 10:
            raise ImageSizeException('image too big, size: %s' % image_size)

        encode_img = base64.b64encode(img_binary)
        results = self.app.baidu_ocr_api.baidu_ocr_accurate(encode_img)
        words_result = results['words_result']
        for item in words_result:
            item['location'] = resize_text_box(item['location'], ratio)
            for char in item['chars']:
                char['location'] = resize_text_box(char['location'], ratio)
        return words_result
