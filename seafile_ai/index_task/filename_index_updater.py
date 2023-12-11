import logging
from threading import Thread

from apscheduler.schedulers.blocking import BlockingScheduler
from seafile_ai.repo_data import repo_data


logger = logging.getLogger(__name__)


class RepoFilenameIndexUpdater(object):
    def __init__(self, app):
        self._repo_status_filename_index = app.repo_status_filename_index
        self._repo_filename_index = app.repo_filename_index
        self._index_manager = app.index_manager

    def start(self):
        RepoFilenameIndexUpdaterTimer(
            self._repo_status_filename_index, self._repo_filename_index, self._index_manager
        ).start()


def clear_deleted_repo(repo_status_filename_index, repo_filename_index, index_manager, repos):
    logger.info("start to clear filename index deleted repo")

    repo_list = repo_status_filename_index.get_all_repos_from_index()
    repo_all = [e.get('repo_id') for e in repo_list]

    repo_deleted = set(repo_all) - set(repos)

    logger.info("filename index %d repos need to be deleted." % len(repo_deleted))
    for repo_id in repo_deleted:
        index_manager.delete_repo_filename_index(repo_id, repo_filename_index, repo_status_filename_index)
        logger.info('Repo %s has been deleted from filename index.' % repo_id)
    logger.info("filename index deleted repo has been cleared")


def update_repo_file_name_indexes(repo_status_filename_index, repo_filename_index, index_manager):
    start, count = 0, 1000
    all_repos = []
    while True:
        try:
            repo_commits = repo_data.get_repo_id_commit_id(start, count)
        except Exception as e:
            logger.error("Error: %s" % e)
            return
        start += 1000

        if len(repo_commits) == 0:
            break

        for repo_id, commit_id in repo_commits.items():
            all_repos.append(repo_id)

            context = {
                'repo_id': repo_id,
                'commit_id': commit_id
            }

            index_manager.update_library_filename_index(context, repo_filename_index, repo_status_filename_index)

    clear_deleted_repo(repo_status_filename_index, repo_filename_index, index_manager, all_repos)


class RepoFilenameIndexUpdaterTimer(Thread):
    def __init__(self, repo_status_filename_index, repo_filename_index, index_manager):
        super(RepoFilenameIndexUpdaterTimer, self).__init__()
        self.repo_status_filename_index = repo_status_filename_index
        self.repo_filename_index = repo_filename_index
        self.index_manager = index_manager

    def run(self):
        sched = BlockingScheduler()
        @sched.scheduled_job('cron', minute='*/5')
        def timed_job():
            logging.info('Starts to update filename index...')
            try:
                update_repo_file_name_indexes(self.repo_status_filename_index, self.repo_filename_index, self.index_manager)
            except Exception as e:
                logging.exception('periodical update filename index error: %s', e)

        sched.start()
