import logging

from flask import request


logger = logging.getLogger(__name__)


def error_response(message, status_code):
    return {'error_msg': message}, status_code


def parse_json_request():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError('Invalid JSON body')
    return data


def parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)
