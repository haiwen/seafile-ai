import json
import logging
import os
import jwt
import shutil

from flask import request, Flask
from sqlalchemy.orm import scoped_session

from seafile_ai import config
from seafile_ai.db import init_db_session_class
from seafile_ai.index_task.index_task_manager import index_task_manager
from seafile_ai.utils.constant import LIBRARY_SDOC_INDEX
from seafile_ai.utils import get_file_by_token
from seafile_ai.utils.sdoc2md import sdoc2md

logger = logging.getLogger(__name__)
flask_app = Flask(__name__)
Session = scoped_session(init_db_session_class(config))


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


@flask_app.teardown_request
def shutdown_session(error=None):
    Session.remove()


@flask_app.route('/api/v1/library-sdoc-indexes/', methods=['POST'])
def library_sdoc_indexes():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    associate_id = data.get('repo_id')
    last_modify = data.get('last_modify')
    sdoc_info_list = data.get('sdoc_info_list')

    if not associate_id:
        return {'error_msg': 'associate_id invalid.'}, 400

    db_session = Session()

    try:
        index = flask_app.app.index_manager.get_library_sdoc_index_by_associate_id(associate_id, db_session)
    except Exception as e:
        logger.error(e)
        return {'error_msg': 'Internet server error.'}, 500

    if index:
        return {'error_msg': 'Index has exists.'}, 400

    task = index_task_manager.get_pending_or_running_task(associate_id)

    if task:
        return {'task_id': task.id}, 200

    flask_app.app.index_manager.create_library_sdoc_index_db(associate_id, last_modify, db_session)

    context = {
        'associate_id': associate_id,
        'sdoc_info_list': sdoc_info_list
    }

    task_id = index_task_manager.add_library_sdoc_index_task(context)

    return {'task_id': task_id}, 200


@flask_app.route('/api/v1/similarity-search-in-library/', methods=['POST'])
def similarity_search_in_library():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    query = data.get('query')
    associate_id = data.get('associate_id')
    sdoc_files_info = data.get('sdoc_files_info')

    if not query:
        return {'error_msg': 'query invalid.'}, 400

    if not associate_id:
        return {'error_msg': 'associate_id invalid.'}, 400

    if not sdoc_files_info:
        return {'error_msg': 'sdoc_files_info invalid.'}, 400

    try:
        count = int(data.get('count'))
    except:
        count = 10

    db_session = Session()

    try:
        index = flask_app.app.index_manager.get_library_sdoc_index_by_associate_id(associate_id, db_session)
    except Exception as e:
        logger.error(e)
        return {'error_msg': 'Internet server error.'}, 500

    if not index:
        return {'error_msg': 'Library index not found.'}, 400

    try:
        children_similarity = index_task_manager.search_similar_children_in_library(query, associate_id, sdoc_files_info)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error.'}, 500


    children_list = sorted(children_similarity, key=lambda row: row['distance'], reverse=False)[:count]

    return {'children_list': children_list}, 200


@flask_app.route('/api/v1/question-answering-search-in-library/', methods=['POST'])
def question_answering_search_in_library():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    query = data.get('query')
    associate_id = data.get('associate_id')
    sdoc_files_info = data.get('sdoc_files_info')

    if not query:
        return {'error_msg': 'query invalid.'}, 400

    if not associate_id:
        return {'error_msg': 'associate_id invalid.'}, 400

    if not sdoc_files_info:
        return {'error_msg': 'sdoc_files_info invalid.'}, 400

    try:
        count = int(data.get('count'))
    except:
        count = 10

    db_session = Session()

    try:
        index = flask_app.app.index_manager.get_library_sdoc_index_by_associate_id(associate_id, db_session)
    except Exception as e:
        logger.error(e)
        return {'error_msg': 'Internet server error.'}, 500

    if not index:
        return {'error_msg': 'Library index not found.'}, 400
    try:
        children_similarity = index_task_manager.search_similar_children_in_library(query, associate_id, sdoc_files_info)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error.'}, 500

    children_list = sorted(children_similarity, key=lambda row: row['distance'], reverse=False)[:count]
    first_children_path = children_list[0].get('path')
    content_sdoc = get_file_by_token(first_children_path, (sdoc_files_info.get(first_children_path)).get('download_token'))
    content_md = sdoc2md(json.loads(content_sdoc.decode()))
    prompt = open("static/prompts/question_answering_search.txt").read().format(
    str(content_md), str(query)
    )
    res = flask_app.app.openai_api.chat_completions(prompt, 0)
    print(res)
    return { 'answering_result': res, 'hit_sdoc': [{'path': first_children_path}] }, 200


