from seafile_ai.index_task.index_task_manager import index_task_manager
from seafile_ai.index_store.index_manager import IndexManager
from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.models.pretrained_model_manager import PretrainedModelManager
from seafile_ai.utils.seafile_api import SeafileAPI
from seafile_ai.utils.seasearch_api import SeaSearchAPI
from seafile_ai.index_store.repo_status_index import RepoStatusIndex
from seafile_ai.index_store.repo_file_index import RepoFileIndex
from seafile_ai.index_store.repo_file_name_index import RepoFileNameIndex
from seafile_ai.utils.openai_api import OpenAIAPI
from seafile_ai.index_task.filename_index_updater import RepoFilenameIndexUpdater
from seafile_ai.utils.constants import REPO_STATUS_FILE_INDEX_NAME, REPO_STATUS_FILENAME_INDEX_NAME
from seafile_ai.repo_data import RepoData


class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        self.index_manager = IndexManager(config.DB_HOST, config.DB_PORT, config.DB_USER, config.DB_PASSWORD,
                                          config.DB_NAME, config.DB_UNIX_SOCKET)
        self.retrieval_model = PretrainedModelManager.create_retrieval_model(config)
        self.seafile_api = SeafileAPI(config.APP_NAME, config.SEAFILE_SERVER)
        self.seasearch_api = SeaSearchAPI(config.SEASEARCH_SERVER, config.SEASEARCH_TOKEN)
        self.repo_data = RepoData(config.MYSQL_HOST, config.MYSQL_PORT, config.MYSQL_USER, config.MYSQL_PASSWORD,
                                  config.MYSQL_DB, config.MYSQL_UNIX_SOCKET)

        # for semantic search
        self.repo_status_index = RepoStatusIndex(self.seasearch_api, REPO_STATUS_FILE_INDEX_NAME)
        self.repo_file_index = RepoFileIndex(self.seasearch_api)

        # for keyword search
        self.repo_status_filename_index = RepoStatusIndex(self.seasearch_api, REPO_STATUS_FILENAME_INDEX_NAME)
        self.repo_filename_index = RepoFileNameIndex(self.seasearch_api, self.repo_data)

        index_task_manager.init(self)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

        self.openai_api = OpenAIAPI(config.OPENAI_PROXY_URL)

        self._repo_filename_index_updater = RepoFilenameIndexUpdater(self)

    def serve_forever(self):
        index_task_manager.start()
        self.seafile_ai_http_server.start()

        # cron task
        self._repo_filename_index_updater.start()
