from __future__ import annotations

import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from neo.auth import AuthError, AuthService
from neo.config import Config
from neo.events import EventBus


class SkinPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2] / ".test-tmp" / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.previous_config = os.environ.get("NEO_CONFIG_DIR")
        os.environ["NEO_CONFIG_DIR"] = str(self.root / "config")
        self.config = Config()
        self.service = AuthService(self.config, EventBus())

    def tearDown(self) -> None:
        if self.previous_config is None:
            os.environ.pop("NEO_CONFIG_DIR", None)
        else:
            os.environ["NEO_CONFIG_DIR"] = self.previous_config
        shutil.rmtree(self.root, ignore_errors=True)

    def _add_accounts(self) -> None:
        self.config.upsert_account(
            {
                "uuid": "player-one",
                "name": "PlayerOne",
                "type": "microsoft",
                "access_token": "token",
                "skin": None,
            }
        )
        self.config.upsert_account(
            {
                "uuid": "player-two",
                "name": "PlayerTwo",
                "type": "microsoft",
                "access_token": "token",
            }
        )

    def test_microsoft_skin_is_cached_without_switching_active_account(self) -> None:
        self._add_accounts()
        with mock.patch.object(
            self.service,
            "_fetch_textures",
            return_value={
                "skin": "https://textures.minecraft.net/texture/example",
                "skin_model": "slim",
                "cape": None,
            },
        ):
            preview = self.service.skin_preview("player-one")

        self.assertEqual(preview["skin"], "https://textures.minecraft.net/texture/example")
        self.assertEqual(preview["skin_model"], "slim")
        self.assertEqual(self.config.active_account()["uuid"], "player-two")
        self.assertEqual(
            self.config.find_account("player-one")["skin_model"],
            "slim",
        )

    def test_cached_skin_is_available_when_mojang_is_unreachable(self) -> None:
        self._add_accounts()
        self.config.update_account(
            "player-one",
            {
                "skin": "https://textures.minecraft.net/texture/cached",
                "skin_model": "classic",
            },
        )
        with mock.patch.object(self.service, "_fetch_textures", return_value=None):
            preview = self.service.skin_preview("player-one")

        self.assertEqual(preview["skin"], "https://textures.minecraft.net/texture/cached")
        self.assertTrue(preview["cached"])

    def test_offline_account_cannot_open_skin_preview(self) -> None:
        self.config.upsert_account(
            {"uuid": "offline", "name": "Offline", "type": "offline", "skin": None}
        )
        with self.assertRaisesRegex(AuthError, "微软正版"):
            self.service.skin_preview("offline")


if __name__ == "__main__":
    unittest.main()
