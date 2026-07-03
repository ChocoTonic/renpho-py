"""AES-128-ECB encryption utilities for the Renpho API.

The Renpho cloud API encrypts all request/response payloads using
AES-128-ECB with PKCS7 padding, base64-encoded for transport.
"""

import base64
import json

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from .constants import ENCRYPTION_KEY


def aes_encrypt(plaintext: str, key: str = ENCRYPTION_KEY) -> str:
    """Encrypt a string with AES-128-ECB + PKCS7 padding, return base64."""
    cipher = AES.new(key.encode("utf-8"), AES.MODE_ECB)
    padded = pad(plaintext.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(padded)
    return base64.b64encode(encrypted).decode("utf-8")


def aes_decrypt(encrypted_b64: str, key: str = ENCRYPTION_KEY) -> str:
    """Decrypt a base64 AES-128-ECB + PKCS7 string."""
    cipher = AES.new(key.encode("utf-8"), AES.MODE_ECB)
    encrypted = base64.b64decode(encrypted_b64)
    decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
    return decrypted.decode("utf-8")


def encrypt_request(obj: dict, key: str = ENCRYPTION_KEY) -> dict:
    """Encrypt a request payload into ``{"encryptData": "..."}`` format."""
    serialized = json.dumps(obj, separators=(",", ":"))
    return {"encryptData": aes_encrypt(serialized, key)}


def encrypt_empty_object(key: str = ENCRYPTION_KEY) -> dict:
    """Encrypt an empty JSON object ``{}``."""
    return encrypt_request({}, key)


def encrypt_empty_bytes(key: str = ENCRYPTION_KEY) -> dict:
    """Encrypt an empty byte array (used by some endpoints)."""
    cipher = AES.new(key.encode("utf-8"), AES.MODE_ECB)
    padded = pad(b"", AES.block_size)
    encrypted = cipher.encrypt(padded)
    return {"encryptData": base64.b64encode(encrypted).decode("utf-8")}


def decrypt_response(encrypted_data: str, key: str = ENCRYPTION_KEY):
    """Decrypt the ``data`` field from an API response and parse as JSON."""
    decrypted = aes_decrypt(encrypted_data, key)
    return json.loads(decrypted)
