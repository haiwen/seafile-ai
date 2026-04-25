from threading import Thread

from waitress import create_server


class WaitressServer(Thread):
    def __init__(self, flask_app, app, host, port):
        super().__init__()
        flask_app.app = app
        self.server = create_server(flask_app, host=host, port=port)

    def run(self):
        self.server.run()
