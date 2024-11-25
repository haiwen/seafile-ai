from gevent import monkey; monkey.patch_all()

import config
import os

from ocr.app.log import LogConfigurator
from ocr.app.app import App

os.environ["MODELSCOPE_CACHE"] = config.OCR_MODEL_DIR


def main():
    app_logger = LogConfigurator(config.LOG_LEVEL, config.LOG_FILE)

    if config.ENABLE_SYS_LOG:
        app_logger.add_syslog_handler()

    app = App()
    app.serve_forever()


if __name__ == '__main__':
    main()
