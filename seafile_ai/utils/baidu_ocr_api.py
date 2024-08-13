import requests

from seafile_ai.server.apis import cache
from seafile_ai.utils import OcrErrorException
from seafile_ai.utils.seafile_api import parse_response


class BaiduOCRAPI:

    def __init__(self, url, api_key, secret_key):
        self.data_logger = None
        self.api_key = api_key
        self.secret_key = secret_key
        self.access_token_cache_key = 'baidu_ocr_access_token'
        self.timeout = 30
        self.max_length = 4097
        self.base_url = url.rstrip('/')
        self.headers = {
            'content-type': 'application/x-www-form-urlencoded'
        }

    def init(self, data_logger):
        self.data_logger = data_logger

    def get_baidu_ocr_access_token(self):
        access_token = cache.get(self.access_token_cache_key)
        if access_token:
            return access_token

        params = {
            'grant_type': 'client_credentials',
            'client_id': self.api_key,
            'client_secret': self.secret_key,
        }

        url = self.base_url + '/oauth/2.0/token'
        response = requests.get(url, params=params, timeout=self.timeout)
        resp = response.json()
        expires_in = resp.get('expires_in', 24 * 3600)
        access_token = resp.get('access_token')
        cache.set(self.access_token_cache_key, access_token, expires_in)
        return access_token

    def baidu_ocr_accurate(self, encode_img):
        data = {
            'image': encode_img,
            'recognize_granularity': 'small',
        }
        url = self.base_url + '/rest/2.0/ocr/v1/accurate'
        access_token = self.get_baidu_ocr_access_token()
        params = {
            'access_token': access_token
        }
        response = requests.post(url, data=data, params=params, headers=self.headers, timeout=self.timeout)
        res = parse_response(response)

        if 'error_msg' in list(res.keys()):
            raise OcrErrorException('baidu ocr error:' + str(res))
        return res
