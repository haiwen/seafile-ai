import io
import cv2


def get_face_image(image, box):
    height, width, _ = image.shape

    left, top, right, bottom = box
    face_width = right - left
    face_height = bottom - top

    face_box_size = int(max(face_width, face_height) * 1.9)

    face_center_x = (left + right) // 2
    face_center_y = (top + bottom) // 2

    half_size = face_box_size // 2
    new_left = max(0, face_center_x - half_size)
    new_top = max(0, face_center_y - half_size)
    new_right = min(width, face_center_x + half_size)
    new_bottom = min(height, face_center_y + half_size)

    face_img = image[new_top:new_bottom, new_left:new_right]
    face_img = cv2.cvtColor(face_img, cv2.COLOR_RGB2BGR)
    _, encoded_img = cv2.imencode('.jpg', face_img)
    byte_io = io.BytesIO(encoded_img.tobytes())
    byte_data = byte_io.getvalue()
    return byte_data
