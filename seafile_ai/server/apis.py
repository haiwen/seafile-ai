import json
import logging
import jwt

from flask import Flask, request
from flask_caching import Cache
from seafile_ai import config
from seafile_ai.utils import ImageSizeException

logger = logging.getLogger(__name__)
flask_app = Flask(__name__)
cache = Cache(flask_app, config={'CACHE_TYPE': 'SimpleCache'})


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


@flask_app.route('/api/v1/ocr/', methods=['POST'])
def ocr():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request'}, 400

    repo_id = data.get('repo_id')
    path = data.get('path')
    obj_id = data.get('obj_id')

    if not repo_id:
        return {'error_msg': 'repo_id invalid'}, 400
    if not path:
        return {'error_msg': 'path invalid'}, 400
    if not obj_id:
        return {'error_msg': 'obj_id invalid'}, 400

    try:
        ocr_result = flask_app.app.image_processing_manager.get_box_and_text(repo_id, path, obj_id)
    except ImageSizeException as e:
        logger.error(e)
        return {'error_msg': 'Image too big'}, 400
    except Exception as e:
        logger.error(e)
        return {'error_msg': 'Internet server error'}, 500

    return {'ocr_result': ocr_result}, 200
