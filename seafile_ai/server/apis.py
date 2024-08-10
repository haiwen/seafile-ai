import logging
import jwt
import json

from flask import Flask, request
from seafile_ai import config


logger = logging.getLogger(__name__)
flask_app = Flask(__name__)


def check_auth_token(req):
    auth = req.headers.get('Authorization', '').split()
    if not auth or auth[0].lower() != 'token' or len(auth) != 2:
        return False

    token = auth[1]
    if not token:
        return False

    private_key = config.SECRET_KEY
    try:
        jwt.decode(token, private_key, algorithms=['HS256'])
    except (jwt.ExpiredSignatureError, jwt.InvalidSignatureError) as e:
        return False

    return True


@flask_app.route('/api/v1/update-docs-summary', methods=['POST'])
def library_sdoc_indexes():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    repo_id = data.get('repo_id')
    files_info_list = data.get('files_info_list')

    if not repo_id:
        return {'error_msg': 'repo_id invalid.'}, 400
    if not files_info_list or not isinstance(files_info_list, list):
        return {'error_msg': 'files_info_list should be a non-empty list.'}, 400

    try:
        task_status = flask_app.app.metadata_ai_server.update_docs_summary(repo_id, files_info_list)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error.'}, 500

    return task_status, 200
