import logging
import queue
import uuid
from datetime import datetime, timedelta
from threading import Thread, Lock

from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.gevent import GeventScheduler
from sqlalchemy.sql import text

from seafile_ai import config
from seafile_ai.db import init_db_session_class

logger = logging.getLogger(__name__)
Session = init_db_session_class(config)


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
        readable_id = context.get('associate_id')
        with self.check_task_lock:
            task = self.get_pending_or_running_task(readable_id)
            if task:
                return task.id

            task_id = str(uuid.uuid4())
            task = IndexTask(task_id, readable_id, self.app.index_manager.create_library_sdoc_index_without_session, (context, self.app.retrieval_model))
            self.tasks_map[task_id] = task
            self.readable_id2task_map[task.readable_id] = task
            self.tasks_queue.put(task)

            return task_id

    def search_similar_children_in_library(self, query, associate_id, sdoc_files_info):
        with self.check_task_lock:
            return self.app.index_manager.search_children_in_library(query, associate_id, sdoc_files_info,
                                                                      self.app.retrieval_model,
                                                                    )

    def add_update_a_library_sdoc_index_task(self, context):
        readable_id = context.get('associate_id')
        with self.check_task_lock:
            task = self.get_pending_or_running_task(readable_id)
            if task:
                return task.id

            task_id = str(uuid.uuid4())
            task = IndexTask(task_id, readable_id, self.app.index_manager.update_library_sdoc_index_without_session,
                             (context, self.app.retrieval_model))
            self.tasks_map[task_id] = task
            self.readable_id2task_map[task.readable_id] = task
            self.tasks_queue.put(task)

            return task_id

    @staticmethod
    def list_pending_library_indexes(db_session):
        sql = """
                SELECT `associate_id`, `last_modify`
                FROM library_sdoc_index WHERE `updated`<:per_day_check_time
                """

        per_day_check_time = datetime.now() - timedelta(hours=23)
        library_sdoc_indexes = db_session.execute(text(sql), {
            'per_day_check_time': per_day_check_time,
        })
        return library_sdoc_indexes

    def update_library_sdoc_indexes(self, db_session):
        library_sdoc_indexes = self.list_pending_library_indexes(db_session)
        seafile_api = self.app.seafile_api

        for library_index in library_sdoc_indexes:
            associate_id = library_index[0]
            old_last_modify = library_index[1]

            library_files = seafile_api.get_library_files(associate_id)
            new_last_modify = library_files.get('last_modify')

            if old_last_modify == new_last_modify:
                continue

            sdoc_info_list = library_files.get('sdoc_info_list')

            context = {
                'associate_id': associate_id,
                'last_modify': new_last_modify,
                'sdoc_info_list': sdoc_info_list
            }

            self.add_update_a_library_sdoc_index_task(context)


    def cron_update_library_sdoc_indexes(self):
        """
            update library sdoc indexes periodly
            query tasks and add them to queue by calling self.add_update_a_library_sdoc_index_task
        """
        db_session = Session()
        try:
            self.update_library_sdoc_indexes(db_session)
        except Exception as e:
            logger.exception('periodical update library sdoc indexes error: %s', e)
        finally:
            db_session.close()

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
                logger.error('Failed to handle task %s, error: %s \n' % (task.id, e))
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
