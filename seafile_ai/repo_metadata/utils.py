import logging
import os

from sqlalchemy import text

from seafile_ai.db import init_db_session_class
from seafile_ai.repo_metadata.constants import FACES_TABLE, METADATA_TABLE
from seafobj import commit_mgr, fs_mgr

logger = logging.getLogger(__name__)
UNKNOWN_PEOPLE_NAME = '_Unknown_people'
seafile_db_session_class = init_db_session_class('seafile')
seahub_db_session_class = init_db_session_class()

def get_metadata_by_obj_ids(repo_id, obj_ids, metadata_server_api):
    sql = f'SELECT * FROM `{METADATA_TABLE.name}` WHERE `{METADATA_TABLE.columns.obj_id.name}` IN ('
    parameters = []

    for obj_id in obj_ids:
        sql += '?, '
        parameters.append(obj_id)

    if not parameters:
        return []
    sql = sql.rstrip(', ') + ');'
    query_result = metadata_server_api.query_rows(repo_id, sql, parameters).get('results', [])

    if not query_result:
        return []

    return query_result


def get_metadata_by_row_ids(repo_id, row_ids, metadata_server_api):
    sql = f'SELECT * FROM `{METADATA_TABLE.name}` WHERE `{METADATA_TABLE.columns.id.name}` IN ('
    parameters = []

    for row_id in row_ids:
        sql += '?, '
        parameters.append(row_id)

    if not parameters:
        return []
    sql = sql.rstrip(', ') + ');'
    query_result = metadata_server_api.query_rows(repo_id, sql, parameters).get('results', [])

    if not query_result:
        return []

    return query_result


def query_metadata_rows(repo_id, metadata_server_api, sql, limit=-1, params=None):
    """
    Query metadata rows from the metadata server.

    Args:
        repo_id: The repository ID.
        metadata_server_api: The MetadataServerAPI instance.
        sql: The SQL query to execute.
        limit: Maximum number of rows to return.
                - -1 (default): return all records (paginated internally).
                - > 0: return at most 'limit' rows, stops fetching after reaching the limit.
        params: SQL query parameters.

    Returns:
        List of metadata row dicts.
    """
    rows = []
    offset = 10000
    start = 0

    while True:
        fetch_limit = min(offset, limit) if limit > 0 else offset
        query_sql = f"{sql} LIMIT {start}, {fetch_limit}"
        response_rows = metadata_server_api.query_rows(repo_id, query_sql, params or []).get('results', [])
        if not response_rows:
            response_rows = []
        rows.extend(response_rows)

        # If a positive limit is set and we've fetched enough, stop
        if limit > 0 and len(rows) >= limit:
            rows = rows[:limit]
            break

        if len(response_rows) < offset:
            break
        start += offset

    return rows

def get_faces_rows(repo_id, metadata_server_api):
    logger.info('get_faces_rows, repo_id=%s', repo_id)
    sql = f'SELECT * FROM `{FACES_TABLE.name}`'
    query_result = query_metadata_rows(repo_id, metadata_server_api, sql)
    clustered_rows = []
    unclustered_rows = []
    for row in query_result:
        if row.get(FACES_TABLE.columns.name.name) == UNKNOWN_PEOPLE_NAME:
            unclustered_rows.append(row)
        else:
            clustered_rows.append(row)
    return clustered_rows, unclustered_rows


def get_metadata_by_path(repo_id, path, metadata_server_api):
    metadata = get_repo_metadata(repo_id)
    if not metadata or not metadata.enabled:
        repo = get_repo_info(repo_id)
        if not repo:
            return None

        obj_id = get_file_id_by_path(repo, path)
        if not obj_id:
            return None

        return {
            METADATA_TABLE.columns.obj_id.name: obj_id,
        }

    parent_dir = os.path.dirname(path) or '/'
    file_name = os.path.basename(path)
    if not file_name:
        return None

    sql = (
        f'SELECT * FROM `{METADATA_TABLE.name}` '
        f'WHERE `{METADATA_TABLE.columns.parent_dir.name}` = ? '
        f'AND `{METADATA_TABLE.columns.file_name.name}` = ? '
        f'AND `{METADATA_TABLE.columns.is_dir.name}` = False LIMIT 1;'
    )
    query_result = metadata_server_api.query_rows(repo_id, sql, [parent_dir, file_name]).get('results', [])
    if not query_result:
        return None

    return query_result[0]

def get_repo_metadata(repo_id):
    with seahub_db_session_class() as session:
        sql = text("""
            SELECT enabled
            FROM repo_metadata
            WHERE repo_id = :repo_id
            LIMIT 1
        """)
        return session.execute(sql, {'repo_id': repo_id}).first()


def is_repo_metadata_enabled(repo_id):
    metadata = get_repo_metadata(repo_id)
    return bool(metadata and metadata.enabled)


def get_repo_info(repo_id):
    with seafile_db_session_class() as session:
        sql = text("""
            SELECT v.origin_repo as origin_repo_id
            FROM Repo r
            LEFT JOIN VirtualRepo v ON r.repo_id = v.repo_id
            WHERE r.repo_id = :repo_id
        """)
        result = session.execute(sql, {'repo_id': repo_id}).first()
        if not result:
            return None

        repo = {
            'repo_id': repo_id,
            'origin_repo_id': result.origin_repo_id,
        }
        return repo

def get_repo_head_commit(repo_id):
    try:
        with seafile_db_session_class() as session:
            sql = text("""SELECT b.commit_id, r.type
                        from Branch as b inner join RepoInfo as r
                        where b.repo_id=r.repo_id and b.repo_id=:repo_id"""
            )
            res = session.execute(sql, {'repo_id': repo_id}).first()
            return res
    except Exception as error:
        raise error

def get_file_id_by_path(repo, file_path):
    origin_repo_id = repo.get('origin_repo_id')
    commit_id = get_repo_head_commit(repo['repo_id'])[0]
    commit = commit_mgr.load_commit(repo['repo_id'], 0, commit_id)
    root_id = commit.root_id

    if origin_repo_id:
        file_id = fs_mgr.get_file_id_by_path(origin_repo_id, 1, root_id, file_path)
    else:
        file_id = fs_mgr.get_file_id_by_path(repo['repo_id'], 1, root_id, file_path)

    return file_id
