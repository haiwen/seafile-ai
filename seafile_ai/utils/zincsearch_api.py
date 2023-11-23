import json
import logging
import requests
import ndjson

logger = logging.getLogger(__name__)


def parse_response(response):
    if response.status_code >= 400:
        raise ConnectionError(response.status_code, response.text)
    else:
        try:
            return json.loads(response.text)
        except:
            pass


class ZincSearchAPI(object):

    def __init__(self, zinc_server, token, timeout=180):
        self.token = token
        self.zinc_server = zinc_server
        self.timeout = timeout
        self.gen_header()

    def gen_header(self):
        self.headers = {
            'Authorization': 'Basic ' + self.token
        }

    def create_mapping(self, index_name, mapping):
        url = self.zinc_server + '/es/' + index_name + '/_mapping'
        response = requests.put(url, headers=self.headers, json=mapping, timeout=self.timeout)
        data = parse_response(response)

        return data

    def bulk(self, data):
        """
        this option includes add, update and delete
        """
        url = self.zinc_server + '/es/_bulk'
        data = ndjson.dumps(data)
        response = requests.post(url, headers=self.headers, data=data, timeout=self.timeout)

        return parse_response(response)

    def vector_search(self, data, index_name):
        url = self.zinc_server + '/api/' + index_name + '/_search/vector'
        response = requests.post(url, headers=self.headers, json=data, timeout=self.timeout)

        return parse_response(response)

    def normal_search(self, index_name, data):
        url = self.zinc_server + '/es/' + index_name + '/_search'
        response = requests.post(url, headers=self.headers, json=data, timeout=self.timeout)

        return parse_response(response)

    def check_index_mapping(self, index_name):
        url = self.zinc_server + '/es/' + index_name + '/_mapping'
        response = requests.get(url, headers=self.headers, timeout=self.timeout)
        if response.status_code == 400:
            return {'is_exist': False}
        elif response.status_code > 400:
            raise ConnectionError(response.status_code, response.text)

        return {'is_exist': True}
