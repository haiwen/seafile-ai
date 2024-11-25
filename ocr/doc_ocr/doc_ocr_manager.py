import logging
import os

from ocr.doc_ocr.model import Model
from ocr.doc_ocr.utils import get_image_by_token

logger = logging.getLogger(__name__)


class DocOcrManager:

    def __init__(self):
        self.model = Model()

    def doc_ocr(self, path, download_token):
        file_name = os.path.basename(path.rstrip('/'))
        content = get_image_by_token(download_token, file_name)
        if not content:
            return None

        return self.model.predict(content)


