from urllib.parse import quote as urlquote

import requests


class SeafileFileClient:
    def __init__(self, server_url, timeout=10):
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout

    def gen_file_get_url(self, token, filename):
        return '%s/files/%s/%s' % (self.server_url + '/seafhttp', token, urlquote(filename))

    def get_file_by_token(self, token, filename):
        response = requests.get(self.gen_file_get_url(token, filename), timeout=self.timeout)
        if response.status_code != 200:
            raise ConnectionError(response.status_code, response.text)
        return response.content

    def get_image_by_token(self, token, filename):
        return self.get_file_by_token(token, filename)
