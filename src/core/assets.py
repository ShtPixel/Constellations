"""Asset manifest loader and helpers.

This module centralizes access to assets defined in assets/assets.manifest.json.
It is optional: if the manifest or files are missing, callers should gracefully
fallback to defaults.
"""
from __future__ import annotations
import json
import os
from typing import Any, Optional


class AssetManifest:
    def __init__(self, path: Optional[str] = None):
        # Resolve default path relative to current working directory
        self.path = path or os.path.join(os.getcwd(), "assets", "assets.manifest.json")
        self._data: dict[str, Any] = {}
        self._loaded = False
        self.load()

    def load(self) -> None:
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f) or {}
            else:
                self._data = {}
        except Exception:
            # Any JSON error -> treat as empty manifest
            self._data = {}
        self._loaded = True

    def _get_nested(self, *keys: str) -> Any:
        node: Any = self._data
        try:
            for k in keys:
                node = node[k]
            return node
        except Exception:
            return None

    # Convenience getters
    def get_image(self, name: str) -> Optional[str]:
        v = self._get_nested("images", name)
        return v if isinstance(v, str) else None

    def get_sound(self, name: str) -> Optional[str]:
        v = self._get_nested("sounds", name)
        return v if isinstance(v, str) else None

    def get_font(self, name: str) -> Optional[str]:
        v = self._get_nested("fonts", name)
        return v if isinstance(v, str) else None


# Optional pygame helpers (only executed if pygame is available)
def load_pygame_image(path: str):
    try:
        import pygame  # type: ignore
        if not os.path.exists(path):
            return None
        return pygame.image.load(path)
    except Exception:
        return None


def load_pygame_font(path: str, size: int):
    try:
        import pygame  # type: ignore
        if not os.path.exists(path):
            return None
        return pygame.font.Font(path, size)
    except Exception:
        return None
