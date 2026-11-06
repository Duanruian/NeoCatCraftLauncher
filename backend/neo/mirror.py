from __future__ import annotations

import threading
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.sessions import Session


DEFAULT_BMCLAPI_BASE = "https://bmclapi2.bangbang93.com"
DOWNLOAD_SOURCES = {"official", "bmclapi"}
_FALLBACK_STATUS_CODES = {403, 404, 408, 410, 425, 429}
_TIMEOUT = (8, 60)

_lock = threading.RLock()
_enabled = False
_base = DEFAULT_BMCLAPI_BASE
_original_session_request = Session.request
_request_patch_installed = False


def _normalize_base(value: Any) -> str:
    base = str(value or DEFAULT_BMCLAPI_BASE).strip().rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return DEFAULT_BMCLAPI_BASE
    return base


def _mirror_url(url: str) -> str | None:
    if not url or not str(url).lower().startswith(("http://", "https://")):
        return None
    parsed = urlsplit(str(url))
    host = parsed.hostname.lower() if parsed.hostname else ""
    path = parsed.path or "/"

    if host == "resources.download.minecraft.net":
        mirror_path = "/assets" + path
    elif host == "libraries.minecraft.net":
        mirror_path = "/maven" + path
    elif host in {
        "launchermeta.mojang.com",
        "launcher.mojang.com",
        "piston-meta.mojang.com",
        "piston-data.mojang.com",
    }:
        mirror_path = path
    elif host == "maven.minecraftforge.net":
        mirror_path = "/maven" + path
    elif host == "files.minecraftforge.net" and path.startswith("/maven"):
        mirror_path = "/maven" + path.removeprefix("/maven")
    elif host == "meta.fabricmc.net":
        mirror_path = "/fabric-meta" + path
    elif host == "maven.fabricmc.net":
        mirror_path = "/maven" + path
    elif host == "meta.quiltmc.org":
        mirror_path = "/quilt-meta" + path
    elif host == "maven.neoforged.net" and not path.startswith("/api/"):
        mirror_path = "/maven" + path
    else:
        return None

    with _lock:
        base = _base
    return base + mirror_path + (f"?{parsed.query}" if parsed.query else "")


def _should_fallback(response: Any) -> bool:
    status = int(getattr(response, "status_code", 0) or 0)
    return status in _FALLBACK_STATUS_CODES or status >= 500


def _patched_session_request(self: Session, method: str, url: str, **kwargs: Any) -> Any:
    kwargs.setdefault("timeout", _TIMEOUT)
    with _lock:
        enabled = _enabled
    mirrored = _mirror_url(url) if enabled and str(method).upper() == "GET" else None
    if not mirrored:
        return _original_session_request(self, method, url, **kwargs)
    try:
        response = _original_session_request(self, method, mirrored, **kwargs)
    except requests.RequestException:
        return _original_session_request(self, method, url, **kwargs)
    if _should_fallback(response):
        response.close()
        return _original_session_request(self, method, url, **kwargs)
    return response


def install_request_patch() -> None:
    global _request_patch_installed
    with _lock:
        if _request_patch_installed:
            return
        Session.request = _patched_session_request
        _request_patch_installed = True


def configure_download_mirror(config: Any) -> None:
    global _enabled, _base
    source = str(config.get("minecraft_download_source") or "official").strip().lower()
    if source not in DOWNLOAD_SOURCES:
        source = "official"
    base = _normalize_base(config.get("bmclapi_base"))
    with _lock:
        _enabled = source == "bmclapi"
        _base = base


install_request_patch()


__all__ = [
    "DEFAULT_BMCLAPI_BASE",
    "DOWNLOAD_SOURCES",
    "configure_download_mirror",
]
