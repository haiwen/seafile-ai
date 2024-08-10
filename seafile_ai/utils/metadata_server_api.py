import requests, jwt, time


def parse_response(response):
    if response.status_code >= 400 or response.status_code < 200:
        raise ConnectionError(response.status_code, response.text)
    else:
        try:
            return response.json()
        except:
            pass


class MetadataServerAPI:
    def __init__(self, user, server_url, secret_key, timeout=30):
        self.user = user
        self.timeout = timeout
        self.server_url = server_url
        self.secret_key = secret_key

    def gen_headers(self, base_id):
        payload = {
            'exp': int(time.time()) + 3600,
            'base_id': base_id,
            'user': self.user
        }
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return {"Authorization": "Bearer %s" % token}

    def update_rows(self, base_id, table_id, rows):
        headers = self.gen_headers(base_id)
        url = f'{self.server_url}/api/v1/base/{base_id}/rows'
        data = {
                'table_id': table_id,
                'rows': rows
            }
        response = requests.put(url, json=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    def query_rows(self, base_id, sql, params=[]):
        headers = self.gen_headers(base_id)
        post_data = {
            'sql': sql
        }

        if params:
            post_data['params'] = params
        url = f'{self.server_url}/api/v1/base/{base_id}/query'
        response = requests.post(url, json=post_data, headers=headers, timeout=self.timeout)
        return parse_response(response)
