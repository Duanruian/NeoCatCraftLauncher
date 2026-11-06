from __future__ import annotations

import base64
import json
import re
import zipfile
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

ICON_LIMIT_BYTES = 384 * 1024
DESCRIPTION_LIMIT = 260
ICON_CACHE: dict[str, str | None] = {}

_FORMAT_CODE = re.compile(r"\u00a7.")
_WHITESPACE = re.compile(r"\s+")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _clean_text(value: Any, limit: int = DESCRIPTION_LIMIT) -> str:
    if not value:
        return ""
    text = _FORMAT_CODE.sub("", str(value))
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:limit]


def _jar_display_name(path: Path) -> str:
    filename = path.name
    while filename.lower().endswith((".jar", ".disabled")):
        filename = filename.rsplit(".", 1)[0]
    return filename or path.stem


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [str(key) for key in value.keys()]
    if isinstance(value, (list, tuple)):
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                candidate = item.get("name") or item.get("login") or item.get("id")
                if candidate:
                    result.append(str(candidate))
        return result
    return []


def _read_json(archive: zipfile.ZipFile, name: str) -> Any:
    try:
        raw = archive.read(name)
    except KeyError:
        return None
    except Exception:
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return None


def _read_text(archive: zipfile.ZipFile, name: str) -> str | None:
    try:
        return archive.read(name).decode("utf-8", errors="replace")
    except Exception:
        return None


def _image_mime(data: bytes, suffix: str) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(suffix.lower(), "image/png")


def _icon_candidates(icon_path: str, mod_id: Any) -> list[str]:
    candidates: list[str] = []

    def add(value: str) -> None:
        normalized = value.replace("\\", "/").strip().lstrip("/")
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    path = icon_path.replace("\\", "/").strip().lstrip("/")
    if path:
        add(path)
        if ":" in path and "://" not in path:
            namespace, resource = path.split(":", 1)
            if namespace and resource:
                add(f"assets/{namespace}/{resource}")
        if not path.lower().startswith("assets/"):
            add(f"assets/{path}")
            identifier = _clean_text(mod_id, 120).lower()
            if identifier:
                add(f"assets/{identifier}/{path}")

    identifier = _clean_text(mod_id, 120).lower()
    if identifier:
        for filename in ("icon.png", "logo.png", "icon.jpg", "logo.jpg"):
            add(f"assets/{identifier}/{filename}")
    for filename in ("icon.png", "logo.png"):
        add(filename)
    return candidates


def _icon_data_uri(archive: zipfile.ZipFile, icon_path: Any, mod_id: Any = None) -> str | None:
    if isinstance(icon_path, dict):
        icon_path = icon_path.get("path") or icon_path.get("icon")
    if not isinstance(icon_path, str):
        icon_path = ""

    raw_path = icon_path.strip()
    if raw_path.lower().startswith("data:image/"):
        if len(raw_path.encode("utf-8")) <= ICON_LIMIT_BYTES * 2:
            return raw_path
        return None

    archive_names = {name.lower(): name for name in archive.namelist()}
    for candidate in _icon_candidates(raw_path, mod_id):
        actual = archive_names.get(candidate.lower())
        if not actual:
            continue
        try:
            info = archive.getinfo(actual)
            if info.file_size <= 0 or info.file_size > ICON_LIMIT_BYTES:
                continue
            data = archive.read(actual)
        except Exception:
            continue
        suffix = Path(actual).suffix.lower()
        if suffix and suffix not in _IMAGE_SUFFIXES:
            continue
        mime = _image_mime(data, suffix)
        return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")

    # Metadata occasionally uses a different directory but the same unique
    # image filename. Only use that fallback when the basename is unambiguous.
    basename = Path(raw_path.replace("\\", "/")).name.lower()
    if basename and Path(basename).suffix.lower() in _IMAGE_SUFFIXES:
        matches = [
            actual
            for lowered, actual in archive_names.items()
            if Path(lowered).name == basename and Path(lowered).suffix.lower() in _IMAGE_SUFFIXES
        ]
        if len(matches) == 1:
            try:
                info = archive.getinfo(matches[0])
                if 0 < info.file_size <= ICON_LIMIT_BYTES:
                    data = archive.read(matches[0])
                    suffix = Path(matches[0]).suffix.lower()
                    mime = _image_mime(data, suffix)
                    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
            except Exception:
                pass
    return None


