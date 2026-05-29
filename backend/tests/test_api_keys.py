from app.auth.api_keys import generate_api_key, hash_api_key, verify_api_key


def test_key_has_correct_prefix():
    key, _ = generate_api_key()
    assert key.startswith("agentis_sk_")


def test_hash_differs_from_key():
    key, key_hash = generate_api_key()
    assert key != key_hash
    assert len(key_hash) == 64  # SHA-256 hex digest


def test_verify_correct_key():
    key, key_hash = generate_api_key()
    assert verify_api_key(key, key_hash) is True


def test_verify_wrong_key():
    _, key_hash = generate_api_key()
    assert verify_api_key("agentis_sk_wrong", key_hash) is False


def test_two_keys_never_equal():
    key1, _ = generate_api_key()
    key2, _ = generate_api_key()
    assert key1 != key2


def test_hash_api_key_is_deterministic():
    key = "agentis_sk_test"
    assert hash_api_key(key) == hash_api_key(key)
