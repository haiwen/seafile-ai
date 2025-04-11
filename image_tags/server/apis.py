import logging
import jwt
import os

from PIL import UnidentifiedImageError
from flask import Flask, request

from image_tags import config

logger = logging.getLogger(__name__)
flask_app = Flask(__name__)


def check_auth_token(req):
    auth = req.headers.get('Authorization', '').split()
    if not auth or auth[0].lower() != 'token' or len(auth) != 2:
        return False

    token = auth[1]
    if not token:
        return False

    private_key = os.getenv('IMAGE_TAGS_SERVICE_KEY') or config.SECRET_KEY
    try:
        jwt.decode(token, private_key, algorithms=['HS256'])
    except (jwt.ExpiredSignatureError, jwt.InvalidSignatureError) as e:
        return False

    return True


@flask_app.route('/api/v1/image-tags/', methods=['POST'])
def image_tags():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = request.form
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request'}, 400

    file = request.files.get('file')
    lang = data.get('lang') or 'en'

    if not file:
        return {'error_msg': 'file invalid.'}, 400

    try:
        tags = flask_app.app.image_tags_manager.image_tags(file.read(), lang)
    except UnidentifiedImageError as e:
        logger.exception(e)
        return {'error_msg': 'file format not supported.'}, 400
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error'}, 500

    return {'tags': tags}, 200
