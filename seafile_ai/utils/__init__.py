import requests
import json
import logging
import mammoth
import re

from urllib.parse import quote as urlquote
from urllib.parse import urlparse
from pathlib import Path
from io import BytesIO
from PIL import Image

from pdfminer.high_level import extract_text

from seafile_ai.config import SEAFILE_SERVER_URL
from seafile_ai.utils.sdoc2md import sdoc2md
from seafile_ai.utils.parse_pptx import get_pptx_text
from seafobj import fs_mgr

logger = logging.getLogger(__name__)

ZERO_OBJ_ID = '0000000000000000000000000000000000000000'
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
    parsed = urlparse(SEAFILE_SERVER_URL)
    seafile_server_url = f"{parsed.scheme}://{parsed.netloc}"
    return '%s/files/%s/%s' % (seafile_server_url.rstrip('/') + '/seafhttp', token, urlquote(filename))

def get_file_content_by_seafobj(repo_id, obj_id):
    if obj_id == ZERO_OBJ_ID:
        return b''
    f = None
    try:
        f = fs_mgr.load_seafile(repo_id, 1, obj_id)
        b_content = f.get_content()
        if not b_content.strip():
            return b''
        return b_content
    except Exception as e:
        raise Exception('Failed to get file content by obj id: %s' % e)
    finally:
        # MEMORY FIX: Clear SeaFile object's cached content to prevent memory leak
        # The _content field caches the entire file content and is never released
        if f is not None:
            f._content = None
            f.blocks = None


def parse_file(file_name, repo_id, obj_id):
    doc = get_file_content_by_seafobj(repo_id, obj_id)
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

def parse_file_content(file_name, doc):
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


def remove_reference_markers(content):
    return re.sub(r'\[Reference \d+\]', '', content or '')


def remove_sources_content_and_snippets(sources):
    results = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        new_source = dict(source)
        new_source.pop('content', None)
        new_source.pop('snippets', None)
        results.append(new_source)
    return results


def object_to_json_str(obj):
    if isinstance(obj, str):
        return obj
    try:
        return '```json\n' + json.dumps(obj, indent=4, ensure_ascii=False) + '\n```'
    except Exception:
        return str(obj)
