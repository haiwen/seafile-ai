import json
import logging
import jwt

from flask import request, Flask

from seafile_ai import config
from seafile_ai.index_task.index_task_manager import index_task_manager
from seafile_ai.utils import get_file_by_token
from seafile_ai.utils.sdoc2md import sdoc2md


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

    repo_id = data.get('repo_id')

    if not repo_id:
        return {'error_msg': 'repo_id invalid.'}, 400

    commit_id = flask_app.app.repo_data.get_repo_head_commit(repo_id)

    if not commit_id:
        return {'error_msg': 'repo invalid.'}, 400

    try:
        is_exist = flask_app.app.repo_file_index.check_index(repo_id)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error.'}, 500

    if is_exist:
        return {'error_msg': 'Index exists.'}, 400

    task = index_task_manager.get_pending_or_running_task(repo_id)

    if task:
        return {'task_id': task.id}, 200

    try:
        flask_app.app.index_manager.create_index_repo_db(repo_id)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error.'}, 500

    task_id = index_task_manager.add_library_sdoc_index_task(repo_id, commit_id)

    return {'task_id': task_id}, 200


@flask_app.route('/api/v1/search/', methods=['POST'])
def search():
    is_valid = check_auth_token(request)
    if not is_valid:
        return {'error_msg': 'Permission denied'}, 403

    try:
        data = json.loads(request.data)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Bad request.'}, 400

    query = data.get('query').strip()
    repos = data.get('repos')
    suffixes = data.get('suffixes')
    search_filename_only = data.get('search_filename_only')

    if not query:
        return {'error_msg': 'query invalid.'}, 400

    if not repos:
        return {'error_msg': 'repos invalid.'}, 400

    try:
        count = int(data.get('count'))
    except:
        count = 10

    if search_filename_only:
        results = index_task_manager.keyword_search(query, repos, count, suffixes)
    else:
        results = index_task_manager.hybrid_search(query, repos[0], count)

    return {'results': results}, 200


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
    repo = data.get('repo')
    if not query:
        return {'error_msg': 'query invalid.'}, 400

    if not repo:
        return {'error_msg': 'repo_id invalid.'}, 400
    
    count = int(data.get('count', 10))

    files = index_task_manager.hybrid_search(query, repo, count)
    sdoc_files = [file for file in files if file['fullpath'].endswith('.sdoc')]
    if not sdoc_files:
        return {'answering_result': '', 'hit_files': []}, 200

    first_file_path = sdoc_files[0].get('fullpath')

    repo_id = repo[0]
    origin_repo_id = repo[1]
    origin_path = repo[2]
    if origin_repo_id:
        repo_id = origin_repo_id

    res = flask_app.app.seafile_api.get_file_download_token(repo_id, first_file_path)
    download_token = res.get('download_token')
    content_sdoc = get_file_by_token(first_file_path, download_token)
    content_md = sdoc2md(content_sdoc)

    if origin_path:
        first_file_path = first_file_path.split(origin_path)[-1]

    try:
        prompt = open("static/prompts/question_answering_search.txt").read().format(content_md, query)
        answering_result = flask_app.app.openai_api.chat_completions(prompt, 0)
    except json.JSONDecodeError:
        logger.error('Error decoding JSON.')
        answering_result = 'false'
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error.'}, 500

    return {'answering_result': answering_result, 'hit_files': [first_file_path]}, 200


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

    repo_id = data.get('repo_id')

    if not repo_id:
        return {'error_msg': 'repo_id invalid'}, 400

    try:
        index_repo = flask_app.app.index_manager.get_index_repo_by_repo_id(repo_id)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error.'}, 500

    if request.method == 'DELETE':
        if not index_repo:
            return {'success': True}, 200

        task = index_task_manager.get_pending_or_running_task(repo_id)

        if task:
            return {'error_msg': 'library sdoc index is running'}, 400

        try:
            flask_app.app.index_manager.delete_library_sdoc_index_by_repo_id(repo_id, flask_app.app.repo_file_index, flask_app.app.repo_status_index)
        except Exception as e:
            logger.exception(e)
            return {'error_msg': 'Internet server error.'}, 500

        return {'success': True}, 200

    elif request.method == 'PUT':
        commit_id = flask_app.app.repo_data.get_repo_head_commit(repo_id)

        if not commit_id:
            return {'error_msg': 'repo invalid.'}, 400

        task = index_task_manager.get_pending_or_running_task(repo_id)

        if task:
            return {'task_id': task.id}, 200


        try:
            task_id = index_task_manager.add_update_a_library_sdoc_index_task(repo_id, commit_id)
        except Exception as e:
            logger.exception(e)
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

    repo_id = request.args.get('repo_id')
    if not repo_id:
        return {'error_msg': 'repo_id invalid'}, 400

    try:
        is_exist = flask_app.app.repo_status_index.check_repo_status(repo_id)
    except Exception as e:
        logger.exception(e)
        return {'error_msg': 'Internet server error.'}, 500

    if not is_exist:
        return {'state': 'uncreated', 'task_id': ''}

    task = index_task_manager.get_pending_or_running_task(repo_id)

    return task and {'state': 'running', 'task_id': task.id} or {'state': 'finished', 'task_id': ''}
