import logging
from seafile_ai.repo_metadata.constants import FACES_TABLE, METADATA_TABLE

logger = logging.getLogger(__name__)
UNKNOWN_PEOPLE_NAME = '_Unknown_people'

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