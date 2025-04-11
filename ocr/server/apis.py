import logging
import jwt
import os

from flask import Flask, request

from ocr import config

logger = logging.getLogger(__name__)
flask_app = Flask(__name__)


def check_auth_token(req):
    auth = req.headers.get('Authorization', '').split()
    if not auth or auth[0].lower() != 'token' or len(auth) != 2:
        return False

    token = auth[1]
    if not token:
        return False

    private_key = os.getenv('OCR_SERVICE_KEY') or config.SECRET_KEY
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

    file = request.files.get('file')

    if not file:
        return {'error_msg': 'file invalid.'}, 400

    try:
        ocr_result = flask_app.app.doc_ocr_manager.doc_ocr(file.read())
    except Exception as e:
        logger.error(e)
        return {'error_msg': 'Internet server error'}, 500

    return {'ocr_result': ocr_result}, 200
