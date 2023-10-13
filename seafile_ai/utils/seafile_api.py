import json
import logging
import requests
from seafile_ai.utils import gen_headers

logger = logging.getLogger(__name__)

def parse_response(response):
    if response.status_code >= 400:
        raise ConnectionError(response.status_code, response.text)
    else:
        try:
            data = json.loads(response.text)
            return data
        except:
            pass


class SeafileAPI(object):

    def __init__(self, username, seafile_server, timeout=180):
        self.username = username
        self.seafile_server = seafile_server.rstrip('/') if seafile_server else None
        self.timeout = timeout

    def get_library_files(self, repo_id):
        headers = gen_headers(repo_id, self.username)
        url = self.seafile_server + '/api/v2.1/ai/repo/files/?repo_id='+ repo_id + '&from=seafile-ai'
        response = requests.get(url, headers=headers, timeout=self.timeout)
        data = parse_response(response)

        return data
