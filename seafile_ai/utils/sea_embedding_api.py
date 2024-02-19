import logging
import requests
import jwt
import time

from seafile_ai.utils.seafile_api import parse_response
from seafile_ai.config import SEA_EMBEDDING_KEY

logger = logging.getLogger(__name__)


class SeaEmbeddingAPI(object):

    def __init__(self, username, sea_embedding_url, time_out=180):
        self.username = username
        self.sea_embedding_url = sea_embedding_url.rstrip('/')
        self.time_out = time_out

    def gen_headers(self):
        payload = {'exp': int(time.time()) + 300, }
        token = jwt.encode(payload, SEA_EMBEDDING_KEY, algorithm='HS256')
        return {"Authorization": "Token %s" % token}

    def embeddings(self, input):
        url = self.sea_embedding_url + '/api/v1/embeddings/'
        params = {
            'input': input,
        }
        headers = self.gen_headers()

        response = requests.post(url, headers=headers, json=params, timeout=self.time_out)
        data = parse_response(response)
        return data
