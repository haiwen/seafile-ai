import logging

from flask import Flask, request

from common.auth import is_valid_token
from common.http import error_response, parse_bool
from face_embedding.settings import settings

logger = logging.getLogger(__name__)
flask_app = Flask(__name__)


def check_auth_token(req):
    return is_valid_token(req.headers.get('Authorization', ''), settings.SECRET_KEY)


@flask_app.route('/api/v1/face-embeddings/', methods=['POST'])
def face_embeddings():
    is_valid = check_auth_token(request)
    if not is_valid:
        return error_response('Permission denied', 403)

    try:
        data = request.form
    except Exception as e:
        logger.exception(e)
        return error_response('Bad request.', 400)

    need_face = parse_bool(data.get('need_face', False))
    file = request.files.get('file')

    if not file:
        return error_response('file invalid.', 400)

    try:
        faces = flask_app.app.face_embedding_manager.face_embedding(file.read(), need_face)
    except Exception as e:
        logger.exception(e)
        return error_response('Internal server error.', 500)

    return {'faces': faces}, 200
