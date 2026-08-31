import config

from face_embedding.app.log import LogConfigurator
# from face_embedding.app.face_embedding_app import FaceEmbeddingApp


def main():
    app_logger = LogConfigurator(config.LOG_LEVEL, config.LOG_FILE)

    if config.ENABLE_SYS_LOG:
        app_logger.add_syslog_handler()

    # app = FaceEmbeddingApp(config)
    # app.serve_forever()


if __name__ == '__main__':
    main()
