# -*- coding: utf-8 -*-
import redis


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
