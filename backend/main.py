from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from neo.auth import AuthError, AuthService
from neo.content import ContentService
from neo.config import APP_NAME, APP_VERSION, DEFAULT_PORT, DEFAULT_SKIN_SITES, Config
from neo.events import EventBus, make_event
from neo.instances import InstanceError, InstanceManager
from neo.java_manager import AVAILABLE_MAJORS, JAVA_LABELS, JavaError, JavaManager, java_major_for_minecraft
from neo.launcher import LauncherService
from neo.mirror import configure_download_mirror
from neo.modpacks import ModpackError, ModpackService
from neo.mods.platform import ModPlatformError, ModService
from neo.tasks import TaskManager

config = Config()
configure_download_mirror(config)
bus = EventBus()
tasks = TaskManager(bus)
instances = InstanceManager(config)
java = JavaManager(config, tasks, bus)
auth = AuthService(config, bus)
launcher = LauncherService(config, tasks, bus, instances, java, auth)
mods = ModService(config, tasks, bus, instances)
content = ContentService(config, tasks, bus, instances)
modpacks = ModpackService(config, tasks, bus, instances, java)

ROOT = Path(__file__).resolve().parent
_frontend_root = ROOT.parent / "frontend"
FRONTEND = _frontend_root / "dist" if (_frontend_root / "dist").is_dir() else _frontend_root


@asynccontextmanager
async def lifespan(_: FastAPI):
    bus.bind_loop(asyncio.get_running_loop())
    bus.log(f"{APP_NAME} 后端已就绪（minecraft-launcher-lib {launcher.library_version()}）", source="system")
    yield
    launcher.stop_all()


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def fail(error: Exception, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": str(error)}, status_code=status)


def public_settings() -> dict[str, Any]:
    payload = config.settings
    payload["microsoft_client_id"] = payload.get("microsoft_client_id") or ""
    payload["curseforge_api_key_set"] = bool((payload.get("curseforge_api_key") or "").strip())
    payload.pop("curseforge_api_key", None)
    payload["minecraft_directory"] = str(config.minecraft_directory)
    payload["javas_directory"] = str(config.javas_directory)
    payload["instances_directory"] = str(config.instances_directory)
    payload["skin_sites"] = payload.get("skin_sites") or DEFAULT_SKIN_SITES
    return payload


# ---------- 基础 ----------


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "name": APP_NAME,
        "version": APP_VERSION,
        "library": launcher.library_version(),
        "minecraft_directory": str(config.minecraft_directory),
        "mods_directory": str(config.mods_directory),
        "javas_directory": str(config.javas_directory),
        "instances_directory": str(config.instances_directory),
        "config_dir": str(config.dir),
        "port": int(os.environ.get("NEO_PORT", DEFAULT_PORT)),
        "pid": os.getpid(),
        "time": time.time(),
    }


@app.get("/api/app/bootstrap")
def bootstrap() -> dict[str, Any]:
    active = config.active_account()
    resolved = instances.resolve(None)
    return {
        "ok": True,
        "name": APP_NAME,
        "version": APP_VERSION,
        "settings": public_settings(),
        "first_run_done": bool(config.get("first_run_done")),
        "disclaimer_accepted": bool(config.get("disclaimer_accepted")),
        "accounts": config.public_accounts(),
        "active_account": active.get("uuid") if active else None,
        "instances": instances.list(),
        "active_instance": resolved["id"] if resolved else None,
        "java": {
            "available_majors": [{"major": major, "label": JAVA_LABELS.get(major, f"Java {major}")} for major in AVAILABLE_MAJORS],
            "installed": java.managed(),
            "system": java.system(),
        },
        "tasks": tasks.list(),
    }


