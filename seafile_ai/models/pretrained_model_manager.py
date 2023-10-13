import logging
import os
import shutil
from abc import ABC, abstractmethod

from modelscope.models import Model
from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks
from modelscope.hub.snapshot_download import snapshot_download as ms_download

from text2vec import SentenceModel
from huggingface_hub import snapshot_download as hf_download


logger = logging.getLogger(__name__)


class BaseModel(ABC):
    @abstractmethod
    def download_model(self):
        pass


class RetrievalBaseModel(BaseModel):
    def __init__(self, model_id, cache_dir, metric, dimension):
        self.model_id = model_id
        self.cache_dir = cache_dir
        self.metric = metric
        self.dimension = dimension
        self.local_model_path = None

    @abstractmethod
    def encode(self, sentences):
        pass


class RerankBaseModel(BaseModel):
    def __init__(self, model_id, cache_dir):
        self.model_id = model_id
        self.cache_dir = cache_dir
        self.local_model_path = None

    @abstractmethod
    def rerank(self, query, compare_sentences):
        pass


class HuggingFaceRetrievalModel(RetrievalBaseModel):
    def __init__(self, model_id, cache_dir, metric=None, dimension=768):
        super().__init__(model_id, cache_dir, metric, dimension)
        self._init()

    def _init(self):
        if not self.local_model_path:
            self.local_model_path = self.download_model()

    def download_model(self):
        model_dir_name = 'models--' + self.model_id.replace('/', '--')
        storage_model_path = os.path.join(self.cache_dir, model_dir_name)
        if os.path.exists(storage_model_path):
            local_model_path = hf_download(repo_id=self.model_id, cache_dir=self.cache_dir, local_files_only=True)
        else:
            try:
                local_model_path = hf_download(repo_id=self.model_id, cache_dir=self.cache_dir)
            except Exception as e:
                logger.critical("Download model failed: %s." % e)
                shutil.rmtree(storage_model_path, ignore_errors=True)
                raise RuntimeError("Download model failed: %s" % e)
        return local_model_path

    def encode(self, sentences):
        return SentenceModel(self.local_model_path).encode(sentences)


def alibaba_model_download(cache_dir, model_id):
    storage_model_path = os.path.join(cache_dir, model_id)
    if os.path.exists(storage_model_path):
        local_model_path = ms_download(model_id, cache_dir=cache_dir, local_files_only=True)
    else:
        try:
            local_model_path = ms_download(model_id, cache_dir=cache_dir)
        except Exception as e:
            logger.critical("Download model failed: %s." % e)
            shutil.rmtree(storage_model_path, ignore_errors=True)
            raise RuntimeError("Download model failed: %s" % e)
    return local_model_path


class AlibabaRetrievalModel(RetrievalBaseModel):
    def __init__(self, model_id, cache_dir, metric=None, dimension=768):
        super().__init__(model_id, cache_dir, metric, dimension)
        self.pipeline = None
        self._init()

    def _init(self):
        if not self.local_model_path:
            self.local_model_path = self.download_model()

        model = Model.from_pretrained(self.local_model_path)
        self.pipeline = pipeline(Tasks.sentence_embedding, model=model)

    def download_model(self):
        return alibaba_model_download(self.cache_dir, self.model_id)

    def encode(self, sentences):
        inputs = {
            "source_sentence": sentences
        }
        return self.pipeline(input=inputs).get('text_embedding')


class AlibabaRerankModel(RerankBaseModel):
    def __init__(self, model_id, cache_dir):
        super().__init__(model_id, cache_dir)
        self.pipeline = None
        self._init()

    def _init(self):
        if not self.local_model_path:
            self.local_model_path = self.download_model()
        model = Model.from_pretrained(self.local_model_path)
        self.pipeline = pipeline(Tasks.text_ranking, model=model)

    def download_model(self):
        return alibaba_model_download(self.cache_dir, self.model_id)

    def rerank(self, query, compare_sentences):
        inputs = {
            'source_sentence': [query],
            'sentences_to_compare': compare_sentences
        }
        return self.pipeline(input=inputs).get('scores')


class PretrainedModelManager(object):
    retrieval_model = {'alibaba': AlibabaRetrievalModel, 'huggingface': HuggingFaceRetrievalModel}
    rerank_model = {'alibaba': AlibabaRerankModel}

    @classmethod
    def create_retrieval_model(cls, config):
        source = config.RETRIEVAL_SOURCE
        model_id = config.RETRIEVAL_MODEL_ID
        cache_dir = config.MODEL_CACHE_DIR
        metric = config.RETRIEVAL_METRIC
        dimension = config.DIMENSION

        return cls.retrieval_model[source](model_id, cache_dir, metric, dimension)

    @classmethod
    def create_rerank_model(cls, config):
        source = config.RERANK_SOURCE
        model_id = config.RERANK_MODEL_ID
        cache_dir = config.MODEL_CACHE_DIR

        return cls.rerank_model[source](model_id, cache_dir)
