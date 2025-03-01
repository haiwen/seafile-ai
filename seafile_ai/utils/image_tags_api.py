import time

import jwt
import requests
import logging

from seafile_ai.utils import parse_response

logger = logging.getLogger(__name__)


class ImageTagsAPI:
    def __init__(self, server_url, secret_key, timeout=60):
        self.server_url = server_url.rstrip('/')
        self.secret_key = secret_key
        self.timeout = timeout

    def gen_headers(self):
        payload = {'exp': int(time.time()) + 300, }
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return {"Authorization": "Token %s" % token}

    def image_tags(self, file, lang):
        url = self.server_url + '/api/v1/image-tags/'
        headers = self.gen_headers()
        json_data = {
            'lang': lang
        }
        response = requests.post(url, files={'file': file}, data=json_data, headers=headers, timeout=self.timeout)
        data = parse_response(response)
        return data
