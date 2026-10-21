import io
import logging
import time

import jwt
import requests

from seafile_ai.utils import parse_response

logger = logging.getLogger(__name__)


class SeahubAPI:
    def __init__(self, server_url, secret_key, timeout=60):
        self.server_url = server_url.rstrip('/')
        self.secret_key = secret_key
        self.timeout = timeout

    def gen_headers(self):
        payload = {
            'exp': int(time.time()) + 300,
            'is_internal': True,
        }
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return {"Authorization": "Token %s" % token}

    def save_face(self, repo_id, image, filename, replace=False):
        logger.info('save_face, repo_id=%s, filename=%s, replace=%s', repo_id, filename, replace)
        url = f'{self.server_url}/api/v2.1/internal/repos/{repo_id}/save-face/'
        headers = self.gen_headers()
        files = {
            'image': (filename, io.BytesIO(image), 'image/jpeg')
        }
        data = {
            'filename': filename,
            'replace': str(replace).lower(),
        }
        response = requests.post(url, files=files, data=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    def create_sdoc(self, draft, token):
        url = f'{self.server_url}/api/v2.1/ai/chat/sdoc-create/'
        response = requests.post(url, json=draft,
                                 headers={'Authorization': 'Token %s' % token},
                                 timeout=self.timeout)
        if 400 <= response.status_code < 500:
            return {'type': 'sdoc', 'status': 'failed', 'error_code': 'create_failed'}
        response.raise_for_status()
        return response.json()
