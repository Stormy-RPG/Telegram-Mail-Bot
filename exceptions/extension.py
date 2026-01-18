# Copyright (C) 2026 Stormy-RPG
# SPDX-License-Identifier: AGPL-3.0-only
from typing import Any, Optional


class ExtensionException(Exception):
    pass

class ExtensionError(ExtensionException):
    def __init__(self, message: Optional[str] = None, *args: Any, name: str) -> None:
        self.name: str = name
        message = message or f"An error occurred in extension {name!r}."
        super().__init__(message, *args)


class ExtensionAlreadyLoaded(ExtensionError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Extension {name!r} is already loaded.", name=name)


class ExtensionNotLoaded(ExtensionError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Extension {name!r} is not loaded.", name=name)


class NoEntryPointError(ExtensionError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Extension {name!r} does not have a 'setup' function.", name=name)


class ExtensionFailed(ExtensionError):
    def __init__(self, name: str, original: Exception) -> None:
        self.original: Exception = original
        msg = f"Extension {name!r} raised an error: {original.__class__.__name__}: {original}"
        super().__init__(msg, name=name)


class ExtensionNotFound(ExtensionError):
    def __init__(self, name: str) -> None:
        msg = f"Failed to load extension {name!r}."
        super().__init__(msg, name=name)