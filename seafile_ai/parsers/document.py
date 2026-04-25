import json
from io import BytesIO
from pathlib import Path

import mammoth
from PIL import Image
from pdfminer.high_level import extract_text

from seafile_ai.utils.parse_pptx import get_pptx_text
from seafile_ai.utils.sdoc2md import sdoc2md


def parse_file(file_name, file_content):
    file_ext = Path(file_name).suffix.lower()
    parser_mapping = {
        '.sdoc': lambda x: sdoc2md(json.loads(x.decode())),
        '.md': lambda x: x.decode(),
        '.markdown': lambda x: x.decode(),
        '.docx': docx_to_markdown,
        '.pdf': get_pdf_text,
        '.pptx': get_pptx_text,
    }
    return parser_mapping.get(file_ext, lambda _: '')(file_content)


def docx_to_markdown(file_content):
    result = mammoth.convert_to_markdown(BytesIO(file_content), convert_image=lambda _: [])
    return result.value.replace('\\', '')


def get_pdf_text(file_content):
    return extract_text(BytesIO(file_content))


def get_file_ext(file_name):
    return Path(file_name).suffix.lower()


def is_pdf(file_path):
    return file_path.lower().endswith('.pdf')


def resize_image_binary(image_binary, ext, size):
    ext = 'jpeg' if ext == 'jpg' else ext
    with Image.open(BytesIO(image_binary)) as img:
        img = img.convert('RGB')
        width, height = img.size

        if width <= size or height <= size:
            return image_binary

        if width <= height:
            ratio = size / width
        else:
            ratio = size / height

        new_width = int(width * ratio)
        new_height = int(height * ratio)
        resized_img = img.resize((new_width, new_height), Image.LANCZOS)

        output_buffer = BytesIO()
        resized_img.save(output_buffer, format=ext)
        output_buffer.seek(0)
        return output_buffer.getvalue()
