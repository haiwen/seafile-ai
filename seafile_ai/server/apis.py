import logging

from PIL import UnidentifiedImageError
from flask import Flask, request
from pathlib import Path

from common.auth import is_valid_token
from common.http import error_response, parse_json_request
from seafile_ai.exceptions import InvalidWritingTypeException, LLMChatCompletionException, FormatNotSupportedException
from seafile_ai.settings import settings
from seafile_ai.utils.constants import LANGUAGE, SUMMARY_SUPPORTED_FILES


logger = logging.getLogger(__name__)
flask_app = Flask(__name__)


def check_auth_token(req):
    return is_valid_token(req.headers.get('Authorization', ''), settings.SECRET_KEY)


def _build_context(data):
    return {
        'username': data.get('username'),
        'org_id': data.get('org_id')
    }


@flask_app.route('/api/v1/generate-summary', methods=['POST'])
def generate_summary():
    is_valid = check_auth_token(request)
    if not is_valid:
        return error_response('Permission denied', 403)

    try:
        data = parse_json_request()
    except Exception as e:
        logger.exception(e)
        return error_response('Bad request.', 400)

    path = data.get('path')
    download_token = data.get('download_token')
    username = data.get('username')

    context = _build_context(data)

    if not path:
        return error_response('path invalid.', 400)
    if not download_token:
        return error_response('download_token invalid.', 400)
    if Path(path).suffix not in SUMMARY_SUPPORTED_FILES:
        return error_response('unsupported file format.', 400)
    if not username:
        return error_response('username invalid.', 400)
    try:
        summary = flask_app.app.text_processing_manager.generate_summary(path, download_token, context)
    except Exception as e:
        logger.exception(e)
        return error_response('Internal server error.', 500)

    return {'summary': summary}, 200


@flask_app.route('/api/v1/image-caption/', methods=['POST'])
def image_caption():
    is_valid = check_auth_token(request)
    if not is_valid:
        return error_response('Permission denied', 403)

    try:
        data = parse_json_request()
    except Exception as e:
        logger.exception(e)
        return error_response('Bad request.', 400)

    path = data.get('path')
    lang = data.get('lang')
    username = data.get('username')
    download_token = data.get('download_token')
    capture_time = data.get('capture_time')
    address = data.get('address')

    if not path:
        return error_response('path invalid.', 400)
    if not lang:
        return error_response('lang invalid.', 400)
    if not download_token:
        return error_response('download_token invalid.', 400)
    if not username:
        return error_response('username invalid.', 400)

    context = _build_context(data)

    try:
        desc = flask_app.app.image_processing_manager.image_caption(path, download_token, lang, context, capture_time, address)
    except UnidentifiedImageError as e:
        logger.exception(e)
        return error_response('file format not supported.', 400)
    except Exception as e:
        logger.exception(e)
        return error_response('Internal server error.', 500)

    return {'desc': desc}, 200


@flask_app.route('/api/v1/generate-file-tags/', methods=['POST'])
def generate_file_tags():
    is_valid = check_auth_token(request)
    if not is_valid:
        return error_response('Permission denied', 403)

    try:
        data = parse_json_request()
    except Exception as e:
        logger.exception(e)
        return error_response('Bad request.', 400)

    path = data.get('path')
    download_token = data.get('download_token')
    file_type = data.get('file_type')
    username = data.get('username')

    context = _build_context(data)

    if not path:
        return error_response('path invalid.', 400)
    if not download_token:
        return error_response('download_token invalid.', 400)
    if not file_type or file_type not in ['image', 'doc']:
        return error_response('file_type invalid.', 400)
    if not username:
        return error_response('username invalid.', 400)

    if file_type == 'image':
        lang = data.get('lang', 'en')
        try:
            tags = flask_app.app.image_processing_manager.image_tags(path, download_token, lang, context)
        except Exception as e:
            logger.exception(e)
            return error_response('Internal server error.', 500)
    else:
        candidate_tags = data.get('candidate_tags', [])

        if not isinstance(candidate_tags, list):
            return error_response('candidate_tags invalid.', 400)

        try:
            tags = flask_app.app.text_processing_manager.doc_tags(path, download_token, candidate_tags, context)
        except Exception as e:
            logger.exception(e)
            return error_response('Internal server error.', 500)

    return {'tags': tags}, 200


