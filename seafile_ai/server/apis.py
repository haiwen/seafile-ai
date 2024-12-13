import logging
import jwt
import json

from PIL import UnidentifiedImageError
from flask import Flask, request
from pathlib import Path

from seafile_ai import config
from seafile_ai.utils.constants import SUMMARY_SUPPORTED_FILES


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


@flask_app.route('/api/v1/generate-summary', methods=['POST'])
def generate_summary():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    path = data.get('path')
    download_token = data.get('download_token')

    if not path:
        return {'error_msg': 'path invalid.'}, 400
    if not download_token:
        return {'error_msg': 'download_token invalid.'}, 400
    if Path(path).suffix not in SUMMARY_SUPPORTED_FILES:
        return {'error_msg': 'unsupported file format.'}, 400

    try:
        summary = flask_app.app.text_processing_manager.generate_summary(path, download_token)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error.'}, 500

    return {'summary': summary}, 200


@flask_app.route('/api/v1/image-caption/', methods=['POST'])
def image_caption():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    path = data.get('path')
    lang = data.get('lang')
    download_token = data.get('download_token')

    if not path:
        return {'error_msg': 'path invalid.'}, 400
    if not lang:
        return {'error_msg': 'lang invalid.'}, 400
    if not download_token:
        return {'error_msg': 'download_token invalid.'}, 400

    try:
        desc = flask_app.app.image_processing_manager.image_caption(path, download_token, lang)
    except UnidentifiedImageError as e:
        logger.exception(e)
        return {'error_msg': 'file format not supported.'}, 400
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error.'}, 500

    return {'desc': desc}, 200


@flask_app.route('/api/v1/generate-file-tags/', methods=['POST'])
def generate_file_tags():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    path = data.get('path')
    download_token = data.get('download_token')
    file_type = data.get('file_type')

    if not path:
        return {'error_msg': 'path invalid.'}, 400
    if not download_token:
        return {'error_msg': 'download_token invalid.'}, 400
    if not file_type or file_type not in ['image', 'doc']:
        return {'error_msg': 'file_type invalid.'}, 400

    if file_type == 'image':
        lang = data.get('lang', 'en')
        try:
            tags = flask_app.app.image_processing_manager.image_tags(path, download_token, lang)
        except Exception as e:
            logger.exception(e)
            return {'error_msg': 'Internet server error.'}, 500
    else:
        candidate_tags = data.get('candidate_tags', [])

        if not isinstance(candidate_tags, list):
            return {'error_msg': 'candidate_tags invalid.'}, 400

        try:
            tags = flask_app.app.text_processing_manager.doc_tags(path, download_token, candidate_tags)
        except Exception as e:
            logger.exception(e)
            return {'error_msg': 'Internet server error.'}, 500

    return {'tags': tags}, 200