def _parse_fabric(archive: zipfile.ZipFile, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "loader": "fabric",
        "name": meta.get("name") or meta.get("id"),
        "version": meta.get("version"),
        "mod_id": meta.get("id"),
        "description": meta.get("description"),
        "authors": _as_list(meta.get("authors")),
        "mc_version": (meta.get("depends") or {}).get("minecraft"),
        "icon": meta.get("icon"),
    }


def _parse_quilt(archive: zipfile.ZipFile, meta: dict[str, Any]) -> dict[str, Any]:
    loader_section = meta.get("quilt_loader") or {}
    metadata = loader_section.get("metadata") or {}
    dependencies = loader_section.get("depends") or []
    minecraft_range = None
    if isinstance(dependencies, list):
        for entry in dependencies:
            if isinstance(entry, dict) and entry.get("id") == "minecraft":
                minecraft_range = entry.get("versions")
    return {
        "loader": "quilt",
        "name": metadata.get("name") or loader_section.get("id"),
        "version": loader_section.get("version"),
        "mod_id": loader_section.get("id"),
        "description": metadata.get("description"),
        "authors": _as_list(metadata.get("contributors")),
        "mc_version": minecraft_range,
        "icon": metadata.get("icon"),
    }


def _parse_toml(archive: zipfile.ZipFile, text: str, loader: str) -> dict[str, Any]:
    if tomllib is None:
        raise ValueError("当前 Python 缺少 tomllib，无法解析 mods.toml")
    data = tomllib.loads(text)
    mods = data.get("mods") or []
    first = mods[0] if mods else {}
    minecraft_range = None
    dependencies = data.get("dependencies") or {}
    if isinstance(dependencies, dict):
        for entries in dependencies.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and str(entry.get("modId", "")).lower() in {"minecraft"}:
                    minecraft_range = entry.get("versionRange")
    return {
        "loader": loader,
        "name": first.get("displayName") or first.get("modId"),
        "version": first.get("version"),
        "mod_id": first.get("modId"),
        "description": first.get("description"),
        "authors": _as_list(first.get("authors")) or _as_list(data.get("authors")),
        "mc_version": minecraft_range,
        "icon": first.get("logoFile") or data.get("logoFile"),
        "mod_count": len(mods),
        "mod_loader": data.get("modLoader"),
        "loader_version": data.get("loaderVersion"),
    }


