import os
import logging
from datetime import datetime

from seafile_ai import config
from seafile_ai.db import init_db_session_class
from seafile_ai.index_store.utils import update_library_sdoc_embedding_to_faiss, save_library_sdoc_embedding_to_faiss
from seafile_ai.index_store.models import LibrarySdocIndex
from seafile_ai.utils.constant import LIBRARY_SDOC_INDEX
from seafile_ai.index_store.faiss_cache import FaissCache

logger = logging.getLogger(__name__)


class IndexManager(object):
    def __init__(self):
        self.faiss_cache = FaissCache()

    def get_library_sdoc_index_by_associate_id(self, associate_id, db_session):
        return db_session.query(LibrarySdocIndex).filter(LibrarySdocIndex.associate_id == associate_id).first()

    def create_library_sdoc_index_db(self, associate_id, last_modify, db_session):
        index = LibrarySdocIndex(associate_id, last_modify, datetime.now())
        db_session.add(index)
        db_session.commit()
        return index

    def create_library_sdoc_index_without_session(self, context, retrieval_model):
        db_session = init_db_session_class(config)()
        try:
            self.create_library_sdoc_index(context, db_session, retrieval_model)
        except Exception as e:
            logger.exception(e)
        finally:
            db_session.close()

    def create_library_sdoc_index(self, context, db_session, retrieval_model):
        save_library_sdoc_embedding_to_faiss(context, retrieval_model)
        # update `updated`
        self.get_library_sdoc_index_by_associate_id(context.get('associate_id'), db_session).updated = datetime.now()

        db_session.commit()

    def search_children_in_library(self, query, associate_id, sdoc_files_info, retrieval_model, rerank_model):
        from seafile_ai.index_store.utils import search_children_in_library
        return search_children_in_library(query, associate_id, sdoc_files_info, retrieval_model, rerank_model, self.faiss_cache)

    def update_library_sdoc_index_without_session(self, context, retrieval_model):
        db_session = init_db_session_class(config)()
        try:
            self.update_library_sdoc_index(context, db_session, retrieval_model)
        except Exception as e:
            logger.exception(e)
        finally:
            db_session.close()

    def update_library_sdoc_index(self, context, db_session, retrieval_model):

        associate_id = context.get('associate_id')
        last_modify = context.get('last_modify')

        is_embedding_updated = update_library_sdoc_embedding_to_faiss(context, retrieval_model)

        if is_embedding_updated:
            index_path = os.path.join(config.INDEX_STORAGE_PATH, LIBRARY_SDOC_INDEX, associate_id + '.index')
            self.faiss_cache.delete(index_path)

            # update db
            library_sdoc_index = db_session.query(LibrarySdocIndex). \
                filter(LibrarySdocIndex.associate_id == associate_id)
            library_sdoc_index.update({"updated": datetime.now(), "last_modify": last_modify})
            db_session.commit()

    def delete_library_sdoc_index_by_associate_id(self, associate_id, db_session):
        db_session.query(LibrarySdocIndex).filter(LibrarySdocIndex.associate_id == associate_id).delete()
        db_session.commit()

