from threading import Thread
from waitress import create_server

from face_embedding.server.apis import flask_app


class FaceEmbeddingHttpServer(Thread):

    def __init__(self, app):
        Thread.__init__(self)
        flask_app.app = app

        self.server = create_server(flask_app, host='0.0.0.0', port=8886)

    def run(self):
        self.server.run()
