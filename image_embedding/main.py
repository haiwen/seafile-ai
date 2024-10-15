from gevent import monkey; monkey.patch_all()

import config

from image_embedding.app.log import LogConfigurator
from image_embedding.app.image_embedding_app import ImageEmbeddingApp


def main():
    app_logger = LogConfigurator(config.LOG_LEVEL, config.LOG_FILE)

    if config.ENABLE_SYS_LOG:
        app_logger.add_syslog_handler()

    app = ImageEmbeddingApp(config)
    app.serve_forever()


if __name__ == '__main__':
    main()
