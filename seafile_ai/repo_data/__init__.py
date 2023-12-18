import logging
from sqlalchemy.sql import text

from seafile_ai.db import init_db_session_class

logger = logging.getLogger(__name__)


class RepoData(object):
    def __init__(self, server, port, username, passwd, db_name, unix_socket):
        self.db_session = init_db_session_class(server, port, username, passwd, db_name, unix_socket)

    def to_dict(self, result_proxy):
        res = []
        for i in result_proxy.mappings():
            res.append(i)
        return res

    def _get_repo_head_commit(self, repo_id):
        session = self.db_session()
        try:
            cmd = """SELECT b.commit_id
                     from Branch as b inner join Repo as r
                     where b.repo_id=r.repo_id and b.repo_id=:repo_id"""
            res = session.execute(text(cmd), {'repo_id': repo_id}).fetchone()
            return res[0] if res else None
        except Exception as e:
            raise e
        finally:
            session.close()

    def _get_repo_id_commit_id_by_repos(self, repo_id_list):
        session = self.db_session()
        try:
            sql = """SELECT r.repo_id, b.commit_id from Branch as b inner join Repo as r
                     where b.repo_id=r.repo_id and r.repo_id in :repo_id_list"""

            res = {r[0]: r[1] for r in session.execute(text(sql), {'repo_id_list': repo_id_list})}
            return res
        except Exception as e:
            raise e
        finally:
            session.close()

    def _get_repo_name_mtime_size(self, repo_id):
        session = self.db_session()
        try:
            sql = """SELECT RepoInfo.name, RepoInfo.update_time, RepoSize.size
                     FROM RepoInfo INNER JOIN RepoSize ON RepoInfo.repo_id = RepoSize.repo_id
                     AND RepoInfo.repo_id = :repo_id"""
            res = session.execute(text(sql), {'repo_id': repo_id})
            return self.to_dict(res)
        except Exception as e:
            raise e
        finally:
            session.close()

    def _get_repo_id_commit_id(self, start, count):
        session = self.db_session()
        try:
            cmd = """SELECT repo_id, commit_id
                     FROM Branch WHERE name = :name
                     AND repo_id NOT IN (SELECT repo_id from VirtualRepo)
                     limit :start, :count"""
            res = {r[0]: r[1] for r in session.execute(text(cmd),
                                                          {'name': 'master',
                                                           'start': start,
                                                           'count': count})}
            return res
        except Exception as e:
            raise e
        finally:
            session.close()

    def get_repo_head_commit(self, repo_id):
        try:
            return self._get_repo_head_commit(repo_id)
        except Exception as e:
            logger.error(e)
            return self._get_repo_head_commit(repo_id)

    def get_repo_id_commit_id_by_repos(self, repo_id_list):
        if not repo_id_list:
            return {}
        try:
            return self._get_repo_id_commit_id_by_repos(repo_id_list)
        except Exception as e:
            logger.error(e)
            return self._get_repo_id_commit_id_by_repos(repo_id_list)

    def get_repo_name_mtime_size(self, repo_id):
        try:
            return self._get_repo_name_mtime_size(repo_id)
        except Exception as e:
            logger.error(e)
            return self._get_repo_name_mtime_size(repo_id)

    def get_repo_id_commit_id(self, start, count):
        try:
            return self._get_repo_id_commit_id(start, count)
        except Exception as e:
            logger.error(e)
            return self._get_repo_id_commit_id(start, count)
