# Telegram-Mail-Bot

Telegram bot for forwarding emails (via IMAP) to a specified Telegram channel or group.

## Languages

* [English](README.md)
* [Русский](README_RU.md)

## Description

This bot monitors the specified mailbox via the IMAP protocol and automatically forwards new messages to the specified Telegram channel or group. It is built on the aiogram library for interacting with the Telegram API and supports a modular structure using "cogs" for extensibility. Additionally, the bot runs an HTTP server on port 4022 for monitoring or other needs.

Key features:

* Automatic forwarding of unread emails to Telegram.
* Support for development and production modes.
* Event logging through the audit system.
* Docker integration for easy deployment.
* Optional GitHub integration. A function to retrieve the timestamp of the last commit is implemented in utils/other.py. It can be used in any module if necessary.

The bot is developed in Python and licensed under AGPL-3.0-only.

## Requirements

* Python 3.10+ (recommended 3.13.3).
* Libraries: listed in requirements.txt.
* Access to an IMAP server (e.g., Gmail, Yandex.Mail).
* Telegram Bot Token (obtain from @BotFather).
* Docker and Docker Compose for containerization (optional).

## Installation

### Docker (recommended)

1. Clone the repository:

   ```
   git clone https://github.com/Stormy-RPG/Telegram-Mail-Bot.git
   cd Telegram-Mail-Bot
   ```
2. Copy the example configuration:

   ```
   cp .env.example .env
   ```

   Fill .env with necessary values (see "Configuration" section).
3. Build and run the container:

   ```
   make up
   ```

   Or manually:

   ```
   docker compose up -d
   ```
4. To view logs:

   ```
   make logs -B
   ```

### Manual Installation

1. Clone the repository (as above).
2. Install dependencies (recommended to use venv):

   ```
   pip install -r requirements.txt
   ```
3. Copy and fill .env (as above).
4. Run the bot:

   ```
   python main.py -mode production
   ```

   (Or -mode development for development).

## Configuration

Configuration is done via the .env file. Example:

```
# ----- GENERAL SETTINGS -----
PRODUCTION_TELEGRAM_API_TOKEN=your_production_token
DEVELOPMENT_TELEGRAM_API_TOKEN=your_development_token
# Optional - leave empty if not used
GITHUB_TOKEN=github_token

# ----- Email-to-Telegram forwarder -----
MODULE_TEXT=public/mail_forwarder.json  # Relative path to .json file containing message localization
IMAP_HOST=imap.example.com  # For example, imap.gmail.com
IMAP_PORT=993  # Standard port for IMAP over SSL
MAIL_LOGIN=your@email.com
MAIL_PASSWORD=your_password
GROUP_ID=-100xxxxxxxxxx  # ID of Telegram channel or group (use negative value for supergroups/channels)
# Optional - leave empty if not used
THREAD_ID=thread_id_in_group
```

* **TELEGRAM_API_TOKEN** : Required to specify at least one (depending on the mode).
* **IMAP_** *: Data for connecting to mail.
* **GROUP_ID** : ID of the target channel/group (bot must be an administrator).
* **THREAD_ID** : Optional, for forwarding to a specific thread in the group.

## Usage

After launch, the bot will automatically check mail and forward new messages to the specified channel.

* To stop: make down (Docker) or Ctrl+C (manual launch).
* Update: make update (pull from Git and restart).
* Logs are stored in ./logs (in Docker) or at the path specified in the code.

If errors occur, check the logs and ensure IMAP access is allowed (for Gmail, enable "Less secure app access" or use app password).

## Development

* Structure:
  * main.py: Entry point, bot and HTTP server initialization.
  * cogs/: Extension modules (e.g., for email processing).
  * utils/: Utilities (audit, middleware).
  * public/: Public files, such as mail_forwarder.json (bot message configuration).

To add new features, create new modules in the "cogs" folder.

## License

Copyright (C) 2026 Stormy-RPG.
License: AGPL-3.0-only.
See LICENSE file for details.

## Contacts

Developer: Stormy-RPG
GitHub: [https://github.com/Stormy-RPG/Telegram-Mail-Bot](https://github.com/Stormy-RPG/Telegram-Mail-Bot)
If improvements are needed or there are questions, create an issue or pull request.
