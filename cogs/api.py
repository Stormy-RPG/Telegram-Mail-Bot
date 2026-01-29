# Copyright (C) 2026 Stormy-RPG
# SPDX-License-Identifier: AGPL-3.0-only
from aiohttp import web

from models.bot import TelegramMailBot


def setup(bot: TelegramMailBot):

    async def uptime(self, request: web.Request):
        return web.Response(body="OK")
    
    bot.http_server.router.add_get("/api/uptime", uptime)