import time

import jwt
import requests
import logging

from seafile_ai.clients.http_client import parse_json_response

logger = logging.getLogger(__name__)


class FaceEmbeddingAPI:
    def __init__(self, server_url, secret_key, timeout=60):
        self.server_url = server_url.rstrip('/')
        self.secret_key = secret_key
        self.timeout = timeout

    def gen_headers(self):
        payload = {'exp': int(time.time()) + 300, }
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return {"Authorization": "Token %s" % token}

    def face_embeddings(self, file, need_face=False):
        url = self.server_url + '/api/v1/face-embeddings/'
        headers = self.gen_headers()
        json_data = {
            'need_face': need_face
        }
        response = requests.post(url, files={'file': file}, data=json_data, headers=headers, timeout=self.timeout)
        data = parse_json_response(response)
        return data
