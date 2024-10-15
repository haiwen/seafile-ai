import logging
import jwt
import json

from flask import Flask, request

from image_embedding import config

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


@flask_app.route('/api/v1/face-embeddings', methods=['POST'])
def face_embeddings():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    repo_id = data.get('repo_id')
    obj_ids = data.get('obj_ids')

    if not repo_id:
        return {'error_msg': 'repo_id invalid.'}, 400
    if not obj_ids or not isinstance(obj_ids, list):
        return {'error_msg': 'obj_ids invalid.'}, 400

    try:
        embeddings = flask_app.app.face_embedding_manager.face_embedding(repo_id, obj_ids)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error.'}, 500

    return {'data': embeddings}, 200
