import math

import cv2
import numpy as np


def crop_image(img, position):
    position = np.array(position, dtype=np.float32)
    position = position[position[:, 0].argsort()]

    position[:2] = position[:2][position[:2, 1].argsort()]
    position[2:] = position[2:][position[2:, 1].argsort()]

    x1, y1 = position[0]
    x2, y2 = position[2]
    x3, y3 = position[3]
    x4, y4 = position[1]

    img_width = distance((x1 + x4) / 2, (y1 + y4) / 2, (x2 + x3) / 2, (y2 + y3) / 2)
    img_height = distance((x1 + x2) / 2, (y1 + y2) / 2, (x4 + x3) / 2, (y4 + y3) / 2)

    corners = np.array([[x1, y1], [x2, y2], [x4, y4], [x3, y3]], dtype=np.float32)
    corners_trans = np.array([[0, 0], [img_width - 1, 0], [0, img_height - 1], [img_width - 1, img_height - 1]],
                             dtype=np.float32)
    transform = cv2.getPerspectiveTransform(corners, corners_trans)
    dst = cv2.warpPerspective(img, transform, (int(img_width), int(img_height)))
    return dst


def distance(x1, y1, x2, y2):
    return math.sqrt(pow(x1 - x2, 2) + pow(y1 - y2, 2))


def order_points(points):
    arr = np.array(points, dtype=np.float32).reshape(4, 2)
    centroid = np.mean(arr, axis=0)
    theta = np.arctan2(arr[:, 1] - centroid[1], arr[:, 0] - centroid[0])
    sorted_points = arr[np.argsort(theta)]
    if sorted_points[0, 0] > centroid[0]:
        sorted_points = np.roll(sorted_points, shift=1, axis=0)
    return sorted_points
