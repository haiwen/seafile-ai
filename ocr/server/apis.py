import logging
import jwt
import json

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

    if not request.data:
        data = {}
    else:
        try:
            data = json.loads(request.data)
        except Exception as e:
            logger.exception(e)
            return {'error_msg': 'Bad request'}, 400

    path = data.get('path')
    download_token = data.get('download_token')
    file = request.files.get('file')

    if not (file or (path and download_token)):
        missing_fields = []
        if not file:
            missing_fields.append('file')
        if not path:
            missing_fields.append('path')
        if not download_token:
            missing_fields.append('download_token')
        return {'error_msg': f"Invalid or missing parameters: {', '.join(missing_fields)}"}, 400

    try:
        ocr_result = flask_app.app.doc_ocr_manager.doc_ocr(path, download_token, file)
    except Exception as e:
        logger.error(e)
        return {'error_msg': 'Internet server error'}, 500

    return {'ocr_result': ocr_result}, 200
