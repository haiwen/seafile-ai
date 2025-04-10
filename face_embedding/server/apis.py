import logging
import jwt

from flask import Flask, request

from face_embedding import config

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


@flask_app.route('/api/v1/face-embeddings/', methods=['POST'])
def face_embeddings():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = request.form
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    need_face = data.get('need_face', False)
    file = request.files.get('file')

    if not file:
        return {'error_msg': 'file invalid.'}, 400

    try:
        faces = flask_app.app.face_embedding_manager.face_embedding(file.read(), need_face)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error.'}, 500

    return {'faces': faces}, 200
