import logging

from ocr.doc_ocr.model import Model

logger = logging.getLogger(__name__)


class DocOcrManager:

    def __init__(self):
        self.model = Model()

    def doc_ocr(self, file):
        return self.model.predict(file)


