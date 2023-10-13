# -*- coding: utf-8 -*-
import logging

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

Base = declarative_base()


def create_engine_from_conf(config):
    db_url = config.SQLALCHEMY_DATABASE_URI
    kwargs = dict(pool_recycle=300, pool_pre_ping=True, echo=False, echo_pool=False)
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
