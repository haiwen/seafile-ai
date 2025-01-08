import logging
import os

from ocr.model import Model
from ocr.doc_ocr.utils import get_image_by_token

logger = logging.getLogger(__name__)


class DocOcrManager:

    def __init__(self):
        self.model = Model()

    def doc_ocr(self, path, download_token, file):
        if path and download_token:
            file_name = os.path.basename(path.rstrip('/'))
            content = get_image_by_token(download_token, file_name)
            return self.model.doc_predict(content)
        elif file:
            return self.model.doc_predict(file.read())
        else:
            return None
