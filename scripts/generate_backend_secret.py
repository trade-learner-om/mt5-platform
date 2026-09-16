import base64
import os
import secrets
import sys


def generate_fernet_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")


def generate_jwt_secret() -> str:
    return secrets.token_urlsafe(48)


if len(sys.argv) != 2:
    raise SystemExit("Usage: generate_backend_secret.py fernet|jwt")

if sys.argv[1] == "fernet":
    print(generate_fernet_key())
elif sys.argv[1] == "jwt":
    print(generate_jwt_secret())
else:
    raise SystemExit("Unknown secret type")
