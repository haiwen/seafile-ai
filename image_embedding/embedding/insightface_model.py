import cv2
import insightface
import numpy as np
from sklearn import preprocessing


class InsightfaceModel:
    def __init__(self, model_dir, gpu_id=0, threshold=1.24, det_thresh=0.50):
        self.gpu_id = gpu_id
        self.threshold = threshold
        self.det_thresh = det_thresh

        self.model = insightface.app.FaceAnalysis(root=model_dir, providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
        self.model.prepare(ctx_id=self.gpu_id, det_thresh=self.det_thresh)

    def embedding(self, content):
        embeddings = []
        input_image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), 1)
        faces = self.model.get(input_image)
        for face in faces:
            embedding = np.array(face.embedding).reshape((1, -1))
            embedding = preprocessing.normalize(embedding)
            embeddings.append(embedding.tolist()[0])
        return embeddings
