# -*- coding: utf-8 -*-
import logging
from seafile_ai.event_redis import RedisClient

logger = logging.getLogger(__name__)


class DataLogging(object):

    def __init__(self, host, port, password):
        self.redis = RedisClient(host, port, password)

    def log_data(self, channel_name, message):
        try:
            self.redis.publish(channel_name, message)
        except Exception as e:
            logger.warning('publish message: %s, to channel: %s, error: %s .', message, channel_name, e)
