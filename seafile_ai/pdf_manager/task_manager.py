import logging
import queue
import uuid
import os

from datetime import datetime
from threading import Thread, Lock

from seafile_ai.utils import get_file_by_token
from seafile_ai.pdf_manager import PDFManager


logger = logging.getLogger(__name__)


class Task:
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
        return f'{self.id}-{self.readable_id}-{self.func}'

    def __str__(self):
        return f'<Task {self.id} {self.readable_id} {self.func.__name__} {self.status}>'


class TaskManager:
    def __init__(self):
        self.ocr_task_queue = queue.Queue()
        self.ocr_worker_num = 3
        self.readable_id2task_map = {}  # {task_readable_id: task} in queue or running
        self.check_task_lock = Lock()

    def init(self, app):
        self.app = app

    def get_pending_or_running_task(self, readable_id):
        task = self.readable_id2task_map.get(readable_id)
        return task

    def add_ocr_task(self, repo_id, path, download_token, upload_token, force):
        file_name = os.path.basename(path.rstrip('/'))
        b_pdf = get_file_by_token(download_token, file_name)
        if not force:
            pdf_reader = PDFManager.read_pdf(b_pdf)
            has_text = PDFManager.has_text_layer(pdf_reader)
            if has_text:
                return None, 'already_ocr'

        with self.check_task_lock:
            readable_id = repo_id + '_' + path
            task = self.get_pending_or_running_task(readable_id)
            if task and not task.is_finished():
                return task.id, 'processing'
            
            task_id = str(uuid.uuid4())
            task = Task(task_id, readable_id, self.app.pdf_manager.gen_dual_layer_pdf, (task_id, path, b_pdf, upload_token))
            self.readable_id2task_map[task.readable_id] = task
            self.ocr_task_queue.put(task)
            
            return task_id, 'queued'

    def handle_task(self):
        while True:
            try:
                task = self.ocr_task_queue.get(timeout=2)
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
                logger.exception('Failed to handle task %s, error: %s \n' % (task.get_info(), e))
            finally:
                with self.check_task_lock:
                    self.readable_id2task_map.pop(task.readable_id, None)

    def start_ocr_workers(self):
        logging.info('Starting OCR workers with %d threads', self.ocr_worker_num)
        for i in range(self.ocr_worker_num):
            worker_name = 'OCR_PDF_Task Thread-' + str(i)
            worker = Thread(target=self.handle_task, name=worker_name)
            worker.daemon = True
            worker.start()

task_manager = TaskManager()
