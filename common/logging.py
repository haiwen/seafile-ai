import logging
import sys
from logging import handlers


def get_log_level(level):
    if level == 'debug':
        return logging.DEBUG
    if level == 'info':
        return logging.INFO
    return logging.WARNING


class LogConfigurator:
    def __init__(self, level, logfile=None, syslog_ident='seafevents'):
        self._level = get_log_level(level)
        self._logfile = logfile
        self._syslog_ident = syslog_ident

        if logfile is None:
            self._basic_config()
        else:
            self._rotating_config()

    def _rotating_config(self):
        handler = handlers.TimedRotatingFileHandler(self._logfile, when='W0', interval=1, backupCount=7)
        handler.setLevel(self._level)
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(name)s:%(lineno)s %(funcName)s %(message)s')
        handler.setFormatter(formatter)

        logging.root.setLevel(self._level)
        logging.root.addHandler(handler)

    def _basic_config(self):
        logging.basicConfig(
            format='[%(asctime)s] [%(levelname)s] %(name)s:%(lineno)s %(funcName)s %(message)s',
            datefmt='%m/%d/%Y %H:%M:%S',
            level=self._level,
            stream=sys.stdout,
        )

    def add_syslog_handler(self):
        handler = handlers.SysLogHandler(address='/dev/log')
        handler.setLevel(self._level)
        formatter = logging.Formatter(f'{self._syslog_ident}[%(process)d]: %(message)s')
        handler.setFormatter(formatter)
        logging.root.addHandler(handler)
