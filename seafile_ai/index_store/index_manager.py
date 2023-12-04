import logging
import time

from seafile_ai import config
from seafile_ai.utils.constants import ZERO_OBJ_ID

logger = logging.getLogger(__name__)


class IndexManager(object):
    def create_library_sdoc_index(self, context, retrieval_model, repo_file_index, repo_status_index):
        repo_id = context.get('repo_id')
        commit_id = context.get('commit_id')

        repo_status_index.begin_update_repo(repo_id, ZERO_OBJ_ID, commit_id)
        repo_file_index.create_index(repo_id)
        repo_file_index.add_files(repo_id, ZERO_OBJ_ID, commit_id, retrieval_model)
        repo_status_index.finish_update_repo(repo_id, commit_id)

        logger.info('library: %s, save library file to SeaSearch success', repo_id)

    def search_children_in_library(self, query, repo_id, retrieval_model, repo_file_index):
        return repo_file_index.search_files(repo_id, config.RETRIEVAL_NUM, retrieval_model, query)

    def update_library_sdoc_index(self, context, retrieval_model, repo_file_index, repo_status_index):
        try:
            repo_id = context.get('repo_id')
            new_commit_id = context.get('commit_id')
            repo_status = context.get('repo_status')

            from_commit = repo_status.from_commit
            to_commit = repo_status.to_commit

            commit_id = from_commit
            if repo_status.need_recovery():
                logger.warning('%s: inrecovery', repo_id)

                is_exist = repo_file_index.check_index(repo_id)
                if not is_exist:
                    repo_file_index.create_index(repo_id)

                repo_file_index.update_files(repo_id, from_commit, to_commit, retrieval_model)

                # time sleep for SeaSearch save data
                time.sleep(1)

                commit_id = to_commit
            repo_status_index.begin_update_repo(repo_id, commit_id, new_commit_id)
            repo_file_index.update_files(repo_id, commit_id, new_commit_id, retrieval_model)
            repo_status_index.finish_update_repo(repo_id, new_commit_id)

            logger.info('library: %s, update library file to SeaSearch success', repo_id)

        except Exception as e:
            logger.exception(e)

    def delete_library_sdoc_index_by_repo_id(self, repo_id, repo_file_index, repo_status_index):
        # first delete repo_file_index
        repo_file_index.delete_index_by_index_name(repo_id)
        repo_status_index.delete_repo_status_by_id(repo_id)

