import logging
from datetime import datetime

from seafile_ai import config
from seafile_ai.db import init_db_session_class
from seafile_ai.index_store.utils import update_library_sdoc_embedding_to_zinc, save_library_sdoc_embedding_to_zinc
from seafile_ai.index_store.models import LibrarySdocIndex

logger = logging.getLogger(__name__)


class IndexManager(object):
    def get_library_sdoc_index_by_associate_id(self, associate_id, db_session):
        return db_session.query(LibrarySdocIndex).filter(LibrarySdocIndex.associate_id == associate_id).first()

    def create_library_sdoc_index_db(self, associate_id, last_modify, db_session):
        index = LibrarySdocIndex(associate_id, last_modify, datetime.now())
        db_session.add(index)
        db_session.commit()
        return index

    def create_library_sdoc_index_without_session(self, context, retrieval_model, zinc_api):
        db_session = init_db_session_class(config)()
        try:
            self.create_library_sdoc_index(context, db_session, retrieval_model, zinc_api)
        except Exception as e:
            logger.exception(e)
        finally:
            db_session.close()

    def create_library_sdoc_index(self, context, db_session, retrieval_model, zinc_api):
        save_library_sdoc_embedding_to_zinc(context, retrieval_model, zinc_api)
        # update `updated`
        self.get_library_sdoc_index_by_associate_id(context.get('associate_id'), db_session).updated = datetime.now()

        db_session.commit()

    def search_children_in_library(self, query, associate_id, sdoc_files_info, retrieval_model, zinc_api):
        from seafile_ai.index_store.utils import search_children_in_library
        return search_children_in_library(query, associate_id, sdoc_files_info, retrieval_model, zinc_api)

    def update_library_sdoc_index_without_session(self, context, retrieval_model, zinc_api):
        db_session = init_db_session_class(config)()
        try:
            self.update_library_sdoc_index(context, retrieval_model, zinc_api, db_session)
        except Exception as e:
            logger.exception(e)
        finally:
            db_session.close()

    def update_library_sdoc_index(self, context, retrieval_model, zinc_api, db_session):
        associate_id = context.get('associate_id')
        last_modify = context.get('last_modify')

        update_library_sdoc_embedding_to_zinc(context, retrieval_model, zinc_api)
        # update db
        library_sdoc_index = db_session.query(LibrarySdocIndex).filter(LibrarySdocIndex.associate_id == associate_id)
        library_sdoc_index.update({"updated": datetime.now(), "last_modify": last_modify})
        db_session.commit()

    def delete_library_sdoc_index_by_associate_id(self, associate_id, db_session):
        db_session.query(LibrarySdocIndex).filter(LibrarySdocIndex.associate_id == associate_id).delete()
        db_session.commit()
