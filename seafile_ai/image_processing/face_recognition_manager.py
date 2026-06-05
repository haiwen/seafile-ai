import base64
import os
import time
import logging
from seafile_ai.image_processing.utils import EMBEDDING_UPDATE_LIMIT, SUPPORTED_IMAGE_FORMATS, VECTOR_DEFAULT_FLAG, b64decode_embeddings, b64encode_embeddings, feature_distance, get_cluster_by_center, get_min_cluster_size
from seafile_ai.repo_metadata.constants import FACES_TABLE, METADATA_TABLE
from seafile_ai.repo_metadata.metadata_server_api import MetadataServerAPI
from seafile_ai.repo_metadata.utils import UNKNOWN_PEOPLE_NAME, get_faces_rows, get_metadata_by_obj_ids, get_metadata_by_row_ids, query_metadata_rows

logger = logging.getLogger(__name__)
class FaceRecognitionManager:

    def __init__(self, app):
        self.app = app
        self.metadata_server_api = MetadataServerAPI('seafile-ai')

    
    def face_embeddings_by_obj_ids(self, repo_id, obj_ids, need_classify=False):
        logger.info('face_embeddings_by_obj_ids, repo_id=%s, obj_count=%d, need_classify=%s', repo_id, len(obj_ids), need_classify)
        query_result = get_metadata_by_obj_ids(repo_id, obj_ids, self.metadata_server_api)
        if not query_result:
            return []
        self.face_embeddings(repo_id, query_result, need_classify=need_classify)

    def face_embeddings(self, repo_id, rows, need_classify=False):
        # loop through rows from a repo, to get embedding datas and save them to metadata
        logger.info('repo %s need update face_vectors rows count: %d', repo_id, len(rows))
        updated_rows = []
        start_time = time.time()
        for row in rows:
            obj_id = row[METADATA_TABLE.columns.obj_id.name]
            faces = self.app.image_processing_manager.face_embeddings_without_token(repo_id, obj_id, False)
            face_embeddings = [face['embedding'] for face in faces]
            vector = b64encode_embeddings(face_embeddings) if face_embeddings else VECTOR_DEFAULT_FLAG
            row_id = row[METADATA_TABLE.columns.id.name]
            updated_rows.append({
                METADATA_TABLE.columns.id.name: row_id,
                METADATA_TABLE.columns.face_vectors.name: vector,
            })
            if len(updated_rows) >= EMBEDDING_UPDATE_LIMIT:
                self.metadata_server_api.update_rows(repo_id, METADATA_TABLE.id, updated_rows)
                if need_classify:
                    self.update_face_classify_by_sim(repo_id, updated_rows)
                logger.info('repo %s updated face_vectors rows count: %d, cost time: %.2f', repo_id, len(updated_rows), time.time() - start_time)
                start_time = time.time()
                updated_rows = []

        if updated_rows:
            self.metadata_server_api.update_rows(repo_id, METADATA_TABLE.id, updated_rows)
            if need_classify:
                self.update_face_classify_by_sim(repo_id, updated_rows)
            logger.info('repo %s updated face_vectors under limits rows count: %d, cost time: %.2f', repo_id, len(updated_rows), time.time() - start_time)

    def save_face(self, repo_id, image, filename, replace=False):
        return self.app.seahub_api.save_face(repo_id, image, filename, replace)
    
    def get_image_face(self, path, download_token, center=None): # may deprecated
        logger.info('get_image_face, path=%s', path)
        faces = self.app.image_processing_manager.face_embeddings(path, download_token, True)
        if not faces:
            return None

        if len(faces) == 1:
            return base64.b64decode(faces[0]['face'])
        
        if center:
            sim = [feature_distance(center, face['embedding']) for face in faces]
            return base64.b64decode(faces[sim.index(min(sim))]['face'])

        return base64.b64decode(faces[0]['face'])
    
    def get_image_face_without_token(self, repo_id, obj_id, center=None):
        faces = self.app.image_processing_manager.face_embeddings_without_token(repo_id, obj_id, True)
        if not faces:
            return None

        if len(faces) == 1:
            return base64.b64decode(faces[0]['face'])
        if center is not None:
            sim = [feature_distance(center, face['embedding']) for face in faces]
            return base64.b64decode(faces[sim.index(min(sim))]['face'])

        return base64.b64decode(faces[0]['face'])
    
    def save_cluster_face(self, repo_id, related_row_ids, row_ids, id_to_record, cluster_center, face_row_id):
        logger.info('save_cluster_face, repo_id=%s, face_row_id=%s', repo_id, face_row_id)
        face_image = None
        record = None
        for row_id in related_row_ids:
            if row_ids.count(row_id) == 1:
                record = id_to_record[row_id]
                break

        if not face_image:
            record = id_to_record[related_row_ids[0]]
        obj_id = record[METADATA_TABLE.columns.obj_id.name]
        face_image = self.get_image_face_without_token(repo_id, obj_id, cluster_center)

        if not face_image:
            return

        filename = f'{face_row_id}.jpg'
        self.save_face(repo_id, face_image, filename)

    def update_face_classify_by_sim(self, repo_id, rows):
        logger.info('update_face_classify_by_sim, repo_id=%s, row_count=%d', repo_id, len(rows))
        clustered_rows, unclustered_rows = get_faces_rows(repo_id, self.metadata_server_api)
        row_id_map = dict()
        for row in rows:
            if row[METADATA_TABLE.columns.face_vectors.name] == VECTOR_DEFAULT_FLAG:
                continue
            face_vectors = b64decode_embeddings(row[METADATA_TABLE.columns.face_vectors.name])

            for item in face_vectors:
                cluster, _ = get_cluster_by_center(item, clustered_rows)
                if cluster:
                    cluster_id = cluster[FACES_TABLE.columns.id.name]
                else:
                    if not unclustered_rows:
                        metadata = self.metadata_server_api.get_metadata(repo_id)
                        tables = metadata.get('tables', [])
                        faces_table_id = next((table['id'] for table in tables if table['name'] == FACES_TABLE.name), None)
                        if not faces_table_id:
                            return
                        result = self.metadata_server_api.insert_rows(repo_id, faces_table_id, [{
                            FACES_TABLE.columns.name.name: UNKNOWN_PEOPLE_NAME,
                        }])
                        face_row_id = result.get('row_ids')[0]
                        unclustered_rows = [{
                            FACES_TABLE.columns.id.name: face_row_id
                        }]
                    cluster_id = unclustered_rows[0][FACES_TABLE.columns.id.name]

                row_id = row[METADATA_TABLE.columns.id.name]
                if row_id not in row_id_map:
                    row_id_map[row_id] = []
                row_id_map[row_id].append(cluster_id)

        if row_id_map:
            self.metadata_server_api.update_link(repo_id, FACES_TABLE.face_link_id, METADATA_TABLE.id, row_id_map)
    
    def ensure_face_vectors(self, repo_id):
        support_formats = tuple(list(SUPPORTED_IMAGE_FORMATS) + [f.upper() for f in SUPPORTED_IMAGE_FORMATS])
        sql = f'SELECT `{METADATA_TABLE.columns.id.name}`, `{METADATA_TABLE.columns.parent_dir.name}`, `{METADATA_TABLE.columns.file_name.name}`, `{METADATA_TABLE.columns.obj_id.name}` FROM `{METADATA_TABLE.name}` WHERE `{METADATA_TABLE.columns.suffix.name}` in {support_formats} AND `{METADATA_TABLE.columns.face_vectors.name}` IS NULL'

        query_result = query_metadata_rows(repo_id, self.metadata_server_api, sql)
        if not query_result:
            return

        self.face_embeddings(repo_id, query_result)
        logger.info('repo %s face vectors is completed', repo_id)

    def face_cluster(self, repo_id):
        logger.info('face_cluster, repo_id=%s', repo_id)
        try:
            from sklearn.cluster import HDBSCAN
            import numpy as np
        except ImportError:
            logger.warning('Package scikit-learn is not installed. ')
            return
        sql = f'SELECT `{METADATA_TABLE.columns.id.name}`, `{METADATA_TABLE.columns.face_vectors.name}`, `{METADATA_TABLE.columns.parent_dir.name}`, `{METADATA_TABLE.columns.file_name.name}`, `{METADATA_TABLE.columns.obj_id.name}` FROM `{METADATA_TABLE.name}` WHERE `{METADATA_TABLE.columns.face_vectors.name}` IS NOT NULL AND `{METADATA_TABLE.columns.face_vectors.name}` <> "{VECTOR_DEFAULT_FLAG}"'
        query_result = query_metadata_rows(repo_id, self.metadata_server_api, sql)
        if not query_result:
            return

        metadata = self.metadata_server_api.get_metadata(repo_id)
        tables = metadata.get('tables', [])
        if not tables:
            return
        faces_table_id = [table['id'] for table in tables if table['name'] == FACES_TABLE.name][0]

        vectors = []
        row_ids = []
        id_to_record = dict()
        for item in query_result:
            row_id = item[METADATA_TABLE.columns.id.name]
            id_to_record[row_id] = item
            face_vectors = b64decode_embeddings(item[METADATA_TABLE.columns.face_vectors.name])
            for face_vector in face_vectors:
                vectors.append(face_vector)
                row_ids.append(row_id)

        clustered_rows, unclustered_rows = get_faces_rows(repo_id, self.metadata_server_api)
        min_cluster_size = get_min_cluster_size(len(vectors))
        if len(vectors) < min_cluster_size:
            clt_labels = [-1] * len(vectors)
        else:
            clt = HDBSCAN(min_cluster_size=min_cluster_size)
            clt.fit(vectors)
            clt_labels = clt.labels_

        cluster_id_to_min_distance = {}
        label_id_to_added_cluster = {}
        label_id_to_updated_cluster = {}
        cluster_id_to_label = {}
        label_ids = np.unique(clt_labels)
        for label_id in label_ids:
            idxs = np.where(clt_labels == label_id)[0]
            related_row_ids = [row_ids[i] for i in idxs]

            if label_id == -1:
                if not unclustered_rows:
                    label_id_to_added_cluster[label_id] = ({
                        FACES_TABLE.columns.name.name: UNKNOWN_PEOPLE_NAME,
                    }, related_row_ids, None)
                else:
                    cluster_id = unclustered_rows[0][FACES_TABLE.columns.id.name]
                    label_id_to_updated_cluster[label_id] = ({}, related_row_ids, cluster_id, None)

                continue

            cluster_center = np.mean([vectors[i] for i in idxs], axis=0)
            face_row = {
                FACES_TABLE.columns.vector.name: b64encode_embeddings(cluster_center.tolist()),
            }
            old_cluster, distance = get_cluster_by_center(cluster_center, clustered_rows)
            if old_cluster:
                cluster_id = old_cluster[FACES_TABLE.columns.id.name]
                old_distance = cluster_id_to_min_distance.get(cluster_id)
                if old_distance:
                    if old_distance > distance:
                        label_id_to_updated_cluster[label_id] = (face_row, related_row_ids, cluster_id, cluster_center)
                        old_label_id = cluster_id_to_label.get(cluster_id)
                        old_cluster_info = label_id_to_updated_cluster.pop(old_label_id)
                        cluster_id_to_min_distance[cluster_id] = distance
                        label_id_to_added_cluster[old_label_id] = (old_cluster_info[0], old_cluster_info[1], old_cluster_info[3])
                    else:
                        label_id_to_added_cluster[label_id] = (face_row, related_row_ids, cluster_center)
                else:
                    label_id_to_updated_cluster[label_id] = (face_row, related_row_ids, cluster_id, cluster_center)
                    cluster_id_to_label[cluster_id] = label_id
                    cluster_id_to_min_distance[cluster_id] = distance
                continue
            label_id_to_added_cluster[label_id] = (face_row, related_row_ids, cluster_center)

        for value in label_id_to_updated_cluster.values():
            face_row, related_row_ids, cluster_id, _ = value
            if face_row:
                face_row[FACES_TABLE.columns.id.name] = cluster_id
                self.metadata_server_api.update_rows(repo_id, faces_table_id, [face_row])
            exist_rows = get_metadata_by_row_ids(repo_id, related_row_ids, self.metadata_server_api)
            row_id_map = {
                cluster_id: [item[METADATA_TABLE.columns.id.name] for item in exist_rows]
            }
            self.metadata_server_api.update_link(repo_id, FACES_TABLE.face_link_id, faces_table_id, row_id_map)

        for value in label_id_to_added_cluster.values():
            face_row, related_row_ids, cluster_center = value
            result = self.metadata_server_api.insert_rows(repo_id, faces_table_id, [face_row])
            face_row_id = result.get('row_ids')[0]
            exist_rows = get_metadata_by_row_ids(repo_id, related_row_ids, self.metadata_server_api)
            row_id_map = {
                face_row_id: [item[METADATA_TABLE.columns.id.name] for item in exist_rows]
            }
            self.metadata_server_api.insert_link(repo_id, FACES_TABLE.face_link_id, faces_table_id, row_id_map)

            if cluster_center is None:
                continue

            # save a cover for new face cluster.
            self.save_cluster_face(repo_id, related_row_ids, row_ids, id_to_record, cluster_center, face_row_id)

    def update_face_cluster(self, repo_id):
        logger.info('Start face clustering in repo %s' % repo_id)
        self.ensure_face_vectors(repo_id)
        self.face_cluster(repo_id)
        logger.info('Finished face clustering in repo %s' % repo_id)

    def update_people_cover_photo(self, repo_id, people_id, obj_id):
        face_image = self.get_image_face_without_token(repo_id,obj_id, center=None)
        filename = f'{people_id}.jpg'
        logger.info('Update cover photo for people %s in repo %s', people_id, repo_id)
        self.save_face(repo_id, face_image, filename, replace=True)

    def recognize_faces_by_obj_ids(self, repo_id, obj_ids):
        logger.info('recognize_faces_by_obj_ids, repo_id=%s, obj_count=%d', repo_id, len(obj_ids))
        query_result = get_metadata_by_obj_ids(repo_id, obj_ids, self.metadata_server_api)
        if not query_result:
            return

        clustered_rows, unclustered_rows = get_faces_rows(repo_id, self.metadata_server_api)
        updated_rows = list()
        row_id_map = dict()
        for row in query_result:
            if row.get(METADATA_TABLE.columns.face_links.name):
                continue

            row_id = row[METADATA_TABLE.columns.id.name]
            if not row.get(METADATA_TABLE.columns.face_vectors.name):
                obj_id = row[METADATA_TABLE.columns.obj_id.name]
                faces = self.app.image_processing_manager.face_embeddings_without_token(repo_id, obj_id) or []
                face_embeddings = [face['embedding'] for face in faces]
                vector = b64encode_embeddings(face_embeddings) if face_embeddings else VECTOR_DEFAULT_FLAG
                updated_rows.append({
                    METADATA_TABLE.columns.id.name: row_id,
                    METADATA_TABLE.columns.face_vectors.name: vector,
                })
            else:
                vector = row[METADATA_TABLE.columns.face_vectors.name]
                face_embeddings = b64decode_embeddings(vector) if vector != VECTOR_DEFAULT_FLAG else []

            for item in face_embeddings:
                cluster, _ = get_cluster_by_center(item, clustered_rows)
                if cluster:
                    cluster_id = cluster[FACES_TABLE.columns.id.name]
                else:
                    cluster_id = unclustered_rows[0][FACES_TABLE.columns.id.name]

                if row_id not in row_id_map:
                    row_id_map[row_id] = []
                row_id_map[row_id].append(cluster_id)

        if updated_rows:
            self.metadata_server_api.update_rows(repo_id, METADATA_TABLE.id, updated_rows)
        if row_id_map:
            self.metadata_server_api.update_link(repo_id, FACES_TABLE.face_link_id, METADATA_TABLE.id, row_id_map)
