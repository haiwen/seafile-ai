import logging
import requests, jwt, time

from seafile_ai.config import METADATA_SERVER_URL, SECRET_KEY

logger = logging.getLogger(__name__)



def parse_response(response):
    if response.status_code >= 400 or response.status_code < 200:
        raise ConnectionError(response.status_code, response.text)
    else:
        try:
            return response.json()
        except:
            pass


class MetadataServerAPI:
    def __init__(self, user, timeout=60):
        self.user = user
        self.timeout = timeout
        self.secret_key = SECRET_KEY
        self.server_url = METADATA_SERVER_URL

    def gen_headers(self, base_id):
        payload = {
            'exp': int(time.time()) + 3600,
            'base_id': base_id,
            'user': self.user
        }
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return {"Authorization": "Bearer %s" % token}

    # metadata
    def get_metadata(self, base_id):
        logger.info('get metadata, base_id=%s', base_id)
        headers = self.gen_headers(base_id)
        url = f'{METADATA_SERVER_URL}/api/v1/base/{base_id}/metadata'
        response = requests.get(url, headers=headers, timeout=self.timeout)
        return parse_response(response)

    # base
    def create_base(self, base_id):
        logger.info('create base, base_id=%s', base_id)
        headers = self.gen_headers(base_id)
        url = f'{self.server_url}/api/v1/base/{base_id}'
        response = requests.post(url, headers=headers, timeout=self.timeout)
        return parse_response(response)

    def delete_base(self, base_id):
        logger.info('delete base, base_id=%s', base_id)
        headers = self.gen_headers(base_id)
        url = f'{self.server_url}/api/v1/base/{base_id}'
        response = requests.delete(url, headers=headers, timeout=self.timeout)

        if response.status_code == 404:
            return {'success': True}
        return parse_response(response)

    # table 
    def create_table(self, base_id, table_name):
        logger.info('create table, base_id=%s, table_name=%s', base_id, table_name)
        headers = self.gen_headers(base_id)
        url = f'{METADATA_SERVER_URL}/api/v1/base/{base_id}/tables'
        data = {
            'name': table_name,
        }
        response = requests.post(url, json=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    # row
    def insert_rows(self, base_id, table_id, rows):
        logger.info('insert rows, base_id=%s, table_id=%s, row_count=%d', base_id, table_id, len(rows))
        headers = self.gen_headers(base_id)
        url = f'{self.server_url}/api/v1/base/{base_id}/rows'
        data = {
                'table_id': table_id,
                'rows': rows
            }
        response = requests.post(url, json=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    def update_rows(self, base_id, table_id, rows):
        logger.info('update rows, base_id=%s, table_id=%s, row_count=%d', base_id, table_id, len(rows))
        headers = self.gen_headers(base_id)
        url = f'{self.server_url}/api/v1/base/{base_id}/rows'
        data = {
                'table_id': table_id,
                'rows': rows
            }
        response = requests.put(url, json=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    def delete_rows(self, base_id, table_id, row_ids):
        logger.info('delete rows, base_id=%s, table_id=%s, row_count=%d', base_id, table_id, len(row_ids))
        headers = self.gen_headers(base_id)
        url = f'{self.server_url}/api/v1/base/{base_id}/rows'
        data = {
                'table_id': table_id,
                'row_ids': row_ids
            }
        response = requests.delete(url, json=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    def query_rows(self, base_id, sql, params=[]):
        logger.info('query rows, base_id=%s, sql=%s', base_id, sql)
        headers = self.gen_headers(base_id)
        post_data = {
            'sql': sql
        }

        if params:
            post_data['params'] = params
        url = f'{self.server_url}/api/v1/base/{base_id}/query'
        response = requests.post(url, json=post_data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    # column
    def add_column(self, base_id, table_id, column):
        logger.info('add column, base_id=%s, table_id=%s, column_key=%s', base_id, table_id, column.get('key'))
        headers = self.gen_headers(base_id)
        url = f'{self.server_url}/api/v1/base/{base_id}/columns'
        data = {
            'table_id': table_id,
            'column': column
        }
        response = requests.post(url, json=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    def add_columns(self, base_id, table_id, columns):
        logger.info('add columns, base_id=%s, table_id=%s, column_count=%d', base_id, table_id, len(columns))
        headers = self.gen_headers(base_id)
        url = f'{METADATA_SERVER_URL}/api/v1/base/{base_id}/columns'
        data = {
            'table_id': table_id,
            'columns': columns
        }
        response = requests.post(url, json=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    def list_columns(self, base_id, table_id):
        logger.info('list columns, base_id=%s, table_id=%s', base_id, table_id)
        headers = self.gen_headers(base_id)
        url = f'{METADATA_SERVER_URL}/api/v1/base/{base_id}/columns'
        data = {
            'table_id': table_id
        }
        response = requests.get(url, json=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    def delete_column(self, base_id, table_id, column_key, permanently=False):
        logger.info('delete column, base_id=%s, table_id=%s, column_key=%s', base_id, table_id, column_key)
        headers = self.gen_headers(base_id)
        url = f'{METADATA_SERVER_URL}/api/v1/base/{base_id}/columns'
        data = {
            'table_id': table_id,
            'column_key': column_key,
            'permanently': permanently
        }
        response = requests.delete(url, json=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    def update_column(self, base_id, table_id, column):
        logger.info('update column, base_id=%s, table_id=%s, column_key=%s', base_id, table_id, column.get('key'))
        headers = self.gen_headers(base_id)
        url = f'{METADATA_SERVER_URL}/api/v1/base/{base_id}/columns'
        data = {
            'table_id': table_id,
            'column': column
        }
        response = requests.put(url, json=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    # link
    def insert_link(self, base_id, link_id, table_id, row_id_map):
        logger.info('insert link, base_id=%s, link_id=%s, table_id=%s', base_id, link_id, table_id)
        headers = self.gen_headers(base_id)
        url = f'{METADATA_SERVER_URL}/api/v1/base/{base_id}/links'
        data = {
            'link_id': link_id,
            'table_id': table_id,
            'row_id_map': row_id_map
        }
        response = requests.post(url, json=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

    def update_link(self, base_id, link_id, table_id, row_id_map):
        logger.info('update link, base_id=%s, link_id=%s, table_id=%s', base_id, link_id, table_id)
        headers = self.gen_headers(base_id)
        url = f'{METADATA_SERVER_URL}/api/v1/base/{base_id}/links'
        data = {
            'link_id': link_id,
            'table_id': table_id,
            'row_id_map': row_id_map
        }
        response = requests.put(url, json=data, headers=headers, timeout=self.timeout)
        return parse_response(response)

