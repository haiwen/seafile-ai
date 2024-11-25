from ocr.doc_ocr.doc_ocr_manager import DocOcrManager
from ocr.server.http_server import HttpServer


class App(object):
    def __init__(self):
        self.doc_ocr_manager = DocOcrManager()
        self.http_server = HttpServer(self)

    def serve_forever(self):
        self.http_server.start()
