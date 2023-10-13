from gevent import monkey; monkey.patch_all()
import pymysql; pymysql.install_as_MySQLdb()

import config
from seafile_ai.app.log import LogConfigurator
from seafile_ai.app.seafile_ai_app import SeafileAIApp


def main():
    app_logger = LogConfigurator(config.LOG_LEVEL, config.LOG_FILE)

    if config.ENABLE_SYS_LOG:
        app_logger.add_syslog_handler()

    app = SeafileAIApp(config)
    app.serve_forever()


if __name__ == '__main__':
    main()
