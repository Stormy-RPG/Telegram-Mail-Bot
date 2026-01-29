# Copyright (C) 2026 Stormy-RPG
# SPDX-License-Identifier: AGPL-3.0-only
import sys
import asyncio
import argparse
import traceback

from dotenv import load_dotenv, dotenv_values

from aiohttp import web

from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties


from models.bot import TelegramMailBot
from models.dp import TelegramMailBotDispatcher
from utils.audit import AioHttpAccessLogger, Audit, handler_name_middleware


# Argument parser section
parser = argparse.ArgumentParser(description="Telegram Mail Bot \ndeveloper: Stormy RPG \nGitHub: https://github.com/Stormy-RPG/Telegram-Mail-Bot")
parser.add_argument("-mode", help="Bot operation mode: production or development", type=str, choices=["production", "development"], default="development", required=False)
args = parser.parse_args()


MODE = args.mode
find_env = load_dotenv()
env_dict = dotenv_values(".env")
audit = Audit(log_file="logs/telegram-mail-bot.log")

print("| Telegram Mail Bot \n| developer: Stormy RPG \n| GitHub: https://github.com/Stormy-RPG/Telegram-Mail-Bot\n")


# .env validation section
if find_env:
    print("\".env\" file found!")
    
    missing_keys = [key for key in ["DEVELOPMENT_TELEGRAM_API_TOKEN", "PRODUCTION_TELEGRAM_API_TOKEN"] if not env_dict.get(key)]
    if missing_keys:
        print(f"The following keys are missing from the .env file: {', '.join(missing_keys)}")
        sys.exit()
else:
    print("\".env\" file not found.")
    sys.exit()

PRODUCTION_TOKEN = env_dict.get("PRODUCTION_TELEGRAM_API_TOKEN")
DEVELOPMENT_TOKEN = env_dict.get("DEVELOPMENT_TELEGRAM_API_TOKEN")
TOKEN = PRODUCTION_TOKEN if MODE == "production" else DEVELOPMENT_TOKEN

GITHUB_TOKEN = env_dict.get("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    GITHUB_TOKEN = None


# Main bot section
http_server = web.Application(middlewares=[handler_name_middleware])
dp = TelegramMailBotDispatcher()

bot = TelegramMailBot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML), 
    dp=dp,

    mode=MODE,
    version="1.0.0",
    audit=audit,
    http_server=http_server,
    github_token=GITHUB_TOKEN,
    reload=True,
    reload_path="cogs"
)

async def bot_start():
    bot.audit.info("Setting bot token...")
    bot.audit.info("Loading extensions...")
    bot.load_extensions("cogs")
    bot.audit.info(f"Starting the Telegram bot. Mode: {MODE}")

    bot_name = await bot.get_my_name()

    bot.audit.info("◼" * 60)
    bot.audit.info(f"Bot {bot_name.name!r} (v{bot.version}) | {bot.id} is running!")
    bot.audit.info("◼" * 60)
    await bot.run()

async def run_http_server():
    await web._run_app(
        app=http_server,
        host="0.0.0.0",
        port=4022,
        access_log=bot.audit._logger,
        access_log_format="%a \"%{User-Agent}i\" - \"%r\" %s %Tf" ,
        access_log_class=AioHttpAccessLogger,
        print=None
    )

async def main():
    bot.audit.info("Starting...")

    task1 = asyncio.create_task(bot_start())
    task2 = asyncio.create_task(run_http_server())
    await task1
    await task2

if __name__ == "__main__":
    try:
        bot.audit.info("File is started as __main__")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print('Exit -> Done')
    except Exception as e: 
        print(traceback.format_exc())