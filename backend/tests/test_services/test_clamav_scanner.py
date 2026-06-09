import sys
import types
from unittest.mock import MagicMock

import pytest


def _make_fake_clamd(instream_return):
    """Create a fake clamd module with a ClamdUnixSocket that returns instream_return."""
    fake_clamd = types.ModuleType("clamd")
    mock_socket = MagicMock()
    mock_socket.instream.return_value = instream_return
    fake_clamd.ClamdUnixSocket = MagicMock(return_value=mock_socket)
    return fake_clamd


def test_scan_bytes_clean():
    from unittest.mock import patch

    fake_clamd = _make_fake_clamd({b"stream": ("OK", None)})
    with patch.dict("sys.modules", {"clamd": fake_clamd}):
        from app.services.clamav_scanner import scan_bytes
        result = scan_bytes(b"hello world", socket_path="/tmp/fake.ctl")

    assert result["clean"] is True
    assert result["virus"] is None


def test_scan_bytes_infected():
    from unittest.mock import patch

    fake_clamd = _make_fake_clamd({b"stream": ("FOUND", "Eicar-Test-Signature")})
    with patch.dict("sys.modules", {"clamd": fake_clamd}):
        from app.services.clamav_scanner import scan_bytes
        result = scan_bytes(b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR", socket_path="/tmp/fake.ctl")

    assert result["clean"] is False
    assert result["virus"] == "Eicar-Test-Signature"


def test_scan_bytes_clamav_unavailable_returns_skipped():
    from unittest.mock import patch

    fake_clamd = types.ModuleType("clamd")
    fake_clamd.ClamdUnixSocket = MagicMock(side_effect=ConnectionRefusedError("not running"))
    with patch.dict("sys.modules", {"clamd": fake_clamd}):
        from app.services.clamav_scanner import scan_bytes
        result = scan_bytes(b"data", socket_path="/tmp/fake.ctl")

    assert result["clean"] is True
    assert result["skipped"] is True
