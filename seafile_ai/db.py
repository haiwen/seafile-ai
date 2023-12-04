# -*- coding: utf-8 -*-
import logging

from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

Base = declarative_base()


# def create_engine_from_conf(config):
#     db_url = config.SQLALCHEMY_DATABASE_URI
#     kwargs = dict(pool_recycle=300, pool_pre_ping=True, echo=False, echo_pool=False)
#     engine = create_engine(db_url, **kwargs)
#
#     return engine
#
#
# # SQLALCHEMY_DATABASE_URI = "mysql+mysqldb://%s:%s@%s:%s/%s?charset=utf8" % \
# #             (MYSQL_USER, quote_plus(MYSQL_PASSWORD), MYSQL_HOST, MYSQL_PORT, MYSQL_DB)
# #
# # if MYSQL_UNIX_SOCKET:
# #     SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI + '&unix_socket=' + MYSQL_UNIX_SOCKET


def create_engine_from_conf(config):
    db_server = config.MYSQL_HOST
    db_port = config.MYSQL_PORT
    db_username = config.MYSQL_USER
    db_passwd = config.MYSQL_PASSWORD
    db_name = config.MYSQL_DB
    mysql_unix_socket = config.MYSQL_UNIX_SOCKET

    db_url = "mysql+pymysql://%s:%s@%s:%s/%s?charset=utf8" % \
             (db_username, quote_plus(db_passwd), db_server, db_port, db_name)

    if mysql_unix_socket:
        db_url = db_url + '&unix_socket=' + mysql_unix_socket

    kwargs = dict(pool_recycle=300, echo=False, echo_pool=False)
    engine = create_engine(db_url, **kwargs)

    return engine


def init_db_session_class(config):
    """Configure session class for mysql according to the config file."""
    try:
        engine = create_engine_from_conf(config)
    except Exception as e:
        logger.error("Init db session class error: %s" % e)
        raise RuntimeError("Init db session class error: %s" % e)

    session = sessionmaker(bind=engine)
    return session


def create_db_tables(config):
    try:
        engine = create_engine_from_conf(config)
    except Exception as e:
        logger.error("Create tables error: %s" % e)
        raise RuntimeError("Create tables error: %s" % e)

    Base.metadata.create_all(engine)
