import glob
import os

import onnxruntime
from image_embedding.models.arcface_onnx import ArcFaceONNX
from image_embedding.models.retinaface import RetinaFace
from image_embedding.models.landmark import Landmark
from image_embedding.models.attribute import Attribute
from image_embedding.models.utils import Face


class Model:
    def __init__(self, model_dir, ctx_id):
        self.model_dir = model_dir
        self.ctx_id = ctx_id
        self.models = {}
        onnx_files = glob.glob(os.path.join(self.model_dir, '*.onnx'))
        onnx_files = sorted(onnx_files)
        for onnx_file in onnx_files:
            model = self.get_model(onnx_file)
            self.models[model.task_name] = model
        self.det_model = self.models['detection']
        self.prepare(self.ctx_id)

    def prepare(self, ctx_id, det_thresh=0.5, det_size=(640, 640)):
        for task_name, model in self.models.items():
            if task_name == 'detection':
                model.prepare(ctx_id, input_size=det_size, det_thresh=det_thresh)
            else:
                model.prepare(ctx_id)

    def get_model(self, onnx_file):
        session = onnxruntime.InferenceSession(onnx_file)
        inputs = session.get_inputs()
        input_cfg = inputs[0]
        input_shape = input_cfg.shape
        outputs = session.get_outputs()

        if len(outputs) >= 5:
            return RetinaFace(model_file=onnx_file, session=session)
        elif input_shape[2] == 192 and input_shape[3] == 192:
            return Landmark(model_dir=self.model_dir, model_file=onnx_file, session=session)
        elif input_shape[2] == 96 and input_shape[3] == 96:
            return Attribute(model_file=onnx_file, session=session)
        elif input_shape[2] == input_shape[3] and input_shape[2] >= 112 and input_shape[2] % 16 == 0:
            return ArcFaceONNX(model_file=onnx_file, session=session)
        else:
            return None

    def get(self, img, max_num=0):
        bboxes, kpss = self.det_model.detect(img, max_num=max_num, metric='default')
        if bboxes.shape[0] == 0:
            return []
        ret = []
        for i in range(bboxes.shape[0]):
            bbox = bboxes[i, 0:4]
            det_score = bboxes[i, 4]
            kps = None
            if kpss is not None:
                kps = kpss[i]
            face = Face(bbox=bbox, kps=kps, det_score=det_score)
            for task_name, model in self.models.items():
                if task_name == 'detection':
                    continue
                model.get(img, face)
            ret.append(face)
        return ret
