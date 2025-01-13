import base64

import cv2
import numpy as np
from sklearn import preprocessing

from image_embedding.embedding.utils import get_face_image
from image_embedding.models.model import Model


class FaceEmbeddingModel:
    def __init__(self, model_dir, gpu_id=0):
        self.gpu_id = gpu_id
        self.model = Model(model_dir, self.gpu_id)

    def embedding(self, content, need_face):
        result = []
        input_image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), 1)
        if input_image is None:
            return None

        input_image = cv2.cvtColor(input_image, cv2.COLOR_BGR2RGB)
        faces = self.model.get(input_image)
        for face in faces:
            det_score = face.det_score
            if det_score < 0.7:
                continue

            face_info = {}
            embedding = np.array(face.embedding).reshape((1, -1))
            embedding = preprocessing.normalize(embedding)
            embedding = embedding.tolist()[0]
            face_info['embedding'] = embedding

            if need_face:
                box = face.bbox.astype(np.int64)
                face_image = get_face_image(input_image, box)
                face_info['face'] = base64.b64encode(face_image).decode('utf-8')

            result.append(face_info)

        return result
