from common.waitress_server import WaitressServer
from seafile_ai.server.apis import flask_app


class SeafileAIHttpServer(WaitressServer):

    def __init__(self, app):
        super().__init__(flask_app, app, host='0.0.0.0', port=8888)
