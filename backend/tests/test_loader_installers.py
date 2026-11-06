from __future__ import annotations

import json
import os
import shutil
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import minecraft_launcher_lib as mll
from neo.config import Config
from neo.launcher import (
    _loader_installer_command,
    cache_mod_loader_jar,
    inspect_mod_loader_jar,
    install_mod_loader_from_jar,
)


class LoaderInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2] / ".test-tmp" / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.previous_config = os.environ.get("NEO_CONFIG_DIR")
        os.environ["NEO_CONFIG_DIR"] = str(self.root / "config")

    def tearDown(self) -> None:
        if self.previous_config is None:
            os.environ.pop("NEO_CONFIG_DIR", None)
        else:
            os.environ["NEO_CONFIG_DIR"] = self.previous_config
        shutil.rmtree(self.root, ignore_errors=True)

    def _jar(self, name: str, profile: dict[str, object] | None = None) -> Path:
        path = self.root / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
            if profile is not None:
                archive.writestr("install_profile.json", json.dumps(profile))
        return path

    def test_reads_forge_profile_metadata(self) -> None:
        path = self._jar(
            "forge-1.20.1-47.2.0-installer.jar",
            {
                "minecraft": "1.20.1",
                "version": "1.20.1-47.2.0",
                "path": "net.minecraftforge:forge:1.20.1-47.2.0",
            },
        )

        details = inspect_mod_loader_jar(path)

        self.assertEqual(details["loader"], "forge")
        self.assertEqual(details["minecraft_version"], "1.20.1")
        self.assertEqual(details["loader_version"], "47.2.0")

    def test_reads_neoforge_profile_metadata(self) -> None:
        path = self._jar(
            "neoforge-21.1.1-installer.jar",
            {
                "minecraft": "1.21.1",
                "version": "21.1.1",
                "path": "net.neoforged:neoforge:21.1.1",
            },
        )

        details = inspect_mod_loader_jar(path)

        self.assertEqual(details["loader"], "neoforge")
        self.assertEqual(details["minecraft_version"], "1.21.1")
        self.assertEqual(details["loader_version"], "21.1.1")

    def test_caches_installer_inside_config_directory(self) -> None:
        path = self._jar(
            "forge-1.20.1-47.2.0-installer.jar",
            {
                "minecraft": "1.20.1",
                "version": "47.2.0",
                "path": "net.minecraftforge:forge:1.20.1-47.2.0",
            },
        )
        config = Config()

        cached = cache_mod_loader_jar(config, path)

        self.assertTrue(cached.is_file())
        self.assertEqual(cached.parent, config.dir / "loader-installers")
        self.assertEqual(cached.read_bytes(), path.read_bytes())

    def test_recognizes_fabric_installer_without_profile(self) -> None:
        path = self.root / "fabric-installer-1.0.1.jar"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "META-INF/MANIFEST.MF",
                "Manifest-Version: 1.0\nMain-Class: net.fabricmc.installer.Main\n",
            )
            archive.writestr("net/fabricmc/installer/Main.class", b"")

        details = inspect_mod_loader_jar(path)

        self.assertEqual(details["loader"], "fabric")
        self.assertEqual(details["loader_version"], "")

    def test_rejects_jars_without_installer_metadata(self) -> None:
        path = self._jar("not-an-installer.jar")

        with self.assertRaisesRegex(ValueError, "无法从安装包识别"):
            inspect_mod_loader_jar(path)

    def test_builds_official_installer_commands(self) -> None:
        forge = _loader_installer_command(
            "forge", "1.20.1", "47.2.0", "C:/game", "C:/installer.jar", "java.exe"
        )
        fabric = _loader_installer_command(
            "fabric", "1.20.1", "0.16.0", "C:/game", "C:/installer.jar", "java.exe"
        )

        self.assertEqual(forge[-2:], ["--installClient", "C:/game"])
        self.assertIn("-mcversion", fabric)
        self.assertIn("1.20.1", fabric)
        self.assertIn("-loader", fabric)
        self.assertIn("0.16.0", fabric)

    def test_online_sources_resolve_to_official_installers(self) -> None:
        cases = {
            "forge": ("47.2.0", "maven.minecraftforge.net"),
            "neoforge": ("21.1.1", "maven.neoforged.net"),
            "fabric": ("0.16.0", "maven.fabricmc.net"),
            "quilt": ("0.27.0", "maven.quiltmc.org"),
        }
        for loader, (version, host) in cases.items():
            with self.subTest(loader=loader):
                url = mll.mod_loader.get_mod_loader(loader)._base.get_installer_url(
                    "1.20.1", version
                )
                self.assertIn(host, url)
                self.assertTrue(url.endswith(".jar"))

    def test_installs_from_cached_local_jar(self) -> None:
        path = self._jar(
            "forge-1.20.1-47.2.0-installer.jar",
            {
                "minecraft": "1.20.1",
                "version": "1.20.1-47.2.0",
                "path": "net.minecraftforge:forge:1.20.1-47.2.0",
            },
        )
        minecraft_dir = self.root / "minecraft"
        version_id = "1.20.1-forge-47.2.0"

        def fake_install(current_version: str, directory: str, **_: object) -> None:
            target = Path(directory) / "versions" / current_version / f"{current_version}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}", encoding="utf-8")

        def fake_run(*_: object, **__: object) -> mock.Mock:
            target = minecraft_dir / "versions" / version_id / f"{version_id}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}", encoding="utf-8")
            result = mock.Mock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with (
            mock.patch.object(mll.install, "install_minecraft_version", side_effect=fake_install),
            mock.patch.object(mll.vanilla_launcher, "do_vanilla_launcher_profiles_exists", return_value=True),
            mock.patch("neo.launcher.subprocess.run", side_effect=fake_run) as run,
        ):
            installed, loader_version = install_mod_loader_from_jar(
                "forge",
                "1.20.1",
                str(minecraft_dir),
                "47.2.0",
                path,
                {},
                "java.exe",
            )

        self.assertEqual(installed, version_id)
        self.assertEqual(loader_version, "47.2.0")
        command = run.call_args.args[0]
        self.assertEqual(command[-2:], ["--installClient", str(minecraft_dir)])


if __name__ == "__main__":
    unittest.main()
