# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

"""Application settings persistence with validation and atomic writes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .detector import MagicNumberDetector


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

    def save_with_formats(
        self,
        settings: dict[str, Any],
        detector: MagicNumberDetector,
        configuration_text: str,
    ) -> tuple[bool, str]:
        """Commit settings and format rules as one recoverable transaction.

        Both replacement files are fully validated and staged before either
        original is replaced. If the second replacement fails, the first is
        restored from its byte-for-byte snapshot before this method returns.
        """
        try:
            configuration = json.loads(configuration_text)
        except json.JSONDecodeError as error:
            return False, f"Invalid JSON: {error}"
        if not isinstance(configuration, dict) or "formats" not in configuration:
            return False, "Configuration must contain a 'formats' list."
        parsed_formats, format_errors = detector.parse_configuration(configuration)
        if format_errors:
            return False, "Configuration was not accepted:\n" + "\n".join(format_errors)

        try:
            format_bytes = json.dumps(
                configuration, ensure_ascii=False, indent=2
            ).encode("utf-8")
            settings_bytes = json.dumps(
                settings, ensure_ascii=False, indent=2
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            return False, f"Could not serialize settings: {error}"

        targets = (
            (detector.config_path, format_bytes, "formats"),
            (self.path, settings_bytes, "settings"),
        )
        staged: list[tuple[Path, Path, bytes | None, str]] = []
        try:
            for index, (target, payload, label) in enumerate(targets):
                target.parent.mkdir(parents=True, exist_ok=True)
                snapshot = target.read_bytes() if target.exists() else None
                temporary = target.with_name(
                    f".{target.name}.{os.getpid()}.transaction-{index}.tmp"
                )
                staged.append((temporary, target, snapshot, label))
                with temporary.open("wb") as handle:
                    handle.write(payload)
        except OSError as error:
            for temporary, _target, _snapshot, _label in staged:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            return False, f"Could not stage settings transaction: {error}"

        committed: list[tuple[Path, bytes | None, str]] = []
        try:
            for temporary, target, snapshot, label in staged:
                os.replace(temporary, target)
                committed.append((target, snapshot, label))
        except OSError as error:
            rollback_errors: list[str] = []
            for target, snapshot, label in reversed(committed):
                rollback_temporary = target.with_name(
                    f".{target.name}.{os.getpid()}.rollback.tmp"
                )
                try:
                    if snapshot is None:
                        target.unlink(missing_ok=True)
                    else:
                        with rollback_temporary.open("wb") as handle:
                            handle.write(snapshot)
                        os.replace(rollback_temporary, target)
                except OSError as rollback_error:
                    rollback_errors.append(f"{label}: {rollback_error}")
                finally:
                    try:
                        rollback_temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
            for temporary, _target, _snapshot, _label in staged:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            message = f"Could not commit settings transaction: {error}"
            if rollback_errors:
                # Reload whatever is now on disk so detection never silently
                # disagrees with a rollback that the filesystem rejected.
                detector.load()
                message += "\nRollback also failed: " + "; ".join(rollback_errors)
            return False, message

        detector.formats = parsed_formats
        return True, f"Loaded {len(parsed_formats)} format rule(s)."