@flask_app.route('/api/v1/ocr/', methods=['POST'])
def ocr():
    is_valid = check_auth_token(request)
    if not is_valid:
        return error_response('Permission denied', 403)

    try:
        data = parse_json_request()
    except Exception as e:
        logger.exception(e)
        return error_response('Bad request.', 400)

    file_name = data.get('file_name')
    download_token = data.get('download_token')
    username = data.get('username')

    context = _build_context(data)

    if not file_name:
        return error_response('file_name invalid.', 400)
    if not download_token:
        return error_response('download_token invalid.', 400)
    if not username:
        return error_response('username invalid.', 400)

    try:
        ocr_result = flask_app.app.text_processing_manager.extract_text(file_name, download_token, context)
    except FormatNotSupportedException as e:
        logger.warning(e)
        return error_response('file format not supported.', 400)
    except Exception as e:
        logger.exception(e)
        return error_response('Internal server error.', 500)

    return {'ocr_result': ocr_result}, 200


@flask_app.route('/api/v1/face-embeddings/', methods=['POST'])
def face_embeddings():
    is_valid = check_auth_token(request)
    if not is_valid:
        return error_response('Permission denied', 403)

    try:
        data = parse_json_request()
    except Exception as e:
        logger.exception(e)
        return error_response('Bad request.', 400)

    path = data.get('path')
    download_token = data.get('download_token')
    need_face = data.get('need_face', False)

    if not path:
        return error_response('path invalid.', 400)
    if not download_token:
        return error_response('download_token invalid.', 400)

    try:
        faces = flask_app.app.image_processing_manager.face_embeddings(path, download_token, need_face)
    except Exception as e:
        logger.exception(e)
        return error_response('Internal server error.', 500)

    return {'faces': faces}, 200


@flask_app.route('/api/v1/translate/', methods=['POST'])
def translate():
    is_valid = check_auth_token(request)
    if not is_valid:
        return error_response('Permission denied', 403)

    try:
        data = parse_json_request()
    except Exception as e:
        logger.exception(e)
        return error_response('Bad request.', 400)

    text = data.get('text')
    lang = data.get('lang')
    username = data.get('username')

    if not text:
        return error_response('text invalid.', 400)
    if not lang or lang not in LANGUAGE:
        return error_response('lang invalid.', 400)
    if not username:
        return error_response('username invalid.', 400)

    context = _build_context(data)

    try:
        translation = flask_app.app.text_processing_manager.translate(text, lang, context)
    except Exception as e:
        logger.exception(e)
        return error_response('Internal server error.', 500)

    return {'translation': translation}, 200


@flask_app.route('/api/v1/writing-assistant/', methods=['POST'])
def writing_assistant():
    is_valid = check_auth_token(request)
    if not is_valid:
        return error_response('Permission denied', 403)

    try:
        data = parse_json_request()
    except Exception as e:
        logger.exception(e)
        return error_response('Bad request.', 400)

    text = data.get('text')
    writing_type = data.get('writing_type')
    custom_prompt = data.get('custom_prompt')
    username = data.get('username')

    if not text:
        return error_response('text invalid.', 400)
    if not custom_prompt and not writing_type:
        return error_response('writing_type invalid.', 400)
    if not username:
        return error_response('username invalid.', 400)

    context = _build_context(data)

    try:
        content = flask_app.app.text_processing_manager.writing_assistant(text, custom_prompt, writing_type, context)
    except InvalidWritingTypeException as e:
        logger.warning(e)
        return error_response('writing type invalid.', 400)
    except LLMChatCompletionException as e:
        logger.warning(e)
        return error_response('openai server error.', 500)
    except Exception as e:
        logger.exception(e)
        return error_response('Internal server error.', 500)

    return {'content': content}, 200
