import hashlib
import hmac
import secrets


def generate_api_key() -> tuple[str, str]:
    """Returns (plaintext_key, sha256_hash). Store only the hash."""
    random_bytes = secrets.token_bytes(32)
    key_body = random_bytes.hex()
    plaintext = f"agentis_sk_{key_body}"
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, key_hash


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(key: str, stored_hash: str) -> bool:
    computed = hashlib.sha256(key.encode()).hexdigest()
    return hmac.compare_digest(computed, stored_hash)
