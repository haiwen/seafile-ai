from seafile_ai.index_task.index_task_manager import index_task_manager
from seafile_ai.index_store.index_manager import IndexManager
from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.models.pretrained_model_manager import PretrainedModelManager
from seafile_ai.utils.seafile_api import SeafileAPI
from seafile_ai.utils.seasearch_api import SeaSearchAPI
from seafile_ai.index_store.repo_status_index import RepoStatusIndex
from seafile_ai.index_store.repo_file_index import RepoFileIndex
from seafile_ai.utils.openai_api import OpenAIAPI


class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        self.index_manager = IndexManager()
        self.retrieval_model = PretrainedModelManager.create_retrieval_model(config)
        self.seafile_api = SeafileAPI(config.APP_NAME, config.SEAFILE_SERVER)
        self.seasearch_api = SeaSearchAPI(config.SEASEARCH_SERVER, config.SEASEARCH_TOKEN)

        self.repo_status_index = RepoStatusIndex(self.seasearch_api)
        self.repo_file_index = RepoFileIndex(self.seasearch_api)

        index_task_manager.init(self)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

        self.openai_api = OpenAIAPI(config.OPENAI_PROXY_URL)

    def serve_forever(self):
        index_task_manager.start()
        self.seafile_ai_http_server.start()
