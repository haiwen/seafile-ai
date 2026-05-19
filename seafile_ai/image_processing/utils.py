from io import BytesIO
import base64
from PIL import Image
import pillow_heif

from seafile_ai.repo_metadata.constants import FACES_TABLE
pillow_heif.register_heif_opener()


VECTOR_DEFAULT_FLAG = '0'
FACE_EMBEDDING_DIM = 512
FACES_TMP_DIR = '/tmp'
FACES_SAVE_PATH = '_Internal/Faces'
EMBEDDING_UPDATE_LIMIT = 200
SUPPORTED_IMAGE_FORMATS = ('jpeg', 'jpg', 'heic', 'png', 'bmp', 'tif', 'tiff', 'jfif', 'jpe', 'ppm', 'heic')
def resize_image_binary(image_binary):
    
    img = Image.open(BytesIO(image_binary))
    img = img.convert("RGB")
    width, height = img.size
    if width <= height:
        ratio = 512 / width
    else:
        ratio = 512 / height

    new_width = int(width * ratio)
    new_height = int(height * ratio)
    resized_img = img.resize((new_width, new_height), Image.LANCZOS)

    output_buffer = BytesIO()
    resized_img.save(output_buffer, format='jpeg')
    output_buffer.seek(0)

    return output_buffer.getvalue()

def feature_distance(feature1, feature2):
    import numpy as np
    diff = np.subtract(feature1, feature2)
    dist = np.sum(np.square(diff), 0)
    return dist


def b64encode_embeddings(embeddings):
    import numpy as np
    embedding_array = np.array(embeddings).astype(np.float32)
    encode = base64.b64encode(embedding_array.tobytes())
    return encode.decode('utf-8')


def b64decode_embeddings(encode):
    import numpy as np
    decode = base64.b64decode(encode)
    embedding_array = np.frombuffer(decode, dtype=np.float32)
    face_num = len(embedding_array) // FACE_EMBEDDING_DIM
    embedding = embedding_array.reshape((face_num, FACE_EMBEDDING_DIM)).tolist()
    return embedding


def get_cluster_by_center(center, clusters):
    min_distance = float('inf')
    nearest_cluster = None
    for cluster in clusters:
        vector = cluster.get(FACES_TABLE.columns.vector.name)
        if not vector:
            continue

        vector = b64decode_embeddings(vector)[0]
        distance = feature_distance(center, vector)
        if distance < 1 and distance < min_distance:
            min_distance = distance
            nearest_cluster = cluster
    return nearest_cluster, min_distance

def get_min_cluster_size(faces_num):
    return max(faces_num // 100, 5)
