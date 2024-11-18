import io
import cv2


def get_face_image(image, box):
    height, width, _ = image.shape
    face_height = box[3] - box[1]
    face_width = box[2] - box[0]
    left = max(box[0] - int(face_width * 0.25), 0)
    top = max(box[1] - int(face_height * 0.25), 0)
    right = min(box[2] + int(face_width * 0.25), width)
    bottom = min(box[3] + int(face_height * 0.25), height)
    face_img = image[top:bottom, left:right]
    face_img = cv2.cvtColor(face_img, cv2.COLOR_RGB2BGR)
    _, encoded_img = cv2.imencode('.jpg', face_img)
    byte_io = io.BytesIO(encoded_img.tobytes())
    byte_data = byte_io.getvalue()
    return byte_data
