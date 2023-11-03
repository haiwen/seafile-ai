from seafile_ai.index_task.index_task_manager import index_task_manager
from seafile_ai.index_store.index_manager import IndexManager
from seafile_ai.server.seafile_ai_http_server import SeafileAIHttpServer
from seafile_ai.models.pretrained_model_manager import PretrainedModelManager
from seafile_ai.utils.seafile_api import SeafileAPI


class SeafileAIApp(object):
    def __init__(self, config):
        self.config = config
        self.index_manager = IndexManager()
        self.retrieval_model = PretrainedModelManager.create_retrieval_model(config)
        self.seafile_api = SeafileAPI(config.APP_NAME, config.SEAFILE_SERVER)

        index_task_manager.init(self)
        self.seafile_ai_http_server = SeafileAIHttpServer(self)

    def serve_forever(self):
        index_task_manager.start()
        self.seafile_ai_http_server.start()
