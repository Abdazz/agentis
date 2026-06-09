"""ClamAV virus scanning for file uploads (spec §16.6, Phase 3B).

When ClamAV is unavailable (daemon not running, socket not found), scanning
is skipped and the file is treated as clean — upload flow is never blocked
by an optional security service.
"""
import structlog

log = structlog.get_logger()


def scan_bytes(data: bytes, socket_path: str) -> dict:
    """Scan bytes via ClamAV unix socket.

    Returns:
        {"clean": True, "virus": None} — file is clean
        {"clean": False, "virus": "VirusName"} — virus found
        {"clean": True, "skipped": True} — ClamAV unavailable, scan skipped
    """
    try:
        import clamd
        cd = clamd.ClamdUnixSocket(path=socket_path)
        result = cd.instream(data)
        status, virus_name = next(iter(result.values()))
        if status == "OK":
            return {"clean": True, "virus": None}
        else:
            log.warning("clamav_virus_detected", virus=virus_name)
            return {"clean": False, "virus": virus_name}
    except Exception as e:
        log.warning("clamav_unavailable", error=str(e))
        return {"clean": True, "skipped": True}
