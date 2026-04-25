from io import BytesIO

from PIL import Image
import pillow_heif
pillow_heif.register_heif_opener()



def resize_image_binary(image_binary):
    img = Image.open(BytesIO(image_binary))
    img = img.convert("RGB")
    width, height = img.size
    if width <= 512 or height <= 512:
        return image_binary

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