def _parse_mcmod_info(archive: zipfile.ZipFile, data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        entries = data.get("modList") or data.get("modlist") or []
    elif isinstance(data, list):
        entries = data
    else:
        entries = []
    first = entries[0] if entries else {}
    return {
        "loader": "forge",
        "name": first.get("name") or first.get("modid"),
        "version": first.get("version"),
        "mod_id": first.get("modid"),
        "description": first.get("description"),
        "authors": _as_list(first.get("authorList") or first.get("author")),
        "mc_version": first.get("mcversion") or first.get("acceptedMinecraftVersions"),
        "icon": first.get("logoFile"),
        "mod_count": len(entries),
    }


def _parse_manifest(archive: zipfile.ZipFile, text: str) -> dict[str, Any]:
    fields: dict[str, str] = {}
    key = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith(" ") and key:
            fields[key] += line.strip()
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower()
            fields[key] = value.strip()
    return {
        "loader": "unknown",
        "name": fields.get("implementation-title"),
        "version": fields.get("implementation-version"),
        "mod_id": None,
        "description": None,
        "authors": _as_list(fields.get("implementation-vendor")),
        "mc_version": None,
        "icon": None,
    }


def parse_mod_jar(path: Path) -> dict[str, Any]:
    stat = path.stat()
    base: dict[str, Any] = {
        "file_name": path.name,
        "path": str(path),
        "size": stat.st_size,
        "modified": stat.st_mtime,
        "enabled": not path.name.lower().endswith(".disabled"),
        "name": _jar_display_name(path),
        "version": "",
        "mod_id": "",
        "loader": "unknown",
        "description": "",
        "authors": [],
        "mc_version": None,
        "icon": None,
        "parsed": False,
        "issues": [],
    }

    try:
        archive = zipfile.ZipFile(path)
    except Exception as error:
        base["issues"].append(f"无法读取 jar: {error.__class__.__name__}")
        return base

    with archive:
        metadata: dict[str, Any] | None = None
        try:
            quilt_json = _read_json(archive, "quilt.mod.json")
            fabric_json = _read_json(archive, "fabric.mod.json")
            if quilt_json is not None:
                metadata = _parse_quilt(archive, quilt_json)
            elif fabric_json is not None:
                metadata = _parse_fabric(archive, fabric_json)
            if metadata is None:
                neoforge_text = _read_text(archive, "META-INF/neoforge.mods.toml")
                if neoforge_text:
                    metadata = _parse_toml(archive, neoforge_text, "neoforge")
            if metadata is None:
                forge_text = _read_text(archive, "META-INF/mods.toml")
                if forge_text:
                    metadata = _parse_toml(archive, forge_text, "forge")
            if metadata is None:
                info = _read_json(archive, "mcmod.info")
                if info is not None:
                    metadata = _parse_mcmod_info(archive, info)
            if metadata is None:
                manifest = _read_text(archive, "META-INF/MANIFEST.MF")
                if manifest:
                    metadata = _parse_manifest(archive, manifest)
        except Exception as error:
            base["issues"].append(f"元数据解析失败: {error}")

        if metadata is None:
            base["issues"].append("未找到可识别的模组元数据")
            return base

        base["name"] = _clean_text(metadata.get("name"), 120) or _jar_display_name(path)
        base["version"] = _clean_text(metadata.get("version"), 60)
        base["mod_id"] = _clean_text(metadata.get("mod_id"), 120)
        base["loader"] = metadata.get("loader") or "unknown"
        base["description"] = _clean_text(metadata.get("description"))
        base["authors"] = [a for a in (_clean_text(x, 60) for x in metadata.get("authors") or []) if a][:6]
        base["mc_version"] = _clean_text(metadata.get("mc_version"), 60) or None
        base["parsed"] = bool(base["version"] or base["mod_id"] or metadata.get("name"))

        cache_key = f"{path}|{stat.st_mtime}"
        if cache_key in ICON_CACHE:
            base["icon"] = ICON_CACHE[cache_key]
        else:
            icon = _icon_data_uri(archive, metadata.get("icon"), metadata.get("mod_id"))
            ICON_CACHE[cache_key] = icon
            base["icon"] = icon

    return base


def scan_mods(mods_directory: Path) -> dict[str, Any]:
    mods_directory.mkdir(parents=True, exist_ok=True)
    files = sorted(
        [entry for entry in mods_directory.iterdir() if entry.is_file() and entry.name.lower().endswith((".jar", ".jar.disabled"))],
        key=lambda entry: entry.name.lower(),
    )
    mods = [parse_mod_jar(entry) for entry in files]

    duplicates: dict[str, list[str]] = {}
    for mod in mods:
        if mod["mod_id"]:
            duplicates.setdefault(mod["mod_id"], []).append(mod["file_name"])
    duplicate_ids = {mod_id: names for mod_id, names in duplicates.items() if len(names) > 1}

    return {
        "directory": str(mods_directory),
        "count": len(mods),
        "unparsed": len([mod for mod in mods if not mod["parsed"]]),
        "duplicates": duplicate_ids,
        "mods": mods,
    }