@app.post("/api/app/first-run")
def finish_first_run(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    if payload.get("disclaimer_accepted"):
        config.set("disclaimer_accepted", True)
    config.set("first_run_done", True)
    bus.publish(make_event("settings.changed"))
    return {"first_run_done": True, "disclaimer_accepted": bool(config.get("disclaimer_accepted"))}


@app.post("/api/app/disclaimer")
def accept_disclaimer() -> dict[str, Any]:
    config.set("disclaimer_accepted", True)
    return {"disclaimer_accepted": True}


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    return public_settings()


@app.put("/api/settings")
def put_settings(patch: dict[str, Any] = Body(...)) -> dict[str, Any]:
    config.update_settings(patch)
    configure_download_mirror(config)
    bus.publish(make_event("settings.changed"))
    if "minecraft_directory" in patch:
        bus.publish(make_event("versions.changed"))
        bus.publish(make_event("instances.changed"))
    return public_settings()


@app.get("/api/tasks")
def list_tasks() -> list[dict[str, Any]]:
    return tasks.list()


@app.get("/api/events")
async def events() -> StreamingResponse:
    queue = bus.subscribe()

    async def stream():
        try:
            yield f"data: {json.dumps(make_event('hello', account=None, tasks=tasks.list()), ensure_ascii=False)}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- 实例 ----------


@app.get("/api/instances")
def list_instances() -> dict[str, Any]:
    active = instances.resolve(None)
    return {"instances": instances.list(), "active": active["id"] if active else None}


@app.post("/api/instances")
def create_instance(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        result = launcher.provision_instance(payload)
        return JSONResponse(result)
    except InstanceError as error:
        return fail(error)


@app.get("/api/instances/{instance_id}")
def get_instance(instance_id: str) -> JSONResponse:
    instance = instances.get(instance_id)
    if instance is None:
        return fail(InstanceError(f"实例不存在: {instance_id}"), 404)
    payload = instances.snapshot(instance)
    payload["java"] = java.resolve(instance)
    payload["required_java"] = java_major_for_minecraft(instance.get("mc_version") or "")
    return JSONResponse(payload)


@app.patch("/api/instances/{instance_id}")
def update_instance(instance_id: str, patch: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        updated = instances.update(instance_id, patch)
        bus.publish(make_event("instances.changed"))
        return JSONResponse(updated)
    except InstanceError as error:
        return fail(error, 404)


@app.delete("/api/instances/{instance_id}")
def delete_instance(instance_id: str, delete_files: bool = False) -> JSONResponse:
    try:
        result = instances.delete(instance_id, delete_files)
        bus.publish(make_event("instances.changed"))
        return JSONResponse(result)
    except InstanceError as error:
        return fail(error, 404)


@app.post("/api/instances/{instance_id}/duplicate")
def duplicate_instance(instance_id: str, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    try:
        created = instances.duplicate(instance_id, payload.get("name") or None)
        bus.publish(make_event("instances.changed"))
        return JSONResponse(created)
    except InstanceError as error:
        return fail(error, 404)


@app.post("/api/instances/{instance_id}/repair")
def repair_instance(instance_id: str) -> JSONResponse:
    try:
        return JSONResponse(launcher.repair_instance(instance_id))
    except InstanceError as error:
        return fail(error, 404)


@app.post("/api/instances/{instance_id}/select")
def select_instance(instance_id: str) -> JSONResponse:
    if instances.get(instance_id) is None:
        return fail(InstanceError("实例不存在"), 404)
    config.set("active_instance", instance_id)
    bus.publish(make_event("instances.changed"))
    return JSONResponse({"active": instance_id})


INSTANCE_SUBDIRS = ("mods", "saves", "logs", "screenshots", "resourcepacks", "shaderpacks", "datapacks", "config")


@app.post("/api/instances/{instance_id}/open")
def open_instance_folder(instance_id: str, sub: str = "") -> JSONResponse:
    instance = instances.get(instance_id)
    if instance is None:
        return fail(InstanceError("实例不存在"), 404)
    folder = instances.directory_of(instance)
    if sub in INSTANCE_SUBDIRS:
        folder = folder / sub
        folder.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(folder))
    return JSONResponse({"directory": str(folder)})


def _safe_child(root: Path, name: str) -> Path | None:
    try:
        candidate = (root / name).resolve()
        candidate.relative_to(root.resolve())
    except Exception:
        return None
    return candidate


@app.get("/api/instances/{instance_id}/saves")
def list_saves(instance_id: str) -> JSONResponse:
    instance = instances.get(instance_id)
    if instance is None:
        return fail(InstanceError("实例不存在"), 404)
    root = instances.directory_of(instance) / "saves"
    root.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        size = 0
        region = child / "region"
        try:
            for entry in (region.iterdir() if region.is_dir() else []):
                size += entry.stat().st_size
        except Exception:
            pass
        items.append(
            {
                "name": child.name,
                "directory": str(child),
                "size": size,
                "modified": child.stat().st_mtime,
            }
        )
    items.sort(key=lambda item: -float(item["modified"]))
    return JSONResponse({"directory": str(root), "count": len(items), "saves": items})


@app.get("/api/instances/{instance_id}/logs")
def list_logs(instance_id: str) -> JSONResponse:
    instance = instances.get(instance_id)
    if instance is None:
        return fail(InstanceError("实例不存在"), 404)
    root = instances.directory_of(instance)
    items: list[dict[str, Any]] = []
    for kind, folder in (("log", root / "logs"), ("crash", root / "crash-reports")):
        if not folder.is_dir():
            continue
        for child in folder.iterdir():
            if child.is_file() and child.suffix.lower() in {".log", ".txt"}:
                try:
                    stat = child.stat()
                except Exception:
                    continue
                items.append(
                    {
                        "name": child.name,
                        "kind": kind,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    }
                )
    items.sort(key=lambda item: -float(item["modified"]))
    return JSONResponse({"directory": str(root), "logs": items})


@app.get("/api/instances/{instance_id}/logs/{name}")
def read_log(instance_id: str, name: str, lines: int = 300) -> JSONResponse:
    instance = instances.get(instance_id)
    if instance is None:
        return fail(InstanceError("实例不存在"), 404)
    root = instances.directory_of(instance)
    target = None
    for folder in (root / "logs", root / "crash-reports"):
        child = _safe_child(folder, name)
        if child and child.is_file():
            target = child
            break
    if target is None:
        return fail(InstanceError("日志文件不存在"), 404)
    try:
        content = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as error:
        return fail(RuntimeError(f"读取日志失败: {error}"), 500)
    limit = max(20, min(int(lines or 300), 2000))
    tail = content[-limit:]
    return JSONResponse({"name": target.name, "content": "\n".join(tail), "truncated": len(content) > len(tail)})


# ---------- 版本 ----------


@app.get("/api/versions")
def versions(force: bool = False) -> dict[str, Any]:
    try:
        return {"available": launcher.available_versions(force), "installed": launcher.installed_versions()}
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"获取版本列表失败: {error}")


@app.post("/api/versions/install")
def install_version(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    version_id = (payload.get("version") or "").strip()
    if not version_id:
        raise HTTPException(status_code=400, detail="缺少 version")
    return launcher.install_version(version_id, payload.get("instance_id") or None)


# ---------- 加载器 ----------


@app.get("/api/loaders")
def loaders() -> list[dict[str, str]]:
    return launcher.loader_list()


@app.get("/api/loaders/{loader}/minecraft-versions")
def loader_minecraft_versions(loader: str, stable_only: bool = True) -> dict[str, Any]:
    try:
        return {"loader": loader, "versions": launcher.loader_minecraft_versions(loader, stable_only)}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.get("/api/loaders/{loader}/versions")
def loader_versions(loader: str, minecraft_version: str = Query(...)) -> dict[str, Any]:
    try:
        return launcher.loader_versions(loader, minecraft_version)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.post("/api/loaders/inspect-jar")
def inspect_loader_jar(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    installer_path = str(payload.get("path") or "").strip()
    if not installer_path:
        return fail(ValueError("缺少安装包路径"))
    try:
        return JSONResponse(launcher.inspect_loader_jar(installer_path))
    except Exception as error:
        return fail(error, 400)


@app.post("/api/loaders/install")
def install_loader(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    loader = (payload.get("loader") or "").strip()
    minecraft_version = (payload.get("minecraft_version") or "").strip()
    if not loader or not minecraft_version:
        raise HTTPException(status_code=400, detail="缺少 loader 或 minecraft_version")
    try:
        return launcher.install_loader(
            loader,
            minecraft_version,
            payload.get("loader_version") or None,
            payload.get("instance_id") or None,
            payload.get("installer_path") or None,
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


# ---------- Java ----------


@app.get("/api/java")
def java_info(force: bool = False) -> dict[str, Any]:
    return {
        "managed": java.managed(),
        "system": java.system(force),
        "all": java.all_java(force),
        "available": [{"major": major, "label": JAVA_LABELS.get(major, f"Java {major}")} for major in AVAILABLE_MAJORS],
        "directory": str(config.javas_directory),
    }


@app.get("/api/java/resolve")
def java_resolve(mc_version: str = "", instance_id: str = "") -> JSONResponse:
    instance = instances.get(instance_id) if instance_id else None
    if instance is None and mc_version:
        instance = {"mc_version": mc_version}
    resolved = java.resolve(instance)
    return JSONResponse(
        {
            "resolved": resolved,
            "required": java_major_for_minecraft(mc_version or (instance or {}).get("mc_version") or ""),
        }
    )


@app.post("/api/java/install")
def java_install(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        major = int(payload.get("major") or 0)
    except Exception:
        return fail(JavaError("无效的 Java 版本"))
    if major <= 0:
        return fail(JavaError("无效的 Java 版本"))
    return JSONResponse(java.install(major))


@app.post("/api/java/ensure")
def java_ensure(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    mc_version = str(payload.get("mc_version") or "").strip()
    instance = instances.get(str(payload.get("instance_id") or "")) if payload.get("instance_id") else None
    if not mc_version and instance:
        mc_version = instance.get("mc_version") or ""
    if not mc_version:
        return fail(JavaError("缺少 mc_version"))
    try:
        return JSONResponse({"resolved": java.ensure(mc_version, instance)})
    except Exception as error:
        return fail(error, 502)


@app.post("/api/java/open-folder")
def open_java_folder() -> JSONResponse:
    folder = config.javas_directory
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(folder))
    return JSONResponse({"directory": str(folder)})


# ---------- 账户 ----------


@app.get("/api/auth/accounts")
def accounts() -> dict[str, Any]:
    active = config.active_account()
    return {"accounts": config.public_accounts(), "active_uuid": active.get("uuid") if active else None}


@app.get("/api/auth/accounts/{uuid_value}/skin")
def account_skin_preview(uuid_value: str) -> JSONResponse:
    try:
        return JSONResponse(auth.skin_preview(uuid_value))
    except AuthError as error:
        return fail(error, 404)
    except Exception as error:
        return fail(RuntimeError(f"获取正版皮肤失败: {error}"), 502)


@app.get("/api/auth/servers")
def auth_servers() -> dict[str, Any]:
    return {
        "skin_sites": config.get("skin_sites") or DEFAULT_SKIN_SITES,
        "unified_base": config.get("unified_auth_base"),
        "unified_server_id": config.get("unified_server_id"),
    }


@app.post("/api/auth/servers/inspect")
def inspect_server(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    url = str(payload.get("url") or "").strip()
    if not url:
        return fail(AuthError("缺少皮肤站地址"))
    try:
        return JSONResponse(auth.inspect_server(url))
    except Exception as error:
        return fail(RuntimeError(f"无法连接该皮肤站: {error}"), 502)


@app.post("/api/auth/microsoft/start")
def microsoft_start() -> dict[str, Any]:
    try:
        return auth.start_microsoft_login()
    except AuthError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.post("/api/auth/microsoft/device/start")
def microsoft_device_start() -> JSONResponse:
    try:
        return JSONResponse(auth.start_microsoft_device_login())
    except AuthError as error:
        return fail(error, 400)
    except Exception as error:
        return fail(RuntimeError(f"启动 Microsoft 设备代码登录失败: {error}"), 502)


@app.post("/api/auth/microsoft/device/poll")
def microsoft_device_poll() -> JSONResponse:
    try:
        return JSONResponse(auth.poll_microsoft_device_login())
    except AuthError as error:
        return fail(error, 400)
    except Exception as error:
        return fail(RuntimeError(f"Microsoft 登录状态检查失败: {error}"), 502)


@app.post("/api/auth/microsoft/complete")
def microsoft_complete(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        return auth.complete_microsoft_login(payload.get("code") or payload.get("url") or "")
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"登录失败: {error}")


CALLBACK_PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>NeoCatCraftLauncher 登录</title>
<style>
body{margin:0;height:100vh;display:grid;place-items:center;background:#0d1117;color:#e6edf3;
font-family:"Segoe UI","Microsoft YaHei",sans-serif}
.card{padding:32px 40px;border-radius:16px;background:#161b22;border:1px solid #30363d;text-align:center}
h1{font-size:18px;margin:0 0 8px;font-weight:600}
p{margin:0;color:#8b949e;font-size:14px}
</style></head><body><div class="card"><h1>%s</h1><p>%s</p></div></body></html>"""


@app.get("/api/auth/microsoft/callback", response_class=HTMLResponse)
def microsoft_callback(code: str = "", error: str = "", error_description: str = "") -> HTMLResponse:
    if error:
        return HTMLResponse(CALLBACK_PAGE % ("登录失败", error_description or error), status_code=400)
    if not code:
        return HTMLResponse(CALLBACK_PAGE % ("缺少授权码", "请回到启动器重新发起登录"), status_code=400)
    try:
        account = auth.complete_microsoft_login(code)
        return HTMLResponse(CALLBACK_PAGE % ("登录成功", f"欢迎回来，{account.get('name')}。可以关闭此页面了。"))
    except Exception as exc:
        return HTMLResponse(CALLBACK_PAGE % ("登录失败", str(exc)), status_code=400)


@app.post("/api/auth/offline")
def offline_login(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        account = auth.offline_login(payload.get("username") or "")
        bus.publish(make_event("auth.changed", account=None))
        return JSONResponse(account)
    except AuthError as error:
        return fail(error)


@app.post("/api/auth/authlib")
def authlib_login(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        account = auth.authlib_login(
            str(payload.get("server") or ""),
            str(payload.get("username") or ""),
            str(payload.get("password") or ""),
            str(payload.get("server_name") or ""),
        )
        bus.publish(make_event("auth.changed", account=None))
        return JSONResponse(account)
    except Exception as error:
        return fail(error)


@app.post("/api/auth/unified")
def unified_login(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        account = auth.unified_login(
            str(payload.get("server_id") or ""),
            str(payload.get("username") or ""),
            str(payload.get("password") or ""),
        )
        bus.publish(make_event("auth.changed", account=None))
        return JSONResponse(account)
    except Exception as error:
        return fail(error)


@app.post("/api/auth/select")
def select_account(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    uuid_value = payload.get("uuid")
    if uuid_value is not None:
        config.set_active_account(str(uuid_value))
    bus.publish(make_event("auth.changed", account=None))
    return {"accounts": config.public_accounts()}


@app.delete("/api/auth/accounts/{uuid_value}")
def delete_account(uuid_value: str) -> dict[str, Any]:
    auth.logout(uuid_value)
    return {"accounts": config.public_accounts()}


# ---------- 模组 ----------


@app.get("/api/mods")
def scan_mods(instance_id: str = "") -> dict[str, Any]:
    instance = instances.get(instance_id) if instance_id else instances.resolve(None)
    report = mods.scan(instance["id"] if instance else None)
    report["loader"] = (instance or {}).get("loader") or config.get("last_loader")
    report["mc_version"] = (instance or {}).get("mc_version")
    report["instance_id"] = instance["id"] if instance else None
    return report


@app.get("/api/mods/platforms")
def mod_platforms() -> list[dict[str, Any]]:
    return mods.platform_status()


@app.get("/api/mods/search")
def search_mods(
    platform: str = "modrinth",
    query: str = "",
    minecraft_version: str = "",
    loader: str = "",
    limit: int = 20,
    offset: int = 0,
) -> JSONResponse:
    try:
        payload = mods.search(platform, query, minecraft_version or None, loader or None, limit, offset)
        return JSONResponse(payload)
    except ModPlatformError as error:
        return fail(error)
    except Exception as error:
        return fail(RuntimeError(f"搜索失败: {error}"), 502)


@app.get("/api/mods/versions")
def mod_versions(
    platform: str = "modrinth",
    project_id: str = Query(...),
    minecraft_version: str = "",
    loader: str = "",
) -> JSONResponse:
    try:
        return JSONResponse(mods.versions(platform, project_id, minecraft_version or None, loader or None))
    except ModPlatformError as error:
        return fail(error)
    except Exception as error:
        return fail(RuntimeError(f"获取版本失败: {error}"), 502)


@app.get("/api/mods/dependencies")
def mod_dependencies(
    platform: str = "modrinth",
    project_id: str = Query(...),
    version_id: str = "",
    minecraft_version: str = "",
    loader: str = "",
    instance_id: str = "",
) -> JSONResponse:
    try:
        return JSONResponse(
            mods.inspect_dependencies(
                platform,
                project_id,
                version_id or None,
                minecraft_version or None,
                loader or None,
                instance_id or None,
            )
        )
    except ModPlatformError as error:
        return fail(error)
    except Exception as error:
        return fail(RuntimeError(f"获取前置信息失败: {error}"), 502)


@app.post("/api/mods/install")
def install_mod(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    platform = payload.get("platform") or "modrinth"
    project_id = str(payload.get("project_id") or "").strip()
    if not project_id:
        return fail(ValueError("缺少 project_id"))
    try:
        result = mods.install(
            platform,
            project_id,
            str(payload["version_id"]) if payload.get("version_id") else None,
            payload.get("minecraft_version") or None,
            payload.get("loader") or None,
            bool(payload.get("with_dependencies", False)),
            bool(payload.get("enabled", True)),
            payload.get("instance_id") or None,
            [
                str(item)
                for item in (payload.get("dependency_project_ids") or [])
                if str(item).strip()
            ],
        )
        return JSONResponse(result)
    except ModPlatformError as error:
        return fail(error)
    except Exception as error:
        return fail(RuntimeError(f"安装失败: {error}"), 502)


@app.post("/api/mods/toggle")
def toggle_mod(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        return JSONResponse(mods.toggle(str(payload.get("file") or ""), payload.get("instance_id") or None))
    except ModPlatformError as error:
        return fail(error)


@app.delete("/api/mods/file")
def delete_mod(file: str = Query(...), instance_id: str = "") -> JSONResponse:
    try:
        return JSONResponse(mods.delete(file, instance_id or None))
    except ModPlatformError as error:
        return fail(error)


@app.post("/api/mods/open-folder")
def open_mods_folder(instance_id: str = "") -> JSONResponse:
    instance = instances.get(instance_id) if instance_id else instances.resolve(None)
    folder = instances.mods_directory_of(instance) if instance else config.mods_directory
    if os.name == "nt":
        os.startfile(str(folder))
    return JSONResponse({"directory": str(folder)})


# ---------- 资源包 / 光影 / 数据包 ----------


@app.get("/api/content/search")
def search_content(
    kind: str = "resourcepack",
    platform: str = "all",
    query: str = "",
    minecraft_version: str = "",
    limit: int = 20,
    offset: int = 0,
) -> JSONResponse:
    try:
        return JSONResponse(
            content.search(
                kind,
                platform,
                query,
                minecraft_version or None,
                limit,
                offset,
            )
        )
    except ModPlatformError as error:
        return fail(error)
    except Exception as error:
        return fail(RuntimeError(f"搜索失败: {error}"), 502)


@app.get("/api/content/versions")
def content_versions(
    kind: str = Query(...),
    platform: str = Query(...),
    project_id: str = Query(...),
    minecraft_version: str = "",
) -> JSONResponse:
    try:
        return JSONResponse(
            content.versions(kind, platform, project_id, minecraft_version or None)
        )
    except ModPlatformError as error:
        return fail(error)
    except Exception as error:
        return fail(RuntimeError(f"获取版本失败: {error}"), 502)


@app.get("/api/content/local")
def list_local_content(
    kind: str = "resourcepack",
    instance_id: str = "",
    world: str = "",
) -> JSONResponse:
    try:
        return JSONResponse(content.scan(kind, instance_id or None, world or None))
    except ModPlatformError as error:
        return fail(error)


@app.post("/api/content/install")
def install_content(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        return JSONResponse(
            content.install(
                str(payload.get("kind") or ""),
                str(payload.get("platform") or ""),
                str(payload.get("project_id") or ""),
                str(payload.get("version_id")) if payload.get("version_id") else None,
                payload.get("minecraft_version") or None,
                payload.get("instance_id") or None,
                payload.get("world") or None,
            )
        )
    except ModPlatformError as error:
        return fail(error)
    except Exception as error:
        return fail(RuntimeError(f"安装失败: {error}"), 502)


@app.post("/api/content/toggle")
def toggle_content(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        return JSONResponse(
            content.toggle(
                str(payload.get("kind") or ""),
                str(payload.get("file") or ""),
                payload.get("instance_id") or None,
                payload.get("world") or None,
            )
        )
    except ModPlatformError as error:
        return fail(error)


@app.delete("/api/content/file")
def delete_content(
    kind: str = Query(...),
    file: str = Query(...),
    instance_id: str = "",
    world: str = "",
) -> JSONResponse:
    try:
        return JSONResponse(
            content.delete(kind, file, instance_id or None, world or None)
        )
    except ModPlatformError as error:
        return fail(error)


@app.post("/api/content/open-folder")
def open_content_folder(payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    try:
        folder = content.directory(
            str(payload.get("kind") or "resourcepack"),
            payload.get("instance_id") or None,
            payload.get("world") or None,
        )
        if os.name == "nt":
            os.startfile(str(folder))
        return JSONResponse({"directory": str(folder)})
    except ModPlatformError as error:
        return fail(error)


# ---------- 整合包 ----------


@app.get("/api/modpacks/search")
def search_modpacks(
    platform: str = "modrinth",
    query: str = "",
    minecraft_version: str = "",
    limit: int = 20,
    offset: int = 0,
) -> JSONResponse:
    try:
        return JSONResponse(modpacks.search(platform, query, minecraft_version or None, limit, offset))
    except ModPlatformError as error:
        return fail(error)
    except Exception as error:
        return fail(RuntimeError(f"搜索整合包失败: {error}"), 502)


@app.get("/api/modpacks/versions")
def modpack_versions(platform: str = "modrinth", project_id: str = Query(...), minecraft_version: str = "") -> JSONResponse:
    try:
        return JSONResponse(modpacks.versions(platform, project_id, minecraft_version or None))
    except ModPlatformError as error:
        return fail(error)
    except Exception as error:
        return fail(RuntimeError(f"获取整合包版本失败: {error}"), 502)


@app.post("/api/modpacks/install")
def install_modpack(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        return JSONResponse(
            modpacks.install(
                str(payload.get("platform") or "modrinth"),
                str(payload.get("project_id") or ""),
                str(payload.get("version_id")) if payload.get("version_id") else None,
                payload.get("name") or None,
            )
        )
    except ModpackError as error:
        return fail(error)


@app.post("/api/modpacks/import")
def import_modpack(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        return JSONResponse(modpacks.import_file(str(payload.get("path") or ""), payload.get("name") or None))
    except ModpackError as error:
        return fail(error)


# ---------- 启动 ----------


@app.post("/api/launch")
def launch(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    instance = instances.resolve(payload.get("instance_id") or None)
    if instance is None:
        return fail(InstanceError("请先创建或选择一个实例"))
    account = config.active_account()
    if not account:
        return fail(ValueError("请先登录账户"))
    try:
        account = auth.ensure_valid_account(account)
        config.set("active_instance", instance["id"])
        config.update_settings({"last_version": instance.get("version_id") or instance.get("mc_version") or ""})
        return JSONResponse(launcher.launch(instance["id"], account))
    except Exception as error:
        return fail(error)


@app.post("/api/launch/stop")
def stop_games() -> dict[str, Any]:
    launcher.stop_all()
    return {"ok": True}


@app.get("/api/launch/status")
def launch_status() -> dict[str, Any]:
    return {"running": launcher.running_games()}


if os.environ.get("NEO_SERVE_FRONTEND") and FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")


def run() -> None:
    import uvicorn

    port = int(os.environ.get("NEO_PORT", DEFAULT_PORT))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level=os.environ.get("NEO_LOG_LEVEL", "warning"))


if __name__ == "__main__":
    run()
