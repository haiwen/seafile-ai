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


def query_metadata_rows(repo_id, metadata_server_api, sql):
    rows = []
    offset = 10000
    start = 0

    while True:
        query_sql = f"{sql} LIMIT {start}, {offset}"
        response_rows = metadata_server_api.query_rows(repo_id, query_sql, []).get('results', [])
        if not response_rows:
            response_rows = []
        rows.extend(response_rows)
        if len(response_rows) < offset:
            break
        start += offset

    return rows


def query_ai_summary_rows(repo_id, metadata_server_api, offset=0, limit=50):
    """
    Query documents with ai_summary with pagination support

    Args:
        repo_id: Repository ID
        metadata_server_api: MetadataServerAPI instance
        offset: Offset for pagination (default: 0)
        limit: Maximum number of rows to return (default: 50)

    Returns:
        List[dict] - Document rows containing ai_summary
    """
    logger.info('query_ai_summary_rows, repo_id=%s, offset=%d, limit=%d', repo_id, offset, limit)

    # Only query required fields to avoid performance issues from selecting all columns
    sql = (
        f'SELECT `{METADATA_TABLE.columns.obj_id.name}`, '
        f'`{METADATA_TABLE.columns.ai_summary.name}`, '
        f'`{METADATA_TABLE.columns.parent_dir.name}`, '
        f'`{METADATA_TABLE.columns.file_name.name}`, '
        f'`{METADATA_TABLE.columns.file_mtime.name}`, '
        f'`{METADATA_TABLE.columns.size.name}` '
        f'FROM `{METADATA_TABLE.name}` '
        f'WHERE `{METADATA_TABLE.columns.ai_summary.name}` IS NOT NULL '
        f'AND `{METADATA_TABLE.columns.ai_summary.name}` != \'\' '
        f'AND `{METADATA_TABLE.columns.is_dir.name}` = False '
        f'ORDER BY `{METADATA_TABLE.columns.file_mtime.name}` DESC '
        f'LIMIT {offset}, {limit}'
    )

    return metadata_server_api.query_rows(repo_id, sql, []).get('results', [])


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
            SELECT enabled, summary_enabled
            FROM repo_metadata
            WHERE repo_id = :repo_id
            LIMIT 1
        """)
        return session.execute(sql, {'repo_id': repo_id}).first()


def is_ai_summary_enabled(repo_id):
    """Check if the repo has metadata enabled and ai_summary enabled."""
    record = get_repo_metadata(repo_id)
    if not record:
        return False
    return bool(record.enabled and record.summary_enabled)

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
