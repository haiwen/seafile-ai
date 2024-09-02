from io import BytesIO

from PIL import Image


def resize_image_binary(image_binary, ext):
    ext = 'jpeg' if ext == 'jpg' else ext
    with BytesIO(image_binary) as f:
        with Image.open(f) as img:
            width, height = img.size

            if width <= height:
                ratio = 600 / width
            else:
                ratio = 600 / height

            new_width = int(width * ratio)
            new_height = int(height * ratio)
            resized_img = img.resize((new_width, new_height), Image.LANCZOS)

            output_buffer = BytesIO()
            resized_img.save(output_buffer, format=ext)
            output_buffer.seek(0)

            return output_buffer.getvalue()
