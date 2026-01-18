# Copyright (C) 2026 Stormy-RPG
# SPDX-License-Identifier: AGPL-3.0-only
import os
import sys
import inspect
from pathlib import Path
from typing import Awaitable, Callable, Optional, Union, TYPE_CHECKING

import asyncio
from aiohttp import web_log
from aiohttp import web

import logging
from colorama import Fore, Style

from utils.other import Other

if TYPE_CHECKING:
    from models.bot import TelegramMailBot


# Sets info about handler for logging.
async def handler_name_middleware(app: web.Application, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]) -> Callable[[web.Request], Awaitable[web.StreamResponse]]:
    async def middleware_handler(request: web.Request) -> web.StreamResponse:
        request["handler_name"] = handler.__name__
        request["handler_path"] = inspect.getfile(handler)
        request["handler_line"] = inspect.getsourcelines(handler)[1]
        request["handler_relpath"] = os.path.relpath(inspect.getfile(handler))

        response = await handler(request)
        return response

    return middleware_handler


# Custom access logger that adds handler context information.
# Enriches standard logs with handler name, file path, and line number.
class AioHttpAccessLogger(web_log.AccessLogger):
    def log(self, request: web_log.BaseRequest, response: web_log.StreamResponse, time: float) -> None:        
        try:
            fmt_info = self._format_line(request, response, time)
            values = list()
            extra = dict()

            handler_name = request.get("handler_name", "unknown")
            # Skip logging for uptime health checks to reduce noise
            if handler_name in ["uptime"]:
                return
            handler_relpath = request.get("handler_relpath", "unknown")
            handler_line = request.get("handler_line", "unknown")
            extra["caller"] = f"{handler_relpath}:{handler_line} ({handler_name})"

            for key, value in fmt_info:
                values.append(value)

                if key.__class__ is str:
                    extra[key] = value
                else:
                    k1, k2 = key  # type: ignore[misc]
                    dct = extra.get(k1, {})  # type: ignore[var-annotated,has-type]
                    dct[k2] = value  # type: ignore[index,has-type]
                    extra[k1] = dct  # type: ignore[has-type,assignment]

            self.logger.info(self._log_format % tuple(values), extra=extra)
        except Exception:
            self.logger.exception("Error in logging")

class ColoredFormatter(logging.Formatter):
    COLORS = {
        "INFO": Fore.GREEN,
        "ERROR": Fore.RED,
        "WARNING": Fore.YELLOW,
        "DEBUG": Fore.CYAN,
        "CRITICAL": Fore.MAGENTA,
    }

    def __init__(self, fmt = None, datefmt = None, style = "%", validate = True, *, defaults = None, use_color: bool = True):
        self.use_color = use_color
        super().__init__(fmt, datefmt, style, validate, defaults=defaults)

    def format(self, record: logging.LogRecord):
        if self.use_color:
            color = self.COLORS.get(record.levelname, Fore.WHITE)
            record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)

    def formatTime(self, record, datefmt=None):
        asctime = super().formatTime(record, datefmt)
        return f"{Fore.BLUE}{asctime}{Style.RESET_ALL}" if self.use_color else asctime


class Audit:
    _log_file: str
    def __init__(self, log_file: Union[str, bytes] = "telegram-mail-bot.log", *, bot: Optional["TelegramMailBot"] = None, loop = None) -> None:        
        file = Path(log_file)

        # Create parent directories if they don't exist
        if not file.parent.exists():
            file.parent.mkdir(parents=True)

        # Create empty log file if it doesn't exist
        if not file.exists():
            with open(file, "w") as f:
                f.write("")

        self.bot = bot
        self.loop = loop or asyncio.get_event_loop()
        self._log_file = str(log_file)
        self._logger = logging.getLogger("telegram-mail-bot")
        self._logger.setLevel(logging.INFO)

        # Console output handler
        self.console_handler = logging.StreamHandler(sys.stdout)
        self.console_handler.setLevel(logging.INFO)

        # File output handler
        self.file_handler = logging.FileHandler(self._log_file, encoding="utf-8")
        self.file_handler.setLevel(logging.INFO)

        # Log formatting
        console_formatter = ColoredFormatter("%(asctime)s - %(caller)s - %(levelname)s: %(message)s", datefmt="%Y.%m.%d %H:%M:%S")
        file_formatter = ColoredFormatter("%(asctime)s - %(caller)s - %(levelname)s: %(message)s", datefmt="%Y.%m.%d %H:%M:%S", use_color=False)
        self.console_handler.setFormatter(console_formatter)
        self.file_handler.setFormatter(file_formatter)

        # Add handlers to logger
        self._logger.addHandler(self.file_handler)

    def _log(self, frame: inspect.FrameInfo | None, level: int, message: str, *, use_relative_path: bool = True, to_console: bool = True):
        caller_path, caller_relative_path, caller_lineno, caller_function_name = Other.get_caller_info(frame=frame)

        # Thanks to the logging module creators for this flexibility
        if not to_console: 
            self._logger.removeHandler(self.console_handler)
        else: 
            self._logger.addHandler(self.console_handler)
        caller = f"{caller_path if not use_relative_path else caller_relative_path}:{caller_lineno}" + (f" ({caller_function_name})" if caller_function_name != "<module>" else "")
        self._logger.log(level, message, extra={"caller": caller})

    def info(self, message: str, *, to_console: bool = True):
        self._log(inspect.currentframe(), logging.INFO, message, to_console=to_console)

    def error(self, message: str, *, to_console: bool = True):
        self._log(inspect.currentframe(), logging.ERROR, message, to_console=to_console)

    def warning(self, message: str, *, to_console: bool = True):
        self._log(inspect.currentframe(), logging.WARNING, message, to_console=to_console)

    def debug(self, message: str, *, to_console: bool = True): 
        self._log(inspect.currentframe(), logging.DEBUG, message, to_console=to_console)

    def critical(self, message: str, *, to_console: bool = True):
        self._log(inspect.currentframe(), logging.CRITICAL, message, to_console=to_console)