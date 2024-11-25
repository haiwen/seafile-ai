import cv2
import numpy as np

from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks

from ocr.doc_ocr.utils import order_points, crop_image


class Model:
    def __init__(self):
        self.detection_model = pipeline(Tasks.ocr_detection, model='damo/cv_resnet18_ocr-detection-db-line-level_damo')
        self.recognition_model = pipeline(Tasks.ocr_recognition, model='damo/cv_convnextTiny_ocr-recognition-document_damo')

    def predict(self, content):
        results = []
        input_image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), 1)
        if input_image is None:
            return None

        det_result = self.detection_model(input_image)
        det_result = det_result['polygons']

        for i in range(det_result.shape[0]):
            box = order_points(det_result[i])
            image_crop = crop_image(input_image, box)
            rec_result = self.recognition_model(image_crop)
            if rec_result and rec_result['text']:
                results.append({
                    'text': rec_result['text'],
                    'box': box.tolist()
                })

        return results
