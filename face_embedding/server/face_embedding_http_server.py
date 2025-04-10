from threading import Thread
from gevent.pywsgi import WSGIServer

from face_embedding.server.apis import flask_app


class FaceEmbeddingHttpServer(Thread):

    def __init__(self, app):
        Thread.__init__(self)
        flask_app.app = app

        self.server = WSGIServer(('0.0.0.0', 8886), flask_app)

    def run(self):
        self.server.serve_forever()
