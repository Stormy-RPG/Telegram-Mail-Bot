# Copyright (C) 2026 Stormy-RPG
# SPDX-License-Identifier: AGPL-3.0-only
import os
import sys
import time
import asyncio
import importlib.util
from typing import List, Optional

import aiogram
from aiogram.dispatcher.event.handler import HandlerObject
from aiogram.dispatcher.event.telegram import TelegramEventObserver
from aiogram.dispatcher.event.event import EventObserver

from aiohttp import web

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import exceptions.extension as errors
from models.dp import TelegramMailBotDispatcher
from utils.other import Other
from utils.audit import Audit


class ExtensionEventHandler(FileSystemEventHandler):
    def __init__(self, loader: 'TelegramMailBot'):
        self.loader = loader
        self.last_modified = {}  # track last modification time per file
        self.debounce_seconds = 0.5  # 500ms debounce

    def _path_to_module(self, filepath: str) -> str:
        """Convert file path to Python module name."""
        # Remove .py extension
        filepath = filepath.replace('.py', '')
        # Convert path separators to dots
        module_name = filepath.replace('\\', '.').replace('/', '.')
        # Remove leading './' if present
        if module_name.startswith('.'):
            module_name = module_name[1:]
        return module_name

    def on_modified(self, event) -> None:
        """Handle file modification events for hot-reload."""
        if event.src_path.endswith('.py'):

            current_time = time.time()
            last_time = self.last_modified.get(event.src_path, 0)

            # Ignore events that happen too quickly after previous one
            if current_time - last_time < self.debounce_seconds:
                return
            
            # Update last modified time
            self.last_modified[event.src_path] = current_time

            module_name = self._path_to_module(event.src_path)
            self.loader.audit.info(f"File modified: {event.src_path} -> Module: {module_name}")
            try:
                self.loader.reload_extension(module_name)
            except Exception as e:
                print(f"Failed to reload {module_name}: {e}")
    
    # Not necessary
    # def on_created(self, event) -> None:
    #     """Handle file creation events."""
    #     if event.src_path.endswith('.py'):
    #         module_name = self._path_to_module(event.src_path)
    #         self.loader.audit.info(f"File created: {event.src_path} -> Module: {module_name}")
    #         try:
    #             self.loader.load_extension(module_name)
    #         except Exception as e:
    #             print(f"Failed to load {module_name}: {e}")
    
    def on_deleted(self, event) -> None:
        """Handle file deletion events."""
        if event.src_path.endswith('.py'):
            module_name = self._path_to_module(event.src_path)
            self.loader.audit.info(f"File deleted: {event.src_path} -> Module: {module_name}")
            try:
                self.loader.unload_extension(module_name)
            except Exception as e:
                print(f"Failed to unload {module_name}: {e}")


