from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any

from .mirror import DEFAULT_BMCLAPI_BASE

APP_NAME = "NeoCatCraftLauncher"
APP_VERSION = "0.2.2"
DEFAULT_PORT = 47821
BUNDLED_CURSEFORGE_API_KEY = "$2a$10$1KoV3Z0Sd0GAwO1g6ptAjuNuEx63qCy5KjHY6bWsMEjuGs9urbWlS"

AZUL_API = "https://api.azul.com/metadata/v1/zulu"
UNIFIED_AUTH_BASE = "https://auth.mc-user.com:233"

DEFAULT_SKIN_SITES: list[dict[str, str]] = [
    {"id": "littleskin", "name": "LittleSkin", "url": "https://littleskin.cn/api/yggdrasil"},
    {"id": "littleskin-global", "name": "LittleSkin 国际", "url": "https://littleskin.cn/api/yggdrasil"},
    {"id": "custom", "name": "自定义皮肤站", "url": ""},
]

SAFE_JVM_ARGS = "-XX:+UseG1GC -Dfile.encoding=UTF-8"
LEGACY_JVM_ARGS = (
    "-XX:+UseG1GC -XX:G1NewSizePercent=20 "
    "-XX:+UnlockExperimentalVMOptions -Dfile.encoding=UTF-8"
)


def _default_minecraft_directory() -> str:
    try:
        import minecraft_launcher_lib

        return minecraft_launcher_lib.utils.get_minecraft_directory()
    except Exception:
        return str(Path.home() / ".minecraft")


def _config_dir() -> Path:
    override = os.environ.get("NEO_CONFIG_DIR")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_NAME


DEFAULT_SETTINGS: dict[str, Any] = {
    "minecraft_directory": _default_minecraft_directory(),
    "java_path": "",
    "memory_mb": 4096,
    "min_memory_mb": 512,
    "jvm_args": SAFE_JVM_ARGS,
    "resolution": {"enabled": False, "width": 1280, "height": 720},
    "microsoft_client_id": os.environ.get("NEO_MS_CLIENT_ID", ""),
    "curseforge_api_key": os.environ.get("NEO_CURSEFORGE_API_KEY") or BUNDLED_CURSEFORGE_API_KEY,
    "preferred_platform": "all",
    "last_version": "",
    "last_loader": "fabric",
    "minecraft_download_source": "official",
    "bmclapi_base": DEFAULT_BMCLAPI_BASE,
    "download_retries": 3,
    "download_timeout": 60,
    "close_animation": True,
    "theme": "ocean",
    "theme_mode": "light",
    "accent_color": "",
    "first_run_done": False,
    "disclaimer_accepted": False,
    "default_isolation": True,
    "active_instance": "",
    "javas_directory": "",
    "java_provider": "zulu",
    "auto_download_java": True,
    "zulu_api": AZUL_API,
    "skin_sites": copy.deepcopy(DEFAULT_SKIN_SITES),
    "unified_auth_base": UNIFIED_AUTH_BASE,
    "unified_server_id": "",
    "authlib_injector_url": "",
}


class Config:
    def __init__(self) -> None:
        self.dir = _config_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.settings_file = self.dir / "settings.json"
        self.accounts_file = self.dir / "accounts.json"
        self._lock = threading.RLock()
        self._settings: dict[str, Any] = copy.deepcopy(DEFAULT_SETTINGS)
        self._accounts: list[dict[str, Any]] = []
        self._active_account: str | None = None
        self._load()
        if self._settings.get("jvm_args") == LEGACY_JVM_ARGS:
            self._settings["jvm_args"] = SAFE_JVM_ARGS
            try:
                self._save_settings()
            except OSError:
                # The in-memory migration still keeps this session launchable
                # when the user configuration directory is read-only.
                pass

    def _load(self) -> None:
        if self.settings_file.is_file():
            try:
                stored = json.loads(self.settings_file.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    self._settings.update(stored)
            except Exception:
                pass
        if not str(self._settings.get("curseforge_api_key") or "").strip():
            self._settings["curseforge_api_key"] = BUNDLED_CURSEFORGE_API_KEY
        if self.accounts_file.is_file():
            try:
                stored = json.loads(self.accounts_file.read_text(encoding="utf-8"))
                self._accounts = list(stored.get("accounts", []))
                self._active_account = stored.get("active")
            except Exception:
                pass

    def _save_settings(self) -> None:
        self.settings_file.write_text(
            json.dumps(self._settings, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _save_accounts(self) -> None:
        payload = {"accounts": self._accounts, "active": self._active_account}
        self.accounts_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @property
    def settings(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._settings)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return copy.deepcopy(self._settings.get(key, default))

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._settings[key] = value
            self._save_settings()

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for key, value in patch.items():
                if key in DEFAULT_SETTINGS:
                    self._settings[key] = value
            self._save_settings()
            return copy.deepcopy(self._settings)

    @property
    def minecraft_directory(self) -> Path:
        path = Path(self.get("minecraft_directory") or _default_minecraft_directory())
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def mods_directory(self) -> Path:
        path = self.minecraft_directory / "mods"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def javas_directory(self) -> Path:
        configured = (self.get("javas_directory") or "").strip()
        path = Path(configured) if configured else self.dir / "javas"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def instances_directory(self) -> Path:
        path = self.minecraft_directory / "instances"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def accounts(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._accounts)

    def public_accounts(self) -> list[dict[str, Any]]:
        result = []
        for account in self.accounts:
            result.append(
                {
                    "uuid": account.get("uuid"),
                    "name": account.get("name"),
                    "type": account.get("type", "offline"),
                    "active": account.get("uuid") == self._active_account,
                    "skin": account.get("skin"),
                    "skin_model": account.get("skin_model") or "classic",
                    "cape": account.get("cape"),
                    "server": account.get("server"),
                    "server_name": account.get("server_name"),
                }
            )
        return result

    def find_account(self, uuid: str) -> dict[str, Any] | None:
        for account in self.accounts:
            if account.get("uuid") == uuid:
                return account
        return None

    def active_account(self) -> dict[str, Any] | None:
        for account in self.accounts:
            if account.get("uuid") == self._active_account:
                return account
        return None

    def set_active_account(self, uuid: str | None) -> None:
        with self._lock:
            self._active_account = uuid
            self._save_accounts()

    def upsert_account(self, account: dict[str, Any]) -> None:
        with self._lock:
            self._accounts = [a for a in self._accounts if a.get("uuid") != account.get("uuid")]
            self._accounts.append(account)
            self._active_account = account.get("uuid")
            self._save_accounts()

    def update_account(self, uuid: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            for account in self._accounts:
                if account.get("uuid") != uuid:
                    continue
                account.update(patch)
                self._save_accounts()
                return copy.deepcopy(account)
        return None

    def remove_account(self, uuid: str) -> None:
        with self._lock:
            self._accounts = [a for a in self._accounts if a.get("uuid") != uuid]
            if self._active_account == uuid:
                self._active_account = self._accounts[0]["uuid"] if self._accounts else None
            self._save_accounts()

    def redirect_uri(self) -> str:
        port = int(os.environ.get("NEO_PORT", DEFAULT_PORT))
        return f"http://localhost:{port}/api/auth/microsoft/callback"
