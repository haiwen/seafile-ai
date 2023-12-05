import logging
import queue
import uuid
import pytz
from datetime import datetime, timedelta
from threading import Thread, Lock

from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.gevent import GeventScheduler

from seafile_ai import config
from seafile_ai.index_store.repo_status_index import RepoStatus
from seafile_ai.repo_data import repo_data

logger = logging.getLogger(__name__)


class IndexTask:

    def __init__(self, task_id, readable_id, func, args):
        self.id = task_id
        self.readable_id = readable_id
        self.func = func
        self.args = args

        self.status = 'init'

        self.started_at = None
        self.finished_at = None

        self.result = None
        self.error = None

    @staticmethod
    def get_readable_id(readable_id):
        return readable_id

    def run(self):
        self.status = 'running'
        self.started_at = datetime.now()
        return self.func(*self.args)

    def set_result(self, result):
        self.result = result
        self.status = 'success'
        self.finished_at = datetime.now()

    def set_error(self, error):
        self.error = error
        self.status = 'error'
        self.finished_at = datetime.now()

    def is_finished(self):
        return self.status in ['error', 'success']

    def get_cost_time(self):
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).seconds
        return None

    def get_info(self):
        return f'{self.id}--{self.readable_id}--{self.func}'

    def __str__(self):
        return f'<IndexTask {self.id} {self.readable_id} {self.func.__name__} {self.status}>'


class IndexTaskManager:

    def __init__(self):
        self.tasks_queue = queue.Queue()
        self.tasks_map = {}             # {task_id: task} all tasks
        self.readable_id2task_map = {}  # {task_readable_id: task} in queue or running
        self.check_task_lock = Lock()   # lock access to readable_id2task_map
        self.sched = GeventScheduler()
        self.app = None
        self.conf = {
            'workers': config.INDEX_MANAGER_WORKERS,
            'expire_time': config.INDEX_TASK_EXPIRE_TIME
        }
        self.sched.add_job(self.clear_expired_tasks, CronTrigger(minute='*/10'))
        self.sched.add_job(self.cron_update_library_sdoc_indexes, CronTrigger(day_of_week='*'))

    def init(self, app):
        self.app = app

    def get_pending_or_running_task(self, readable_id):
        task = self.readable_id2task_map.get(readable_id)
        return task

    def add_library_sdoc_index_task(self, context):
        readable_id = context.get('repo_id')
        with self.check_task_lock:
            task = self.get_pending_or_running_task(readable_id)
            if task:
                return task.id

            task_id = str(uuid.uuid4())
            task = IndexTask(task_id, readable_id, self.app.index_manager.create_library_sdoc_index,
                             (context, self.app.retrieval_model, self.app.repo_file_index, self.app.repo_status_index)
                             )
            self.tasks_map[task_id] = task
            self.readable_id2task_map[task.readable_id] = task
            self.tasks_queue.put(task)

            return task_id

    def search_similar_children_in_library(self, query, associate_id):
        return self.app.index_manager.\
            search_children_in_library(query, associate_id, self.app.retrieval_model, self.app.repo_file_index)

    def add_update_a_library_sdoc_index_task(self, context):
        readable_id = context.get('repo_id')
        with self.check_task_lock:
            task = self.get_pending_or_running_task(readable_id)
            if task:
                return task.id

            task_id = str(uuid.uuid4())
            task = IndexTask(task_id, readable_id, self.app.index_manager.update_library_sdoc_index,
                             (context, self.app.retrieval_model, self.app.repo_file_index, self.app.repo_status_index)
                             )
            self.tasks_map[task_id] = task
            self.readable_id2task_map[task.readable_id] = task
            self.tasks_queue.put(task)

            return task_id

    @staticmethod
    def list_pending_repo_indexes(repo_status_index):
        per_day_check_time = datetime.now() - timedelta(hours=23)
        utc_zone = pytz.timezone('UTC')
        per_day_check_time = per_day_check_time.astimezone(utc_zone)
        per_day_check_time = per_day_check_time.strftime("%Y-%m-%dT%H:%M:%S.8%fZ")

        repo_indexes = repo_status_index.get_repo_status_by_time(per_day_check_time)

        return repo_indexes

    def update_library_sdoc_indexes(self):
        repo_status_index = self.app.repo_status_index
        repo_file_index = self.app.repo_file_index
        repo_indexes = self.list_pending_repo_indexes(repo_status_index)

        repo_id_list = [repo_index.get('repo_id') for repo_index in repo_indexes]
        repo_to_commit = repo_data.get_repos_head_commits(repo_id_list)

        for repo_index in repo_indexes:
            repo_id = repo_index.get('repo_id')
            old_commit_id = repo_index.get('commit_id')
            updatingto = repo_index.get('updatingto')

            repo_status = RepoStatus(repo_id, old_commit_id, updatingto)

            new_commit_id = repo_to_commit.get(repo_id)

            if not new_commit_id:
                # if not new_commit_id delete repo index
                repo_file_index.delete_index_by_index_name(repo_id)
                repo_status_index.delete_repo_status_by_id(repo_id)

            if old_commit_id == new_commit_id:
                continue

            context = {
                "repo_id": repo_id,
                "repo_status": repo_status,
                "commit_id": new_commit_id,
            }

            self.add_update_a_library_sdoc_index_task(context)


    def cron_update_library_sdoc_indexes(self):
        """
            update library sdoc indexes periodly
            query tasks and add them to queue by calling self.add_update_a_library_sdoc_index_task
        """

        try:
            self.update_library_sdoc_indexes()
        except Exception as e:
            logger.exception('periodical update library sdoc indexes error: %s', e)

    def query_task(self, task_id):
        return self.tasks_map.get(task_id)

    def handle_task(self):
        while True:
            try:
                task = self.tasks_queue.get(timeout=2)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(e)
                continue

            try:
                task_info = task.get_info()
                logger.info('Run task: %s' % task_info)

                # run
                task.run()
                task.set_result('success')

                logger.info('Run task success: %s cost %ds \n' % (task_info, task.get_cost_time()))
            except Exception as e:
                task.set_error(e)
                logger.exception('Failed to handle task %s, error: %s \n' % (task.id, e))
            finally:
                with self.check_task_lock:
                    self.readable_id2task_map.pop(task.readable_id, None)

    def start(self):
        thread_num = self.conf['workers']
        for i in range(thread_num):
            t_name = 'IndexTaskManager Thread-' + str(i)
            t = Thread(target=self.handle_task, name=t_name)
            t.setDaemon(True)
            t.start()
        self.sched.start()

    def clear_expired_tasks(self):
        """clear tasks finished for conf['expire_time'] in tasks_map

        when a task end, it will not be pop from tasks_map immediately,
        because this task might be responsible for multi-http-requests(not only one), that might query task status

        but task will not restored forever, so need to clear
        """
        expire_tasks = []
        for task in self.tasks_map.values():
            if not task.is_finished():
                continue
            if (datetime.now() - task.finished_at).seconds >= self.conf['expire_time']:
                expire_tasks.append(task)
        logger.info('expired tasks: %s', len(expire_tasks))
        for task in expire_tasks:
            self.tasks_map.pop(task.id, None)


index_task_manager = IndexTaskManager()
