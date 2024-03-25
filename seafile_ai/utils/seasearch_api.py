import json
import logging
import requests
import ndjson

logger = logging.getLogger(__name__)


def parse_response(response):
    if response.status_code > 400:
        raise ConnectionError(response.status_code, response.text)
    else:
        try:
            return json.loads(response.text)
        except:
            pass


class SeaSearchAPI(object):

    def __init__(self, server, token, timeout=180):
        self.token = token
        self.server = server
        self.timeout = timeout
        self.gen_header()

    def gen_header(self):
        self.headers = {
            'Authorization': 'Basic ' + self.token
        }

    def create_index(self, index_name, data):
        url = self.server + '/api/index/' + index_name
        response = requests.put(url, headers=self.headers, json=data, timeout=self.timeout)
        data = parse_response(response)

        return data

    def create_document_by_id(self, index_name, doc_id, date):
        url = self.server + '/api/' + index_name + '/_doc/' + doc_id
        response = requests.put(url, headers=self.headers, json=date, timeout=self.timeout)
        data = parse_response(response)

        return data

    def bulk(self, index_name, data):
        """
        this option includes add, update and delete index or document
        """
        url = self.server + '/es/' + index_name + '/_bulk'
        data = ndjson.dumps(data)
        response = requests.post(url, headers=self.headers, data=data, timeout=self.timeout)

        return parse_response(response)

    def vector_search(self, index_name, data):
        url = self.server + '/api/' + index_name + '/_search/vector'
        response = requests.post(url, headers=self.headers, json=data, timeout=self.timeout)

        return parse_response(response)

    def normal_search(self, index_name, data):
        url = self.server + '/es/' + index_name + '/_search'
        response = requests.post(url, headers=self.headers, json=data, timeout=self.timeout)

        return parse_response(response)

    def m_search(self, data, unify_score=True):
        url = self.server + '/es/_msearch'
        if unify_score:
            url += '?unify_score=true'
        data = ndjson.dumps(data)
        response = requests.post(url, headers=self.headers, data=data, timeout=self.timeout)
        return parse_response(response)

    def check_index_mapping(self, index_name):
        url = self.server + '/es/' + index_name + '/_mapping'
        response = requests.get(url, headers=self.headers, timeout=self.timeout)
        if response.status_code == 400:
            return {'is_exist': False}
        elif response.status_code > 400:
            raise ConnectionError(response.status_code, response.text)

        return {'is_exist': True}

    def check_document_by_id(self, index_name, doc_id):
        url = self.server + '/api/' + index_name + '/_doc/' + doc_id
        response = requests.get(url, headers=self.headers, timeout=self.timeout)
        if response.status_code == 400:
            return {'is_exist': False}
        elif response.status_code > 400:
            raise ConnectionError(response.status_code, response.text)

        return {'is_exist': True}

    def get_document_by_id(self, index_name, doc_id):
        url = self.server + '/api/' + index_name + '/_doc/' + doc_id
        response = requests.get(url, headers=self.headers, timeout=self.timeout)
        return parse_response(response)

    def delete_document_by_id(self, index_name, doc_id):
        url = self.server + '/api/' + index_name + '/_doc/' + doc_id
        response = requests.delete(url, headers=self.headers, timeout=self.timeout)
        return parse_response(response)

    def delete_index_by_name(self, index_name):
        url = self.server + '/api/index/' + index_name
        response = requests.delete(url, headers=self.headers, timeout=self.timeout)
        return parse_response(response)

    def update_document_by_id(self, index_name, doc_id, data):
        url = self.server + '/api/' + index_name + '/_doc/' + doc_id
        response = requests.put(url, headers=self.headers, json=data, timeout=self.timeout)
        return parse_response(response)
