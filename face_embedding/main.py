from common.logging import LogConfigurator
from face_embedding.settings import settings
from face_embedding.app.face_embedding_app import FaceEmbeddingApp


def main():
    app_logger = LogConfigurator(settings.LOG_LEVEL, settings.LOG_FILE)

    if settings.ENABLE_SYS_LOG:
        app_logger.add_syslog_handler()

    app = FaceEmbeddingApp(settings)
    app.serve_forever()


if __name__ == '__main__':
    main()
