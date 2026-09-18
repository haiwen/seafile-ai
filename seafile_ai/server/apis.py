import logging
import jwt
import json

from PIL import UnidentifiedImageError
from flask import Flask, Response, request, stream_with_context
from pathlib import Path

from seafile_ai import config
from seafile_ai.server.review_plan_binding import (
    encode_review_plan_binding, review_plan_binding_matches,
)
from seafile_ai.server.sdoc_review_utils import build_sdoc_ai_context
from seafile_ai.text_processing.text_processing_manager import (
    ReviewModelOutputTruncatedError, ReviewModelResponseInvalidError,
    ReviewPayloadTooLargeError, ReviewScopeAmbiguousError,
)
from seafile_ai.utils import InvalidWritingTypeException, LLMChatCompletionException, FormatNotSupportedException
from seafile_ai.utils.constants import LANGUAGE, SUMMARY_SUPPORTED_FILES
from seafile_ai.repo_metadata.constants import TAGS_TABLE
from seafile_ai.repo_metadata.metadata_server_api import MetadataServerAPI


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


@flask_app.route('/api/v1/get-ai-reply', methods=['POST'])
def get_ai_reply():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Bad request.'}, 400

    message = data.get('query')
    attachments = data.get('attachments', [])
    session_uuid = data.get('session_uuid')
    repo_id = data.get('repo_id')
    repo_name = data.get('repo_name')
    llm_model = data.get('llm_model')
    repo_prompt = data.get('repo_prompt', '')
    scenario = data.get('scenario', 'chat')

    if not message:
        return {'error_msg': 'question invalid.'}, 400
    if not repo_id:
        return {'error_msg': 'repo_id invalid.'}, 400
    if not isinstance(attachments, list):
        return {'error_msg': 'attachments invalid.'}, 400

    context = {
        'session_uuid': session_uuid,
        'repo_id': repo_id,
        'repo_name': repo_name,
        'repo_prompt': repo_prompt,
        'scenario': scenario,
    }

    return Response(
        stream_with_context(flask_app.app.streaming_chat(message, attachments, context, llm_model)),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


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
    repo_id = data.get('repo_id')
    obj_id = data.get('obj_id')
    scenario = data.get('scenario', 'summary')

    context = {
        'repo_id': repo_id,
        'scenario': scenario,
    }

    if not repo_id:
        return {'error_msg': 'repo_id invalid.'}, 400
    if not obj_id:
        return {'error_msg': 'obj_id invalid.'}, 400
    if not path:
        return {'error_msg': 'path invalid.'}, 400
    if Path(path).suffix.lower() not in SUMMARY_SUPPORTED_FILES:
        return {'error_msg': 'unsupported file format.'}, 400
    try:
        summary = flask_app.app.text_processing_manager.generate_summary(repo_id, obj_id, path, context)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internal server error.'}, 500

    return {'summary': summary}, 200


@flask_app.route('/api/v1/embeddings/batch', methods=['POST'])
def batch_generate_embeddings():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Bad request.'}, 400

    contents = data.get('contents')
    if not isinstance(contents, list) or not contents or len(contents) > 50:
        return {'error_msg': 'contents invalid.'}, 400
    if not all(isinstance(content, str) and content for content in contents):
        return {'error_msg': 'contents invalid.'}, 400
    if not flask_app.app.embedding_api:
        return {'error_msg': 'Embedding model or Seasearch is not configured in seafile-ai. '}, 503

    context = {
        'username': data.get('username'),
        'org_id': data.get('org_id'),
        'scenario': data.get('scenario', 'summary_index'),
    }
    try:
        embeddings = flask_app.app.embedding_api.batch_generate(contents, context)
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Internal server error.'}, 500

    return {
        'model': flask_app.app.embedding_api.model_id,
        'embeddings': embeddings,
    }, 200


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

    obj_id = data.get('obj_id')
    repo_id = data.get('repo_id')
    lang = data.get('lang')
    capture_time = data.get('capture_time')
    address = data.get('address')
    scenario = data.get('scenario', 'image-caption')

    
    if not lang:
        return {'error_msg': 'lang invalid.'}, 400
    
    if not obj_id:
        return {'error_msg': 'obj_id invalid.'}, 400
    
    if not repo_id:
        return {'error_msg': 'repo_id invalid.'}, 400

    context = {
        'repo_id': repo_id,
        'scenario': scenario,
    }

    try:
        desc = flask_app.app.image_processing_manager.image_caption(repo_id, obj_id, lang, context, capture_time, address)
    except UnidentifiedImageError as e:
        logger.exception(e)
        return {'error_msg': 'file format not supported.'}, 400
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internal server error.'}, 500

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
    obj_id = data.get('obj_id')
    repo_id = data.get('repo_id')
    file_type = data.get('file_type')
    scenario = data.get('scenario', 'file-tags')

    context = {
        'repo_id': repo_id,
        'scenario': scenario,
    }
    if not path:
        return {'error_msg': 'path invalid.'}, 400
    if not obj_id:
        return {'error_msg': 'obj_id invalid.'}, 400
    if not repo_id:
        return {'error_msg': 'repo_id invalid.'}, 400
    if not file_type or file_type not in ['image', 'doc']:
        return {'error_msg': 'file_type invalid.'}, 400
    try:
        metadata_server_api = MetadataServerAPI('seafile-ai')
        sql = f'SELECT `{TAGS_TABLE.columns.id.name}`, `{TAGS_TABLE.columns.name.name}`, `{TAGS_TABLE.columns.color.name}` FROM `{TAGS_TABLE.name}`'
        rows = metadata_server_api.query_rows(repo_id, sql).get('results', [])
        tag_id_data_map = {
            row[TAGS_TABLE.columns.id.name]: {
                'id': row[TAGS_TABLE.columns.id.name],
                'name': row[TAGS_TABLE.columns.name.name].strip(),
                'color': row.get(TAGS_TABLE.columns.color.name, ''),
            }
            for row in rows
            if row.get(TAGS_TABLE.columns.id.name) and isinstance(row.get(TAGS_TABLE.columns.name.name), str)
            and row[TAGS_TABLE.columns.name.name].strip()
        }
    except Exception:
        logger.exception('Failed to get metadata tags, repo_id=%s', repo_id)
        return {'tags': []}, 200

    if not tag_id_data_map:
        return {'tags': []}, 200

    candidate_tags = [tag['name'] for tag in tag_id_data_map.values()]

    if file_type == 'image':
        try:
            tags = flask_app.app.image_processing_manager.image_tags(repo_id, obj_id, candidate_tags, context)
        except Exception as e:
            logger.exception(e)
            return {'error_msg': 'Internal server error.'}, 500
    else:
        try:
            tags = flask_app.app.text_processing_manager.doc_tags(repo_id, obj_id, path, candidate_tags, context)
        except Exception as e:
            logger.exception(e)
            return {'error_msg': 'Internal server error.'}, 500

    candidate_tags_by_name = {tag['name']: tag for tag in tag_id_data_map.values()}
    normalized_tags = []
    if isinstance(tags, list):
        for tag in tags:
            if not isinstance(tag, str):
                continue
            candidate_tag = candidate_tags_by_name.get(tag)
            if candidate_tag and candidate_tag not in normalized_tags:
                normalized_tags.append(candidate_tag)
                if len(normalized_tags) == 10:
                    break

    return {'tags': normalized_tags}, 200


@flask_app.route('/api/v1/ocr/', methods=['POST'])
def ocr():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    obj_id = data.get('obj_id')
    repo_id = data.get('repo_id')
    file_name = data.get('file_name')
    scenario = data.get('scenario', 'ocr')

    context = {
        'repo_id': repo_id,
        'scenario': scenario,
    }

    if not file_name:
        return {'error_msg': 'file_name invalid.'}, 400
    if not obj_id:
        return {'error_msg': 'obj_id invalid.'}, 400
    if not repo_id:
        return {'error_msg': 'repo_id invalid.'}, 400

    try:
        ocr_result = flask_app.app.text_processing_manager.extract_text(repo_id, obj_id,file_name, context)
    except FormatNotSupportedException as e:
        logger.exception(e)
        return {'error_msg': 'file format not supported.'}, 400
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internal server error.'}, 500

    return {'ocr_result': ocr_result}, 200

# Face recognition is no longer available.
# @flask_app.route('/api/v1/face-batch-embeddings/', methods=['POST'])
def face_batch_embeddings():
    logger.info('face-batch-embeddings API called')
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
    need_classify = data.get('need_classify', False)

    try:
        flask_app.app.face_recognition_manager.face_embeddings_by_obj_ids(repo_id, obj_ids, need_classify)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internal server error.'}, 500

    return {'success': True}, 200


# Face recognition is no longer available.
# @flask_app.route('/api/v1/face-cluster/', methods=['POST'])
def face_cluster():
    logger.info('face-cluster API called')
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    repo_id = data.get('repo_id')

    if not repo_id:
        return {'error_msg': 'repo_id invalid.'}, 400

    try:
        flask_app.app.face_recognition_manager.update_face_cluster(repo_id)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internal server error.'}, 500

    return {'success': True}, 200

# Face recognition is no longer available.
# @flask_app.route('/api/v1/update-people-cover-photo/', methods=['POST'])
def update_photo_cover():
    logger.info('update-people-cover-photo API called')
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    repo_id = data.get('repo_id')
    people_id = data.get('people_id')
    obj_id = data.get('obj_id')

    try:
        flask_app.app.face_recognition_manager.update_people_cover_photo(repo_id, people_id, obj_id)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internal server error.'}, 500

    return {'success': True}, 200

# Face recognition is no longer available.
# @flask_app.route('/api/v1/recognize-faces/', methods=['POST'])
def recognize_faces():
    logger.info('recognize-faces API called')
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
    

    try:
        flask_app.app.face_recognition_manager.recognize_faces_by_obj_ids(repo_id, obj_ids)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internal server error.'}, 500

    return {'success': True}, 200



@flask_app.route('/api/v1/translate/', methods=['POST'])
def translate():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    text = data.get('text')
    lang = data.get('lang')
    repo_id = data.get('repo_id')
    scenario = data.get('scenario', 'translate')

    if not text:
        return {'error_msg': 'text invalid.'}, 400
    if not lang or lang not in LANGUAGE:
        return {'error_msg': 'lang invalid.'}, 400
    
    context = { 
        'repo_id': repo_id,
        'scenario': scenario,
    }

    try:
        translation = flask_app.app.text_processing_manager.translate(text, lang, context)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internal server error.'}, 500

    return {'translation': translation}, 200


@flask_app.route('/api/v1/writing-assistant/', methods=['POST'])
def writing_assistant():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    text = data.get('text')
    writing_type = data.get('writing_type')
    custom_prompt = data.get('custom_prompt')
    repo_id = data.get('repo_id')
    scenario = data.get('scenario', 'writing-assistant')

    if not text:
        return {'error_msg': 'text invalid.'}, 400
    if not custom_prompt and not writing_type:
        return {'error_msg': 'writing_type invalid.'}, 400

    context = {
        'repo_id': repo_id,
        'scenario': scenario,
    }

    try:
        content = flask_app.app.text_processing_manager.writing_assistant(text, custom_prompt, writing_type, context)
    except InvalidWritingTypeException as e:
        logger.warning(e)
        return {'error_msg': 'writing type invalid.'}, 400
    except LLMChatCompletionException as e:
        logger.warning(e)
        return {'error_msg': 'openai server error.'}, 500
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internal server error.'}, 500

    return {'content': content}, 200


@flask_app.route('/api/v1/search-icons/', methods=['POST'])
def search_icons():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    if not isinstance(data, dict):
        return {'error_msg': 'Bad request.'}, 400

    query = data.get('query')
    count = data.get('count', 15)
    username = data.get('username')
    org_id = data.get('org_id')

    if not query:
        return {'error_msg': 'query invalid.'}, 400
    if not username:
        return {'error_msg': 'username invalid.'}, 400

    try:
        count = int(count)
        if count <= 0 or count > 50:
            count = 15
    except (ValueError, TypeError):
        count = 15

    context = {
        'username': username,
        'org_id': org_id,
        'log_data': False,
    }

    try:
        icons = flask_app.app.text_processing_manager.search_icons(query, count, context)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internal server error.'}, 500

    return {'icons': icons}, 200


@flask_app.route('/api/v1/sdoc-review/', methods=['POST'])
def sdoc_review():
    if not check_auth_token(request):
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Bad request.'}, 400

    prompt = data.get('prompt')
    document_context = data.get('document_context')
    username = data.get('username')
    if not isinstance(prompt, str) or not prompt.strip():
        return {'error_msg': 'prompt invalid.'}, 400
    if not isinstance(document_context, dict):
        return {'error_msg': 'document_context invalid.'}, 400
    if not isinstance(document_context.get('blocks'), list):
        return {'error_msg': 'document_context.blocks invalid.'}, 400
    if not username:
        return {'error_msg': 'username invalid.'}, 400

    context = build_sdoc_ai_context(data, username)
    try:
        review = flask_app.app.text_processing_manager.sdoc_review(prompt, document_context, context)
    except ReviewPayloadTooLargeError as error:
        return {'error_code': 'review_payload_too_large', 'error_msg': str(error)}, 413
    except ReviewModelOutputTruncatedError as error:
        return {'error_code': 'model_output_truncated', 'error_msg': str(error)}, 502
    except ReviewModelResponseInvalidError as error:
        return {'error_code': 'invalid_model_response', 'error_msg': str(error)}, 502
    except ValueError as error:
        return {'error_msg': str(error)}, 400
    except LLMChatCompletionException as error:
        logger.warning(error)
        return {'error_msg': 'openai server error.'}, 500
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Internal server error.'}, 500

    return {'review': review}, 200


@flask_app.route('/api/v1/sdoc-review-plan/', methods=['POST'])
def sdoc_review_plan():
    if not check_auth_token(request):
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Bad request.'}, 400

    prompt = data.get('prompt')
    document_context = data.get('document_context')
    review_task_id = data.get('review_task_id')
    generation_attempt_id = data.get('generation_attempt_id')
    username = data.get('username')
    if not isinstance(prompt, str) or not prompt.strip():
        return {'error_msg': 'prompt invalid.'}, 400
    if not isinstance(document_context, dict):
        return {'error_msg': 'document_context invalid.'}, 400
    if not isinstance(document_context.get('blocks'), list):
        return {'error_msg': 'document_context.blocks invalid.'}, 400
    if not username:
        return {'error_msg': 'username invalid.'}, 400
    if not isinstance(review_task_id, str) or not review_task_id:
        return {'error_msg': 'review_task_id invalid.'}, 400
    if not isinstance(generation_attempt_id, str) or not generation_attempt_id:
        return {'error_msg': 'generation_attempt_id invalid.'}, 400

    context = build_sdoc_ai_context(data, username)
    try:
        plan = flask_app.app.text_processing_manager.sdoc_review_plan(prompt, document_context, context)
    except ReviewPayloadTooLargeError as error:
        return {'error_code': 'review_payload_too_large', 'error_msg': str(error)}, 413
    except ValueError as error:
        return {'error_msg': str(error)}, 400
    except LLMChatCompletionException as error:
        logger.warning(error)
        return {'error_msg': 'openai server error.'}, 500
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Internal server error.'}, 500

    plan = dict(plan)
    plan['plan_token'] = encode_review_plan_binding(
        config.SECRET_KEY, prompt, document_context, plan,
        review_task_id, generation_attempt_id)
    return {'plan': plan}, 200


@flask_app.route('/api/v1/sdoc-review-scope/', methods=['POST'])
def sdoc_review_scope():
    if not check_auth_token(request):
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Bad request.'}, 400

    prompt = data.get('prompt')
    document_context = data.get('document_context')
    if not isinstance(prompt, str) or not prompt.strip():
        return {'error_msg': 'prompt invalid.'}, 400
    if not isinstance(document_context, dict) or not isinstance(document_context.get('blocks'), list):
        return {'error_msg': 'document_context invalid.'}, 400

    try:
        scope = flask_app.app.text_processing_manager.sdoc_review_scope(prompt, document_context)
    except ReviewScopeAmbiguousError as error:
        return {
            'error_code': 'scope_ambiguous',
            'candidates': error.candidates,
        }, 409
    except ValueError as error:
        return {'error_msg': str(error)}, 400
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Internal server error.'}, 500

    return {'scope': scope}, 200


@flask_app.route('/api/v1/sdoc-review-chunk/', methods=['POST'])
def sdoc_review_chunk():
    if not check_auth_token(request):
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Bad request.'}, 400

    prompt = data.get('prompt')
    document_context = data.get('document_context')
    plan_token = data.get('plan_token')
    review_task_id = data.get('review_task_id')
    generation_attempt_id = data.get('generation_attempt_id')
    if 'brief' not in data:
        return {'error_msg': 'brief invalid.'}, 400
    brief = data.get('brief')
    chunk_index = data.get('chunk_index')
    username = data.get('username')
    if not isinstance(prompt, str) or not prompt.strip():
        return {'error_msg': 'prompt invalid.'}, 400
    if not isinstance(document_context, dict):
        return {'error_msg': 'document_context invalid.'}, 400
    if not isinstance(document_context.get('blocks'), list):
        return {'error_msg': 'document_context.blocks invalid.'}, 400
    if not isinstance(chunk_index, int):
        return {'error_msg': 'chunk_index invalid.'}, 400
    if not isinstance(plan_token, str) or not plan_token:
        return {'error_msg': 'plan_token invalid.'}, 400
    if not isinstance(review_task_id, str) or not review_task_id:
        return {'error_msg': 'review_task_id invalid.'}, 400
    if not isinstance(generation_attempt_id, str) or not generation_attempt_id:
        return {'error_msg': 'generation_attempt_id invalid.'}, 400
    if not username:
        return {'error_msg': 'username invalid.'}, 400

    context = build_sdoc_ai_context(data, username)
    try:
        _blocks, _lists, chunks = flask_app.app.text_processing_manager.sdoc_review_chunk_manifest(
            prompt, document_context)
        if not review_plan_binding_matches(
                plan_token, config.SECRET_KEY, prompt, document_context, brief,
                [{'chunk_index': index, 'block_ids': [block.get('block_id') for block in chunk]}
                 for index, chunk in enumerate(chunks)],
                review_task_id, generation_attempt_id):
            return {'error_msg': 'review plan does not match the request.'}, 409
        result = flask_app.app.text_processing_manager.sdoc_review_chunk(
            prompt, document_context, brief, chunk_index, context)
    except ReviewPayloadTooLargeError as error:
        return {'error_code': 'review_payload_too_large', 'error_msg': str(error)}, 413
    except ReviewModelOutputTruncatedError as error:
        return {'error_code': 'model_output_truncated', 'error_msg': str(error)}, 502
    except ReviewModelResponseInvalidError as error:
        return {'error_code': 'invalid_model_response', 'error_msg': str(error)}, 502
    except ValueError as error:
        return {'error_msg': str(error)}, 400
    except LLMChatCompletionException as error:
        logger.warning(error)
        return {'error_msg': 'openai server error.'}, 500
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Internal server error.'}, 500

    return result, 200


@flask_app.route('/api/v1/sdoc-analyze/', methods=['POST'])
def sdoc_analyze():
    if not check_auth_token(request):
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Bad request.'}, 400

    prompt = data.get('prompt')
    document_context = data.get('document_context')
    username = data.get('username')
    if not isinstance(prompt, str) or not prompt.strip():
        return {'error_msg': 'prompt invalid.'}, 400
    if not isinstance(document_context, dict):
        return {'error_msg': 'document_context invalid.'}, 400
    if not username:
        return {'error_msg': 'username invalid.'}, 400

    context = build_sdoc_ai_context(data, username)
    try:
        analysis = flask_app.app.text_processing_manager.sdoc_analyze(prompt, document_context, context)
    except ValueError as error:
        return {'error_msg': str(error)}, 400
    except LLMChatCompletionException as error:
        logger.warning(error)
        return {'error_msg': 'openai server error.'}, 500
    except Exception as error:
        logger.exception(error)
        return {'error_msg': 'Internal server error.'}, 500

    return {'analysis': analysis}, 200
