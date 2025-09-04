import requests
import json
import logging
import mammoth

from urllib.parse import quote as urlquote
from pathlib import Path
from io import BytesIO
from PIL import Image

from pdfminer.high_level import extract_text

from seafile_ai.config import SEAFILE_SERVER_URL
from seafile_ai.utils.sdoc2md import sdoc2md
from seafile_ai.utils.parse_pptx import get_pptx_text

logger = logging.getLogger(__name__)


def parse_response(response):
    if response.status_code >= 400 or response.status_code < 200:
        raise ConnectionError(response.status_code, response.text)
    else:
        try:
            return response.json()
        except:
            pass


class LLMChatCompletionException(Exception):
    pass


class InvalidWritingTypeException(Exception):
    pass


class FormatNotSupportedException(Exception):
    pass


def gen_file_get_url(token, filename):
    return '%s/files/%s/%s' % (SEAFILE_SERVER_URL.rstrip('/') + '/seafhttp', token, urlquote(filename))


def get_file_by_token(token, filename):
    url = gen_file_get_url(token, filename)
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        raise ConnectionError(response.status_code, response.text)

    return response.content


def get_image_by_token(token, filename):
    url = gen_file_get_url(token, filename)
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        raise ConnectionError(response.status_code, response.text)

    return response.content


def parse_file(file_name, download_token):
    doc = get_file_by_token(download_token, file_name)
    file_ext = Path(file_name).suffix.lower()

    parser_mapping = {
        '.sdoc': lambda x: sdoc2md(json.loads(x.decode())),
        '.md': lambda x: x.decode(),
        '.markdown': lambda x: x.decode(),
        '.docx': docx2md,
        '.pdf': get_pdf_text,
        '.pptx': get_pptx_text
    }

    return parser_mapping.get(file_ext, lambda x: '')(doc)


def docx2md(file):
    ignore_images = lambda _: []
    result = mammoth.convert_to_markdown(BytesIO(file), convert_image=ignore_images)
    return result.value.replace('\\', '')


def get_pdf_text(file):
    text = extract_text(BytesIO(file))
    return text


def get_file_ext(file_name):
    return Path(file_name).suffix.lower()


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


def is_pdf(file_path):
    return file_path.lower().endswith('.pdf')