@flask_app.route('/api/v1/library-sdoc-index/', methods=['PUT', 'DELETE'])
def library_sdoc_index():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    associate_id = data.get('associate_id')

    if not associate_id:
        return {'error_msg': 'associate_id invalid'}, 400

    db_session = Session()

    try:
        index = flask_app.app.index_manager.get_library_sdoc_index_by_associate_id(associate_id, db_session)
    except Exception as e:
        logger.error(e)
        return {'error_msg': 'Internet server error.'}, 500

    if index:
        associate_id = index.associate_id
        embedding_dir = os.path.join(config.INDEX_STORAGE_PATH, LIBRARY_SDOC_INDEX)
        library_sdoc_index_path = os.path.join(embedding_dir, associate_id + '.index')
        library_sdoc_info_path = os.path.join(embedding_dir, associate_id + '.json')
        task = index_task_manager.get_pending_or_running_task(associate_id)

    if request.method == 'DELETE':
        if not index:
            return {'success': True}, 200

        if task:
            return {'error_msg': 'library sdoc index is running'}, 400

        try:
            flask_app.app.index_manager.delete_library_sdoc_index_by_associate_id(associate_id, db_session)
            if os.path.exists(library_sdoc_index_path):
                os.remove(library_sdoc_index_path)
            if os.path.exists(library_sdoc_info_path):
                os.remove(library_sdoc_info_path)
        except Exception as e:
            logger.error(e)
            return {'error_msg': 'Internet server error.'}, 500

        return {'success': True}, 200

    elif request.method == 'PUT':
        sdoc_info_list = data.get('sdoc_info_list')
        last_modify = data.get('last_modify')

        if not sdoc_info_list:
            return {'error_msg': 'sdoc_info_list invalid'}, 400

        if not last_modify:
            return {'error_msg': 'last_modify invalid'}, 400

        if not index:
            return {'error_msg': 'Library sdoc index not found.'}, 404

        if last_modify == index.last_modify:
            return {'error_msg': 'Library sdoc index is latest.'}, 400

        if task:
            return {'task_id': task.id}, 200

        context = {
            'associate_id': associate_id,
            'last_modify': last_modify,
            'sdoc_info_list': sdoc_info_list
        }
        try:
            task_id = index_task_manager.add_update_a_library_sdoc_index_task(context)
        except Exception as e:
            logger.error(e)
            return {'error_msg': 'Internet server error.'}, 500

        return {'task_id': task_id}, 200


@flask_app.route('/api/v1/task-status/', methods=['GET'])
def query_task_status():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    task_id = request.args.get('task_id')
    if not task_id:
        return {'error_msg': 'task_id invalid'}, 400

    task = index_task_manager.query_task(task_id)
    if not task:
        return {'error_msg': 'Task not found'}, 404

    return {'is_finished': task.is_finished()}


@flask_app.route('/api/v1/library-index-state/', methods=['GET'])
def query_library_index_state():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    associate_id = request.args.get('associate_id')
    if not associate_id:
        return {'error_msg': 'associate_id invalid'}, 400

    db_session = Session()

    try:
        index = flask_app.app.index_manager.get_library_sdoc_index_by_associate_id(associate_id, db_session)
    except Exception as e:
        logger.error(e)
        return {'error_msg': 'Internet server error.'}, 500

    if not index:
        return {'state': 'uncreated', 'task_id': ''}

    task = index_task_manager.get_pending_or_running_task(index.associate_id)

    return task and {'state': 'running', 'task_id': task.id} or {'state': 'finished', 'task_id': ''}
