# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

"""Configurable first-16-byte magic-number detection."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


SignatureRule = tuple[str, list[tuple[int, bytes]]]


class MagicNumberDetector:
    """Detect formats using rules stored entirely in JSON."""

    HEADER_SIZE = 16

    def __init__(self, config_path: Path | str):
        self.config_path = Path(config_path)
        self.formats: list[SignatureRule] = []

    @classmethod
    def parse_configuration(
        cls, configuration: Any
    ) -> tuple[list[SignatureRule], list[str]]:
        formats = configuration.get("formats", []) if isinstance(configuration, dict) else []
        if not isinstance(formats, list):
            return [], ["Format configuration field 'formats' must be a list."]

        parsed: list[SignatureRule] = []
        errors: list[str] = []
        for index, item in enumerate(formats, start=1):
            try:
                if not isinstance(item, dict):
                    raise ValueError("must be an object")

                extension = str(item.get("extension", "")).strip().lower().lstrip(".")
                if not extension or any(char in extension for char in '\\\\/:*?"<>|'):
                    raise ValueError("contains an invalid extension")

                signatures = item.get("signatures")
                if signatures is None:
                    signatures = [{
                        "offset": item.get("offset", 0),
                        "signature_hex": item.get("signature_hex", ""),
                    }]
                if not isinstance(signatures, list) or not signatures:
                    raise ValueError("requires a non-empty signatures list")

                parts: list[tuple[int, bytes]] = []
                for signature_item in signatures:
                    if not isinstance(signature_item, dict):
                        raise ValueError("each signature must be an object")
                    offset = signature_item.get("offset", 0)
                    raw_hex = str(signature_item.get("signature_hex", "")).replace(" ", "")
                    if not isinstance(offset, int) or not 0 <= offset < cls.HEADER_SIZE:
                        raise ValueError("offset must be an integer from 0 through 15")
                    signature = bytes.fromhex(raw_hex)
                    if not signature:
                        raise ValueError("signature_hex cannot be empty")
                    if offset + len(signature) > cls.HEADER_SIZE:
                        raise ValueError("signature extends beyond the first 16 bytes")
                    parts.append((offset, signature))
                parsed.append((extension, parts))
            except (TypeError, ValueError) as error:
                errors.append(f"Format entry {index}: {error}")
        return parsed, errors

    def load(self) -> tuple[list[SignatureRule], list[str]]:
        if not self.config_path.exists():
            self.formats = []
            return [], [f"Format configuration does not exist: {self.config_path}"]
        try:
            with self.config_path.open("r", encoding="utf-8") as handle:
                configuration = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            return list(self.formats), [f"Cannot load format configuration: {error}"]

        parsed, errors = self.parse_configuration(configuration)
        if errors:
            return list(self.formats), errors
        self.formats = parsed
        return list(self.formats), []

    def save_text(self, configuration_text: str) -> tuple[bool, str]:
        try:
            configuration = json.loads(configuration_text)
        except json.JSONDecodeError as error:
            return False, f"Invalid JSON: {error}"
        if not isinstance(configuration, dict) or "formats" not in configuration:
            return False, "Configuration must contain a 'formats' list."

        parsed, errors = self.parse_configuration(configuration)
        if errors:
            return False, "Configuration was not accepted:\n" + "\n".join(errors)

        temporary = self.config_path.with_name(
            f".{self.config_path.name}.{os.getpid()}.tmp"
        )
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(configuration, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, self.config_path)
        except OSError as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return False, f"Could not save configuration: {error}"

        self.formats = parsed
        return True, f"Loaded {len(parsed)} format rule(s)."

    def detect(self, file_path: Path | str) -> tuple[str | None, str]:
        """Read at most 16 bytes and return the first matching extension."""
        try:
            with open(file_path, "rb") as handle:
                header = handle.read(self.HEADER_SIZE)
        except OSError as error:
            return None, str(error)

        for extension, parts in self.formats:
            if all(
                header[offset:offset + len(signature)] == signature
                for offset, signature in parts
            ):
                return extension, ""
        return None, ""
