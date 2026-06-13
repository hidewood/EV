from functools import wraps
from flask_jwt_extended import JWTManager
from flask_jwt_extended import get_jwt, verify_jwt_in_request
from .errors import error

jwt = JWTManager()


@jwt.unauthorized_loader
def handle_missing_token(reason):
    return error(1002, reason)


@jwt.invalid_token_loader
def handle_invalid_token(reason):
    return error(1002, reason)


@jwt.expired_token_loader
def handle_expired_token(jwt_header, jwt_payload):
    return error(1002, "token 已过期")


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        if get_jwt().get("role") != "admin":
            return error(1003)
        return fn(*args, **kwargs)
    return wrapper


def partner_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        if get_jwt().get("role") != "partner":
            return error(1003)
        return fn(*args, **kwargs)
    return wrapper
