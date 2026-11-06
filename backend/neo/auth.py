from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import uuid as uuid_lib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import minecraft_launcher_lib as mll
from mcauth3 import AuthTimeoutError, MCAuthError, MCMSA, OAuthError, XboxAuthError

from .config import Config
from .events import EventBus, make_event

USER_AGENT = "NeoCatCraftLauncher/0.2 (+https://github.com/neocatcraft)"
AUTHLIB_INJECTOR_META = "https://authlib-injector.yushi.moe/artifact/latest.json"
AUTHLIB_INJECTOR_CDN = "https://authlib-injector.yushi.moe"


class AuthError(ValueError):
    pass


def _http(timeout: int = 20) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def _yggdrasil_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return f"HTTP {response.status_code}"
    message = payload.get("errorMessage") or payload.get("error") or ""
    if not message:
        return f"HTTP {response.status_code}"
    return str(message)


class AuthService:
    def __init__(self, config: Config, bus: EventBus) -> None:
        self.config = config
        self.bus = bus
        self._device_pending: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._injector_lock = threading.Lock()

    # ---------- Microsoft ----------

    def microsoft_client_id(self) -> str | None:
        value = (self.config.get("microsoft_client_id") or "").strip()
        if not value:
            return None
        try:
            return str(uuid_lib.UUID(value))
        except ValueError:
            self.bus.log(
                "已忽略旧版或无效的 Microsoft Client ID，使用 mcauth3 内置 Client ID",
                source="auth",
                level="error",
            )
            return None

    def start_microsoft_login(self) -> dict[str, Any]:
        return self.start_microsoft_device_login()

    def start_microsoft_device_login(self) -> dict[str, Any]:
        authenticator = MCMSA(client_id=self.microsoft_client_id())
        try:
            device_data = authenticator.start_auth()
        except MCAuthError as error:
            raise AuthError(f"mcauth3 无法启动设备代码登录: {error}") from error
        except Exception as error:
            raise AuthError(f"mcauth3 网络请求失败: {error}") from error
        flow = {
            "auth": authenticator,
            "device_data": device_data,
            "status": "pending",
            "account": None,
            "error": None,
            "created_at": time.time(),
            "interval": max(3, int(device_data.get("interval") or 5)),
        }
        with self._lock:
            self._device_pending = flow
        threading.Thread(
            target=self._finish_microsoft_device_login,
            args=(flow,),
            daemon=True,
            name="mcauth3-device-login",
        ).start()
        return {
            "status": "pending",
            "user_code": device_data.get("user_code"),
            "verification_uri": device_data.get("verification_uri") or "https://microsoft.com/link",
            "verification_uri_complete": device_data.get("verification_uri_complete"),
            "expires_in": int(device_data.get("expires_in") or 900),
            "interval": flow["interval"],
            "message": device_data.get("message") or "",
            "provider": "mcauth3",
        }

    def _finish_microsoft_device_login(self, flow: dict[str, Any]) -> None:
        try:
            result = flow["auth"].finish_auth(flow["device_data"])
            account = self._account_from_mcauth_result(result, publish=True)
            with self._lock:
                if self._device_pending is flow:
                    flow["status"] = "success"
                    flow["account"] = account
        except AuthTimeoutError as error:
            self._set_device_error(flow, "expired", f"设备代码已过期: {error}")
        except OAuthError as error:
            self._set_device_error(flow, "denied", f"Microsoft 拒绝了登录或代码已失效: {error}")
        except XboxAuthError as error:
            self._set_device_error(flow, "xbox", f"Xbox 验证失败: {error}")
        except MCAuthError as error:
            self._set_device_error(flow, "error", f"mcauth3 验证失败: {error}")
        except Exception as error:
            self._set_device_error(flow, "error", f"mcauth3 登录失败: {error}")

    def _set_device_error(self, flow: dict[str, Any], status: str, message: str) -> None:
        with self._lock:
            if self._device_pending is not flow:
                return
            flow["status"] = status
            flow["error"] = message

    def poll_microsoft_device_login(self) -> dict[str, Any]:
        with self._lock:
            flow = self._device_pending
            if not flow:
                raise AuthError("设备代码登录会话不存在，请重新获取代码")
            status = flow["status"]
            if status == "pending":
                return {"status": "pending", "interval": flow["interval"], "provider": "mcauth3"}
            account = flow.get("account")
            message = flow.get("error")
            self._device_pending = None
        if status == "success" and account:
            return {"status": "success", "account": self.public_account(account), "provider": "mcauth3"}
        return {"status": status, "message": message or "mcauth3 登录未完成", "provider": "mcauth3"}

    def complete_microsoft_login(self, _: str = "") -> dict[str, Any]:
        result = self.poll_microsoft_device_login()
        if result.get("status") == "success":
            return result["account"]
        raise AuthError(result.get("message") or "mcauth3 设备代码登录仍在等待完成")

    def _account_from_mcauth_result(self, result: dict[str, Any], publish: bool = False) -> dict[str, Any]:
        tokens = result.get("tokens") or {}
        profile = result.get("profile") or {}
        access_token = str(tokens.get("minecraft_access_token") or "")
        refresh_token = str(tokens.get("microsoft_refresh_token") or "")
        profile_id = str(profile.get("id") or "")
        profile_name = str(profile.get("name") or "")
        if not access_token or not profile_id or not profile_name:
            raise AuthError("mcauth3 返回的账户令牌或玩家资料不完整")
        skins = profile.get("skins") or []
        account = {
            "uuid": profile_id,
            "name": profile_name,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "type": "microsoft",
            "skin": skins[0].get("url") if skins else None,
            "updated_at": time.time(),
        }
        self.config.upsert_account(account)
        if publish:
            self.bus.publish(make_event("auth.changed", account=self.public_account(account)))
            self.bus.publish(make_event("auth.success", name=account["name"]))
        return account

    def refresh_account(self, account: dict[str, Any]) -> dict[str, Any]:
        if account.get("type") == "microsoft":
            if not account.get("refresh_token"):
                return account
            try:
                result = MCMSA(client_id=self.microsoft_client_id()).refresh_auth(
                    str(account["refresh_token"])
                )
                return self._account_from_mcauth_result(result)
            except MCAuthError as error:
                raise AuthError(f"mcauth3 令牌刷新失败: {error}") from error
            except Exception as error:
                raise AuthError(f"mcauth3 令牌刷新网络错误: {error}") from error
        if account.get("type") in ("authlib", "unified"):
            return self._refresh_yggdrasil(account)
        return account

    # ---------- 第三方皮肤站 / 统一通行证 ----------

    def inspect_server(self, server_url: str) -> dict[str, Any]:
        base = (server_url or "").strip().rstrip("/")
        if not base.lower().startswith("http"):
            raise AuthError("皮肤站地址需要以 http:// 或 https:// 开头")
        try:
            with _http() as client:
                response = client.get(base)
            if response.status_code != 200:
                raise AuthError(f"皮肤站无法访问（HTTP {response.status_code}）")
            payload = response.json()
        except AuthError:
            raise
        except Exception as error:
            raise AuthError(f"皮肤站无法访问: {error}") from error
        meta = payload.get("meta") or {}
        return {
            "url": base,
            "name": meta.get("serverName") or urlparse(base).netloc,
            "implementation": meta.get("implementationName") or "authlib-injector",
            "implementation_version": meta.get("implementationVersion") or "",
            "links": payload.get("links") or {},
            "skin_domains": payload.get("skinDomains") or [],
        }

    def authlib_login(
        self,
        server_url: str,
        username: str,
        password: str,
        server_name: str = "",
    ) -> dict[str, Any]:
        base = (server_url or "").strip().rstrip("/")
        if not base:
            raise AuthError("请填写皮肤站 API 地址")
        name = (username or "").strip()
        secret = password or ""
        if not name or not secret:
            raise AuthError("请填写邮箱与密码")
        client_token = uuid_lib.uuid4().hex
        payload = {
            "username": name,
            "password": secret,
            "clientToken": client_token,
            "agent": {"name": "Minecraft", "version": 1},
            "requestUser": False,
        }
        with _http() as client:
            response = client.post(f"{base}/authserver/authenticate", json=payload)
        if response.status_code == 403:
            raise AuthError("账号或密码错误")
        if response.status_code != 200:
            raise AuthError(f"登录失败: {_yggdrasil_error(response)}")
        data = response.json()
        profile = data.get("selectedProfile") or (data.get("availableProfiles") or [None])[0]
        if not profile:
            raise AuthError("该账号尚未创建 Minecraft 角色，请先在皮肤站创建角色")
        account = {
            "uuid": profile["id"],
            "name": profile["name"],
            "access_token": data.get("accessToken") or "",
            "client_token": data.get("clientToken") or client_token,
            "refresh_token": "",
            "type": "authlib",
            "server": base,
            "server_name": server_name or urlparse(base).netloc,
            "skin": self._fetch_skin(base, profile["id"]),
            "updated_at": time.time(),
        }
        self.config.upsert_account(account)
        self.bus.publish(make_event("auth.changed", account=self.public_account(account)))
        self.bus.publish(make_event("auth.success", name=account["name"]))
        return self.public_account(account)

    def unified_login(self, server_id: str, username: str, password: str) -> dict[str, Any]:
        server_id = (server_id or "").strip()
        if not server_id:
            raise AuthError("请填写统一通行证服务器 ID")
        base = (self.config.get("unified_auth_base") or "https://auth.mc-user.com:233").rstrip("/")
        return self.authlib_login(
            f"{base}/{server_id}",
            username,
            password,
            server_name=f"统一通行证 #{server_id}",
        )

    def _refresh_yggdrasil(self, account: dict[str, Any]) -> dict[str, Any]:
        base = (account.get("server") or "").rstrip("/")
        token = account.get("access_token") or ""
        client_token = account.get("client_token") or ""
        if not base or not token:
            raise AuthError("该账户缺少可刷新的令牌，请重新登录")
        payload = {"accessToken": token, "clientToken": client_token}
        with _http() as client:
            response = client.post(f"{base}/authserver/refresh", json=payload)
        if response.status_code != 200:
            raise AuthError(f"令牌刷新失败: {_yggdrasil_error(response)}")
        data = response.json()
        profile = data.get("selectedProfile") or {}
        updated = dict(account)
        updated.update(
            {
                "access_token": data.get("accessToken") or token,
                "client_token": data.get("clientToken") or client_token,
                "name": profile.get("name") or account.get("name"),
                "uuid": profile.get("id") or account.get("uuid"),
                "updated_at": time.time(),
            }
        )
        self.config.upsert_account(updated)
        return updated

    def _validate_yggdrasil(self, account: dict[str, Any]) -> bool:
        base = (account.get("server") or "").rstrip("/")
        if not base:
            return False
        try:
            with _http(12) as client:
                response = client.post(
                    f"{base}/authserver/validate",
                    json={
                        "accessToken": account.get("access_token") or "",
                        "clientToken": account.get("client_token") or "",
                    },
                )
            return response.status_code == 204
        except Exception:
            return False

    @staticmethod
    def _texture_details(payload: dict[str, Any]) -> dict[str, Any]:
        for prop in payload.get("properties") or []:
            if prop.get("name") != "textures":
                continue
            try:
                raw = base64.b64decode(prop.get("value") or "")
                textures = json.loads(raw).get("textures") or {}
            except Exception:
                continue
            skin = textures.get("SKIN") or {}
            cape = textures.get("CAPE") or {}
            metadata = skin.get("metadata") or {}
            model = str(metadata.get("model") or "classic").lower()
            return {
                "skin": str(skin.get("url") or "") or None,
                "skin_model": "slim" if model == "slim" else "classic",
                "cape": str(cape.get("url") or "") or None,
            }
        return {"skin": None, "skin_model": "classic", "cape": None}

    def _fetch_textures(self, profile_url: str) -> dict[str, Any] | None:
        try:
            with _http(12) as client:
                response = client.get(profile_url)
            if response.status_code != 200:
                return None
            return self._texture_details(response.json())
        except Exception:
            return None

    def _fetch_skin(self, base: str, uuid_value: str) -> str | None:
        details = self._fetch_textures(
            f"{base}/sessionserver/session/minecraft/profile/{uuid_value}"
        )
        return (details or {}).get("skin")

    def skin_preview(self, uuid_value: str) -> dict[str, Any]:
        account = self.config.find_account(uuid_value)
        if account is None:
            raise AuthError("账户不存在，请重新登录")
        if account.get("type") != "microsoft":
            raise AuthError("皮肤预览仅支持已登录的微软正版账户")

        profile_url = (
            "https://sessionserver.mojang.com/session/minecraft/profile/"
            f"{account.get('uuid') or ''}"
        )
        details = self._fetch_textures(profile_url)
        if details and details.get("skin"):
            updated = self.config.update_account(
                uuid_value,
                {
                    "skin": details.get("skin"),
                    "skin_model": details.get("skin_model") or "classic",
                    "cape": details.get("cape"),
                    "skin_updated_at": time.time(),
                },
            )
            if updated is not None:
                account = updated

        if not account.get("skin"):
            raise AuthError("Mojang 未返回该账户的皮肤，可能尚未设置皮肤或当前网络不可用")
        return {
            **self.public_account(account),
            "active": account.get("uuid") == (self.config.active_account() or {}).get("uuid"),
            "cached": details is None or not details.get("skin"),
        }

    # ---------- authlib-injector ----------

    def injector_jar(self) -> Path:
        target = self.config.dir / "libs" / "authlib-injector.jar"
        if target.is_file() and target.stat().st_size > 0:
            return target
        configured = (self.config.get("authlib_injector_url") or "").strip()
        with self._injector_lock:
            if target.is_file() and target.stat().st_size > 0:
                return target
            url = configured
            if not url:
                try:
                    with _http(20) as client:
                        meta = client.get(AUTHLIB_INJECTOR_META).json()
                    url = str(meta.get("download_url") or "")
                    if url.startswith("/"):
                        url = AUTHLIB_INJECTOR_CDN + url
                except Exception as error:
                    raise AuthError(f"获取 authlib-injector 下载地址失败: {error}") from error
            if not url:
                raise AuthError("无法解析 authlib-injector 下载地址")
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_suffix(".jar.part")
            try:
                with _http(120) as client:
                    with client.stream("GET", url) as response:
                        response.raise_for_status()
                        with part.open("wb") as handle:
                            for chunk in response.iter_bytes(262144):
                                handle.write(chunk)
                part.replace(target)
            except Exception as error:
                try:
                    part.unlink(missing_ok=True)
                except Exception:
                    pass
                raise AuthError(f"下载 authlib-injector 失败: {error}") from error
        self.bus.publish(make_event("java.changed"))
        return target

    def authlib_arguments(self, account: dict[str, Any]) -> list[str]:
        server = (account.get("server") or "").strip()
        if account.get("type") not in ("authlib", "unified") or not server:
            return []
        jar = self.injector_jar()
        return [f"-javaagent:{jar}={server}"]

    # ---------- 离线 ----------

    def ensure_valid_account(self, account: dict[str, Any]) -> dict[str, Any]:
        account_type = account.get("type")
        if account_type == "microsoft":
            if time.time() - float(account.get("updated_at") or 0) < 3000:
                return account
            try:
                return self.refresh_account(account)
            except Exception as error:
                raise AuthError(f"账户令牌刷新失败，请重新登录: {error}") from error
        if account_type in ("authlib", "unified"):
            if self._validate_yggdrasil(account):
                return account
            try:
                return self._refresh_yggdrasil(account)
            except Exception as error:
                raise AuthError(f"统一认证令牌已失效，请重新登录: {error}") from error
        return account

    def offline_login(self, username: str) -> dict[str, Any]:
        name = (username or "").strip()
        if not 3 <= len(name) <= 16:
            raise AuthError("离线用户名长度需在 3-16 个字符之间")
        if not all(char.isalnum() or char == "_" for char in name):
            raise AuthError("离线用户名只能包含字母、数字和下划线")

        digest = bytearray(hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest())
        digest[6] = (digest[6] & 0x0F) | 0x30
        digest[8] = (digest[8] & 0x3F) | 0x80
        account = {
            "uuid": str(uuid_lib.UUID(bytes=bytes(digest))),
            "name": name,
            "access_token": "0",
            "refresh_token": "",
            "type": "offline",
            "skin": None,
            "updated_at": time.time(),
        }
        self.config.upsert_account(account)
        self.bus.publish(make_event("auth.changed", account=self.public_account(account)))
        return self.public_account(account)

    def logout(self, uuid: str | None = None) -> None:
        target = uuid or (self.config.active_account() or {}).get("uuid")
        if target:
            self.config.remove_account(target)
        self.bus.publish(make_event("auth.changed", account=None))

    @staticmethod
    def public_account(account: dict[str, Any]) -> dict[str, Any]:
        type_labels = {
            "microsoft": "微软正版",
            "offline": "离线账户",
            "authlib": "第三方皮肤站",
            "unified": "统一通行证",
        }
        account_type = account.get("type", "offline")
        return {
            "uuid": account.get("uuid"),
            "name": account.get("name"),
            "type": account_type,
            "type_label": type_labels.get(account_type, account_type),
            "skin": account.get("skin"),
            "skin_model": account.get("skin_model") or "classic",
            "cape": account.get("cape"),
            "server": account.get("server"),
            "server_name": account.get("server_name"),
            "active": True,
        }
