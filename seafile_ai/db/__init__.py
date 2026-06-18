# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.event import contains as has_event_listener, listen as add_event_listener
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import Pool

from seafile_ai.config import MYSQL_SEAHUB_DB_NAME, MYSQL_SEAFILE_DB_NAME, MYSQL_CCNET_DB_NAME, MYSQL_DB_HOST, \
    MYSQL_DB_PORT, MYSQL_DB_USER, MYSQL_DB_PWD

logger = logging.getLogger(__name__)

Base = declarative_base()


def create_engine_from_env(db='seahub'):
    need_connection_pool_fix = True

    db_name = ''
    if db == 'seahub':
        db_name = MYSQL_SEAHUB_DB_NAME
    elif db == 'seafile':
        db_name = MYSQL_SEAFILE_DB_NAME
    elif db == 'ccnet':
        db_name = MYSQL_CCNET_DB_NAME

    if not (db_name and MYSQL_DB_HOST and MYSQL_DB_PORT and MYSQL_DB_USER):
        raise RuntimeError('Database configured error')

    db_url = 'mysql+pymysql://%s:%s@%s:%s/%s?charset=utf8' % (MYSQL_DB_USER, quote_plus(MYSQL_DB_PWD), MYSQL_DB_HOST, MYSQL_DB_PORT, db_name)
    kwargs = dict(pool_recycle=300, echo=False, echo_pool=False)
    
    engine = create_engine(db_url, **kwargs)

    if need_connection_pool_fix and not has_event_listener(Pool, 'checkout', ping_connection):
        add_event_listener(Pool, 'checkout', ping_connection)

    return engine


def init_db_session_class(db='seahub'):
    try:
        engine = create_engine_from_env(db=db)
    except Exception as error:
        logger.error('Init db session class error: %s', error)
        raise RuntimeError('Init db session class error: %s' % error)

    return sessionmaker(bind=engine)


def ping_connection(dbapi_connection, connection_record, connection_proxy):  # pylint: disable=unused-argument
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute('SELECT 1')
        cursor.close()
    except:
        logger.info('fail to ping database server, disposing all cached connections')
        connection_proxy._pool.dispose()  # pylint: disable=protected-access
        raise DisconnectionError()
