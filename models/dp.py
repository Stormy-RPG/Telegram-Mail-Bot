# Copyright (C) 2026 Stormy-RPG
# SPDX-License-Identifier: AGPL-3.0-only
import asyncio

import aiogram
from aiogram.fsm.strategy import FSMStrategy
from aiogram.fsm.storage.base import BaseEventIsolation, BaseStorage


class TelegramMailBotDispatcher(aiogram.Dispatcher):
    def __init__(self, *, 
            storage: BaseStorage | None = None,
            fsm_strategy: FSMStrategy = FSMStrategy.USER_IN_CHAT,
            events_isolation: BaseEventIsolation | None = None,
            disable_fsm: bool = False,
            name: str | None = None,
            **kwargs
        ):
        self.__on_readys = []
        super().__init__(
            storage=storage,
            fsm_strategy=fsm_strategy,
            events_isolation=events_isolation,
            disable_fsm=disable_fsm,
            name=name,
            **kwargs
        )

    def on_startup(self, func):
        """Decorator to register a function for execution on bot startup."""
        self.__on_readys.append(func)
        return func

    async def run_startup(self):
        """Executes all registered startup functions."""
        for func in self.__on_readys:
            if asyncio.iscoroutinefunction(func):
                await func()
            else:
                func()