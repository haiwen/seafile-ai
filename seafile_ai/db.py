# -*- coding: utf-8 -*-
import logging

from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

Base = declarative_base()


def create_engine_from_conf(server, port, username, passwd, db_name, unix_socket):
    db_url = "mysql+pymysql://%s:%s@%s:%s/%s?charset=utf8" % \
             (username, quote_plus(passwd), server, port, db_name)

    if unix_socket:
        db_url = db_url + '&unix_socket=' + unix_socket

    kwargs = dict(pool_recycle=300, echo=False, echo_pool=False)
    engine = create_engine(db_url, **kwargs)

    return engine


def init_db_session_class(server, port, username, passwd, db_name, unix_socket=''):
    """Configure session class for mysql according to the config file."""
    try:
        engine = create_engine_from_conf(server, port, username, passwd, db_name, unix_socket)
    except Exception as e:
        logger.error("Init db session class error: %s" % e)
        raise RuntimeError("Init db session class error: %s" % e)

    session = sessionmaker(bind=engine)
    return session
