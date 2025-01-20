import io
import cv2


def get_face_image(image, box):
    height, width, _ = image.shape
    face_height = box[3] - box[1]
    face_width = box[2] - box[0]
    face_size = max(face_height, face_width)
    
    left = max(box[0] - int(face_size * 0.5), 0)
    top = max(box[1] - int(face_size * 0.5), 0)
    right = min(box[2] + int(face_size * 0.5), width)
    bottom = min(box[3] + int(face_size * 0.5), height)
    
    face_img = image[top:bottom, left:right]
    
    # Resize the face image to a square
    face_img = cv2.resize(face_img, (face_size, face_size))
    
    face_img = cv2.cvtColor(face_img, cv2.COLOR_RGB2BGR)
    _, encoded_img = cv2.imencode('.jpg', face_img)
    byte_io = io.BytesIO(encoded_img.tobytes())
    byte_data = byte_io.getvalue()
    return byte_data