class TelegramMailBot(aiogram.Bot):
    def __init__(self, 
            token,
            session=None,
            default=None,
            dp: Optional[TelegramMailBotDispatcher] = None,

            mode: str = "development",
            version: str = "1.0.0", 
            audit: Optional[Audit] = None,
            owner_ids: List[int] = [],
            http_server: web.Application = None,
            github_token: Optional[str] = None,
            reload: bool = False,
            reload_path: os.PathLike = "cogs",
            **kwargs
        ):
        self.__extensions = {}
        self.__extension_observer = Observer()
        self.dp = dp
        
        self.mode = mode
        self.reload = reload
        self.reload_path = reload_path
        self.version = version
        self.audit = audit
        self.owner_ids = owner_ids
        self.http_server = http_server
        self.github_token = github_token
        self.scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
        super().__init__(token, session, default, **kwargs)
    
    async def _scheduler_start(self):
        self.scheduler.start()
        self.audit.info("Task scheduler has been started")

    async def _run(self):
        await self.dp.start_polling(self)

    async def run(self):
        if not self.dp:
            self.dp = TelegramMailBotDispatcher()

        await self.dp.run_startup()

        if self.reload:
            self.start_watching_extensions(self.reload_path)

        try:
            await asyncio.gather(self._run(), self._scheduler_start())
        except Exception as e:
            self.audit.error(f"Critical Error: {e}")
            sys.exit()
    
    def get_all_handlers(self, router: aiogram.Router) -> List[str]:
        all_attrs = dir(router)
        handler_containers = []

        for attr in all_attrs:
            if not attr.startswith('_'):
                obj = getattr(router, attr, None)
                # Check whether a attr is a handler
                if (isinstance(obj, TelegramEventObserver) or isinstance(obj, EventObserver)) and hasattr(obj, 'handlers'):
                    handler_containers.append(attr)
        
        return handler_containers

    def _cleanup_extension_from_router(self, router: aiogram.Router, module_name: str) -> None:
        self._remove_handlers_from_router(router, module_name)
        
        # Recursively process sub-routers
        for sub_router in router.sub_routers[:]: # copy of the list
            if hasattr(sub_router, '__module__') and sub_router.__module__ == module_name:
                router.sub_routers.remove(sub_router)
            else:
                self._cleanup_extension_from_router(sub_router, module_name)
    
    def _remove_handlers_from_router(self, router: aiogram.Router, module_name: str) -> None:
        """Remove all module-specific handlers from the router."""
        handler_types = self.get_all_handlers(router)

        for handler_type in handler_types:
            if hasattr(router, handler_type):
                handler_container = getattr(router, handler_type)

                # Handler filter (removes all module-specific handlers)
                filtered_handlers = []
                for handler in handler_container.handlers:
                    if not self._is_handler_from_module(handler, module_name):
                        filtered_handlers.append(handler)

                handler_container.handlers = filtered_handlers
    
    def _is_handler_from_module(self, handler: HandlerObject, module_name: str) -> bool:
        """Check if handler is associated with the specified module name."""
        if not hasattr(handler, 'callback'):
            return False
        
        callback = handler.callback
        
        # Check module of the handler
        if hasattr(callback, '__module__'):
            if callback.__module__ == module_name:
                return True
        
        # Для методов классов проверяем модуль класса
        # Нужно для случаев кастомных классов в коге

        # For class methods
        if hasattr(callback, '__self__'):  # it is class method
            cls = callback.__self__.__class__
            if cls.__module__ == module_name:
                return True
        
        return False

    def load_extensions(self, path: str) -> None:
            for extension in Other.search_directory(path):
                self.load_extension(extension)
            
    def load_extension(self, key: str, *, package: Optional[str] = None) -> None:
        try:
            key = importlib.util.resolve_name(key, package)
        except ImportError as e:
            raise errors.ExtensionNotFound(key) from e
        
        if key in self.__extensions:
            raise errors.ExtensionAlreadyLoaded(key)

        spec = importlib.util.find_spec(key)
        if spec is None:
            raise errors.ExtensionNotFound(key)

        lib = importlib.util.module_from_spec(spec)
        sys.modules[key] = lib

        try:
            spec.loader.exec_module(lib)
        except Exception as e:
            del sys.modules[key]
            raise errors.ExtensionFailed(key, e) from e

        try:
            setup = lib.setup
        except AttributeError:
            del sys.modules[key]
            raise errors.NoEntryPointError(key) from None

        setup(self)
        self.__extensions[key] = lib
        self.audit.info(f"Cog \"{lib.__name__}\" is ready!")

    def unload_extension(self, key: str, *, package: Optional[str] = None) -> None:
        try:
            key = importlib.util.resolve_name(key, package)
        except ImportError as e:
            raise errors.ExtensionNotFound(key) from e
        
        if key not in self.__extensions:
            raise errors.ExtensionNotLoaded(key)
        

        lib = self.__extensions[key]

        # Call teardown function if it exists
        if hasattr(lib, 'teardown'):
            try:
                lib.teardown(self)
            except Exception as e:
                self.audit.warning(f"Teardown of {key} raised an exception: {e}")


        # Deletes all routers related to module
        self._cleanup_extension_from_router(self.dp, key)
        del self.__extensions[key]
        
        # Double check
        if key in sys.modules and sys.modules[key] is lib:
            del sys.modules[key]
            importlib.invalidate_caches()

        self.audit.info(f"Extension \"{lib.__name__}\" has been unloaded!")

    def reload_extension(self, key: str, *, package: Optional[str] = None) -> None:
        try:
            self.unload_extension(key, package=package)
        except errors.ExtensionNotLoaded:
            pass
        
        self.load_extension(key, package=package)
        self.audit.info(f"Extension \"{key}\" reloaded!")

    def start_watching_extensions(self, path: str):
        if not os.path.exists(path):
            self.audit.error(f"Path does not exist: {path}")
            return
        event_handler = ExtensionEventHandler(self)
        self.__extension_observer.schedule(event_handler, path, recursive=False)  # Watch the extensions directory
        self.__extension_observer.start()
        self.audit.info(f"Started watching for changes in: {path}")
