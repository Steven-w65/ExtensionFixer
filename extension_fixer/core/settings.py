# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

"""Application settings persistence with validation and atomic writes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class ApplicationSettings:
    """Load and save non-format application preferences."""

    DEFAULTS: dict[str, Any] = {
        "last_folder": "",
        "recursive_scan": True,
        "show_only_repair_items": False,
        "enable_backup": True,
        "automatic_scan_after_repair": False,
        "automatic_scan_after_undo": False,
        "duplicate_strategy": 1,
        "max_size_mb": "1024",
        "suffix_blacklist": ".exe, .dll",
    }

    LEGACY_STRATEGIES = {
        "Auto append serial number": 1,
        "Skip when duplicate name exists": 2,
        "Safe mode: forbid overwriting": 3,
    }

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        settings = dict(self.DEFAULTS)
        if not self.path.exists():
            return settings

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                stored = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return settings

        if isinstance(stored, dict):
            for key in settings:
                if key in stored:
                    settings[key] = stored[key]

        strategy = settings["duplicate_strategy"]
        if isinstance(strategy, str):
            strategy = self.LEGACY_STRATEGIES.get(strategy, 1)
        if strategy not in (1, 2, 3):
            strategy = 1
        settings["duplicate_strategy"] = strategy

        for key in (
            "recursive_scan",
            "show_only_repair_items",
            "enable_backup",
            "automatic_scan_after_repair",
            "automatic_scan_after_undo",
        ):
            value = settings[key]
            if isinstance(value, str):
                settings[key] = value.strip().lower() in {"1", "true", "yes", "on"}
            else:
                settings[key] = bool(value)

        try:
            size_limit = float(settings["max_size_mb"])
            if not 0 <= size_limit <= 1_000_000:
                raise ValueError
            settings["max_size_mb"] = str(settings["max_size_mb"])
        except (TypeError, ValueError):
            settings["max_size_mb"] = self.DEFAULTS["max_size_mb"]

        settings["last_folder"] = str(settings["last_folder"])
        settings["suffix_blacklist"] = str(settings["suffix_blacklist"])
        return settings

    def save(self, settings: dict[str, Any]) -> tuple[bool, str]:
        """Persist settings through a same-directory temporary file."""
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(settings, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, self.path)
            return True, ""
        except OSError as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return False, str(error)
