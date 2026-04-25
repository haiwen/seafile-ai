from common.waitress_server import WaitressServer

from face_embedding.server.apis import flask_app


class FaceEmbeddingHttpServer(WaitressServer):

    def __init__(self, app):
        super().__init__(flask_app, app, host='0.0.0.0', port=8886)
