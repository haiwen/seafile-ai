def parse_json_response(response):
    if response.status_code < 200 or response.status_code >= 400:
        raise ConnectionError(response.status_code, response.text)

    try:
        return response.json()
    except ValueError as error:
        raise ValueError('Invalid JSON response') from error
