from io import BytesIO
from PIL import Image


def resize_image_binary(image_binary, ext, max_size):
    ext = 'jpeg' if ext == 'jpg' else ext
    with BytesIO(image_binary) as f:
        with Image.open(f) as img:
            width, height = img.size
            if width <= max_size and height <= max_size:
                return image_binary, 1

            if width <= height:
                ratio = max_size / width
            else:
                ratio = max_size / height

            new_width = int(width * ratio)
            new_height = int(height * ratio)
            resized_img = img.resize((new_width, new_height), Image.LANCZOS)

            output_buffer = BytesIO()
            resized_img.save(output_buffer, format=ext)
            output_buffer.seek(0)

            return output_buffer.getvalue(), ratio


def resize_text_box(box, ratio):
    return {
        'left': box['left'] // ratio,
        'top': box['top'] // ratio,
        'width': box['width'] // ratio,
        'height': box['height'] // ratio
    }
