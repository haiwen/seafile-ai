# -*- coding: utf-8 -*-
import redis
import logging
import time


logger = logging.getLogger(__name__)


class RedisClient(object):

    def __init__(self, host='', port=6379, password=None, socket_connect_timeout=30, socket_timeout=None):
        self._host = host
        self._port = port
        self._password = password

        """
        By default, each Redis instance created will in turn create its own connection pool.
        Every caller using redis client will has it's own pool with config caller passed.
        """
        self.connection = redis.StrictRedis(
            host=self._host, port=self._port, password=self._password,
            socket_timeout=socket_timeout, socket_connect_timeout=socket_connect_timeout,
            decode_responses=True
        )

    def publish(self, channel_name, message):
        self.connection.publish(channel_name, message)

    def get_subscriber(self, channel_name):
        while True:
            try:
                subscriber = self.connection.pubsub(ignore_subscribe_messages=True)
                subscriber.subscribe(channel_name)
            except redis.AuthenticationError as e:
                logger.critical('connect to redis auth error: %s', e)
                raise e
            except Exception as e:
                logger.error('redis pubsub failed. {} retry after 10s'.format(e))
                time.sleep(10)
            else:
                return subscriber
