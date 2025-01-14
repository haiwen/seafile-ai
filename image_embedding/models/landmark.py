import os
import pickle

import numpy as np
import cv2
import onnx
import onnxruntime

from image_embedding.models.utils import transform, trans_points, estimate_affine_matrix_3d23d, P2sRt, matrix2angle


class Landmark:
    def __init__(self, model_dir, model_file, session):
        self.model_file = model_file
        self.session = session
        find_sub = False
        find_mul = False
        model = onnx.load(self.model_file)
        graph = model.graph
        for nid, node in enumerate(graph.node[:8]):
            if node.name.startswith('Sub') or node.name.startswith('_minus'):
                find_sub = True
            if node.name.startswith('Mul') or node.name.startswith('_mul'):
                find_mul = True
            if nid < 3 and node.name == 'bn_data':
                find_sub = True
                find_mul = True
        if find_sub and find_mul:
            input_mean = 0.0
            input_std = 1.0
        else:
            input_mean = 127.5
            input_std = 128.0
        self.input_mean = input_mean
        self.input_std = input_std
        input_cfg = self.session.get_inputs()[0]
        input_shape = input_cfg.shape
        input_name = input_cfg.name
        self.input_size = tuple(input_shape[2:4][::-1])
        self.input_shape = input_shape
        outputs = self.session.get_outputs()
        output_names = []
        for out in outputs:
            output_names.append(out.name)
        self.input_name = input_name
        self.output_names = output_names
        output_shape = outputs[0].shape
        self.require_pose = False
        if output_shape[1] == 3309:
            self.lmk_dim = 3
            self.lmk_num = 68
            self.mean_lmk = pickle.load(open(os.path.join(model_dir, 'meanshape_68.pkl'), 'rb'))
            self.require_pose = True
        else:
            self.lmk_dim = 2
            self.lmk_num = output_shape[1] // self.lmk_dim
        self.task_name = 'landmark_%dd_%d' % (self.lmk_dim, self.lmk_num)

    def prepare(self, ctx_id):
        if ctx_id < 0:
            self.session.set_providers(['CPUExecutionProvider'])

    def get(self, img, face):
        bbox = face.bbox
        w, h = (bbox[2] - bbox[0]), (bbox[3] - bbox[1])
        center = (bbox[2] + bbox[0]) / 2, (bbox[3] + bbox[1]) / 2
        rotate = 0
        _scale = self.input_size[0] / (max(w, h) * 1.5)
        aimg, M = transform(img, center, self.input_size[0], _scale, rotate)
        input_size = tuple(aimg.shape[0:2][::-1])
        blob = cv2.dnn.blobFromImage(aimg, 1.0 / self.input_std, input_size,
                                     (self.input_mean, self.input_mean, self.input_mean), swapRB=True)
        pred = self.session.run(self.output_names, {self.input_name: blob})[0][0]
        if pred.shape[0] >= 3000:
            pred = pred.reshape((-1, 3))
        else:
            pred = pred.reshape((-1, 2))
        if self.lmk_num < pred.shape[0]:
            pred = pred[self.lmk_num * -1:, :]
        pred[:, 0:2] += 1
        pred[:, 0:2] *= (self.input_size[0] // 2)
        if pred.shape[1] == 3:
            pred[:, 2] *= (self.input_size[0] // 2)

        IM = cv2.invertAffineTransform(M)
        pred = trans_points(pred, IM)
        face[self.task_name] = pred
        if self.require_pose:
            P = estimate_affine_matrix_3d23d(self.mean_lmk, pred)
            _, R, _ = P2sRt(P)
            rx, ry, rz = matrix2angle(R)
            pose = np.array([rx, ry, rz], dtype=np.float32)
            face['pose'] = pose
        return pred
