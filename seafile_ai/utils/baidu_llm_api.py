import requests

from seafile_ai.server.apis import cache
from seafile_ai.utils.utils import parse_response


class BaiduLLMAPI:

    def __init__(self, url, api_key, secret_key):
        self.api_key = api_key
        self.secret_key = secret_key
        self.access_token_cache_key = 'baidu_llm_access_token'
        self.timeout = 30
        self.max_length = 4097
        self.base_url = url.rstrip('/')
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

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

    def chat_completions(self, messages, temperature=0.001):
        url = self.base_url + '/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions'
        access_token = self.get_baidu_ocr_access_token()
        params = {
            'access_token': access_token
        }
        json_data = {
            'messages': messages,
            'temperature': temperature
        }
        response = requests.post(url, json=json_data, params=params, headers=self.headers, timeout=self.timeout)
        data = parse_response(response)
        if 'error_msg' in list(data.keys()):
            raise Exception('baidu llm error:' + str(data))
        result = data['result']

        return result
