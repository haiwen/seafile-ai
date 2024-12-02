from gevent import monkey; monkey.patch_all()

import config
from image_tags.app.app import App
from image_tags.app.log import LogConfigurator


def main():
    app_logger = LogConfigurator(config.LOG_LEVEL, config.LOG_FILE)

    if config.ENABLE_SYS_LOG:
        app_logger.add_syslog_handler()

    app = App(config)
    app.serve_forever()


if __name__ == '__main__':
    main()
