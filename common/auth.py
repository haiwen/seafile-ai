import jwt


def is_valid_token(auth_header, secret_key):
    auth = auth_header.split()
    if not auth or auth[0].lower() != 'token' or len(auth) != 2:
        return False

    token = auth[1]
    if not token or not secret_key:
        return False

    try:
        jwt.decode(token, secret_key, algorithms=['HS256'])
    except jwt.PyJWTError:
        return False

    return True
