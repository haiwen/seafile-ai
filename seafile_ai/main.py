from common.logging import LogConfigurator
from seafile_ai.settings import settings
from seafile_ai.app.seafile_ai_app import SeafileAIApp


def main():
    app_logger = LogConfigurator(settings.LOG_LEVEL, settings.LOG_FILE)

    if settings.ENABLE_SYS_LOG:
        app_logger.add_syslog_handler()

    app = SeafileAIApp(settings)
    app.serve_forever()


if __name__ == '__main__':
    main()
