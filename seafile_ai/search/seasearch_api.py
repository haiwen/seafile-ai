import json
import logging

import requests

logger = logging.getLogger(__name__)


def parse_response(response):
    if response.status_code == 400:
        logger.warning('seasearch error: %s', response.text)
    if response.status_code > 400:
        raise ConnectionError(response.status_code, response.text)
    try:
        return json.loads(response.text)
    except Exception:
        return None


class Encoder(json.JSONEncoder):
    def encode(self, obj, *args, **kwargs):
        return '\n'.join(super(Encoder, self).encode(each, *args, **kwargs) for each in obj)


def ndjson_dumps(*args, **kwargs):
    kwargs.setdefault('cls', Encoder)
    return json.dumps(*args, **kwargs)


class SeaSearchAPI:
    def __init__(self, server, token, timeout=180):
        self.server = server.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.headers = {
            'Authorization': 'Basic ' + token,
        }

    def unified_search(self, data):
        url = self.server + '/api/unified_search'
        response = requests.post(url, headers=self.headers, data=data, timeout=self.timeout)
        return parse_response(response)

    def vector_search(self, index_name, data):
        url = self.server + '/api/' + index_name + '/_search/vector'
        response = requests.post(url, headers=self.headers, json=data, timeout=self.timeout)
        return parse_response(response)
