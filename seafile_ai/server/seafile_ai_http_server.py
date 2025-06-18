from threading import Thread
from waitress import create_server
from seafile_ai.server.apis import flask_app


class SeafileAIHttpServer(Thread):

    def __init__(self, app):
        Thread.__init__(self)
        flask_app.app = app

        self.server = create_server(flask_app, host='0.0.0.0', port=8888)

    def run(self):
        self.server.run()
