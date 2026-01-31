# Copyright (C) 2026 Stormy-RPG
# SPDX-License-Identifier: AGPL-3.0-only
import os
import re
import time
import email
import base64
import quopri
import asyncio
import imaplib
import hashlib
import secrets
import tempfile


from email.header import decode_header
from email.message import Message as MailMessage
from typing import List, Optional, TYPE_CHECKING, Tuple, Dict, Any

from dotenv import load_dotenv, dotenv_values


from aiogram import Router
from aiogram.types import FSInputFile, Message, BufferedInputFile, InputMediaPhoto
from aiogram.filters import Command

from utils.templates import MessageTemplate

if TYPE_CHECKING:
    from models.bot import TelegramMailBot

router = Router()


class MailForwarder:
    """Service for forwarding email messages to Telegram.
    
    This service connects to an email account via IMAP, retrieves new messages,
    and forwards them to a specified Telegram chat or group.
    
    Features:
    - Automatic email checking at configurable intervals
    - Support for email attachments
    - Markdown formatting for Telegram messages
    - Error handling and logging"""
    
    def __init__(self, 
                 bot: "TelegramMailBot", 
                 group_id: str, 
                 login: str,
                 password: str,
                 thread_id: Optional[int] = None, 
                 text_path: str = 'public/mail_forwarder.json', 
                 imap_host: str = 'imap.mail.ru', 
                 imap_port: int = 993
                 ):
        self.bot = bot
        self.group_id = group_id
        self.thread_id = thread_id
        self.task: Optional[asyncio.Task] = None
        self.stop_event = asyncio.Event()
        self.check_interval = 30
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.__login = login
        self.__password = password
        self.msg_template = MessageTemplate(text_path)
    
    def escape_markdown(self, text: str) -> str:
        """Escape special symbols for Telegram Markdown."""
        text = text.replace('\\', '\\\\')
        # escape_chars = r'_*[]()~`>#+-=|{}.!'
        escape_chars = r'_*~`#|'
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        re.sub(r'(?<!\\)\.', r'\\.', text)
        return text
    
    def escape_html(self, text: str) -> str:
        """Escape HTML special characters to prevent Telegram parsing errors."""
        text = text.replace('<', '&lt;').replace('>', '&gt;')
        return text
        

    def _get_decoded_filename(self, part) -> str:
        """Safely retrieves and decodes the attachment filename."""
        filename = part.get_filename()
        if not filename:
            return ""
        
        # Decode the filename
        decoded = decode_header(filename)[0]
        filename_part, encoding = decoded
        
        if isinstance(filename_part, bytes):
            charset = encoding or 'utf-8'
            try:
                return filename_part.decode(charset, errors='ignore')
            except Exception:
                return filename_part.decode('utf-8', errors='ignore')
        else:
            return str(filename_part)

    def _make_filename_safe(self, filename: str) -> str:
        """Makes filename safe by removing dangerous characters."""
        
        # Remove dangerous characters and path traversals
        safe = re.sub(r'[<>:"/\\|?*]', '_', filename)
        safe = re.sub(r'\.\.+', '.', safe)  # Remove ..
        safe = safe.lstrip('.')  # Remove leading dots
        safe = safe.strip()  # Strip whitespace
        
        # Limit length
        if len(safe) > 100:
            name, ext = os.path.splitext(safe) # extension and name of file
            safe = name[:95] + ext
        
        return safe if safe else "attachment"
    
    # The best function )
    def _save_to_temp_file(self, file_data: bytes, original_filename: str) -> Optional[str]:
        """Saves file to system temporary directory with a safe and unique filename."""

        # Create a safe filename
        safe_name = self._make_filename_safe(original_filename)
        if not safe_name:
            safe_name = "attachment"
        
        # Use system temporary directory
        temp_dir = tempfile.gettempdir()
        
        # Create unique identifier (timestamp + random)
        timestamp = int(time.time())
        random_part = secrets.token_hex(4)  # 8 random hex chars
        
        # Create file hash (SHA256 is more secure than MD5)
        file_hash = hashlib.sha256(file_data).hexdigest()[:16]  # 16 chars of SHA256
        
        # Construct unique filename
        safe_name = f"email_attach_{timestamp}_{random_part}_{file_hash}_{safe_name}"
        
        # Create full path
        temp_path = os.path.join(temp_dir, safe_name)
        
        # Atomic file creation to prevent race conditions
        try:
            # Open with exclusive creation (fails if file exists)
            fd = os.open(temp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(file_data)
            
            # Verify file was written correctly
            if os.path.getsize(temp_path) != len(file_data):
                self.bot.audit.error(f"File size mismatch for {temp_path}")
                os.unlink(temp_path)
                return None
                
            return temp_path
            
        except FileExistsError:
            # File already exists (extremely rare with our naming scheme)
            self.bot.audit.warning(f"Temporary file already exists: {temp_path}")
            # Try with a new random part
            return self._save_to_temp_file(file_data, original_filename)
            
        except Exception as e:
            self.bot.audit.error(f"Failed to save temporary file {temp_path}: {e}")
            # Clean up if file was partially created
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
            return None
    
    def cleanup_temp_files(self, temp_file_attachments: List[Dict[str, Any]]) -> None:
        """Deletes all temporary files from the list"""
        for attachment in temp_file_attachments:
            if 'temp_path' in attachment and os.path.exists(attachment['temp_path']):
                try:
                    os.unlink(attachment['temp_path'])
                    self.bot.audit.info(f"Deleted temporary file: {attachment['temp_path']}")
                except Exception as e:
                    self.bot.audit.error(f"Failed to delete temporary file {attachment['temp_path']}: {e}")


    def get_email_subject(self, msg: "MailMessage") -> str:
        """Email subject decoder"""
        # Extract email metadata
        subject = msg.get("Subject", "No Subject")

        # Decoder
        decoded_subject = decode_header(subject)
        subject_text = ""
        for part, encoding in decoded_subject:
            if isinstance(part, bytes):
                if encoding:
                    subject_text += part.decode(encoding, errors='ignore')
                else:
                    subject_text += part.decode('utf-8', errors='ignore')
            else:
                subject_text += str(part)

        return subject_text
    
    def get_email_sender(self, msg: "MailMessage") -> str:
        """Email sender decoder"""
        # Extract email metadata
        letter_from = msg.get("From", "Unknown")

        # Decoder
        decoded_from = decode_header(letter_from)
        from_text = ""
        for part, encoding in decoded_from:
            if isinstance(part, bytes):
                if encoding:
                    from_text += part.decode(encoding, errors='ignore')
                else:
                    from_text += part.decode('utf-8', errors='ignore')
            else:
                from_text += str(part)

        return from_text

    def get_email_body(self, msg: "MailMessage") -> str:
        """Email body decoder"""
        msg_text_parts = []

        for part in msg.walk():
            if (part.get_content_type() == 'text/plain' and part.get_content_disposition() != 'attachment'):
                payload = part.get_payload()
                
                encoding = part.get('Content-Transfer-Encoding', '').lower()
                charset = part.get_content_charset() or 'utf-8'

                # Decode based on content encoding
                try:
                    if encoding == 'base64':
                        decoded_bytes = base64.b64decode(payload)
                        text = decoded_bytes.decode(charset, errors='ignore')
                        
                    elif encoding == 'quoted-printable':
                        decoded_bytes = quopri.decodestring(payload)
                        text = decoded_bytes.decode(charset, errors='ignore')
                        
                    elif encoding in ['7bit', '8bit', 'binary', '']:
                        if isinstance(payload, bytes):
                            text = payload.decode(charset, errors='ignore')
                        else:
                            text = str(payload)
                            
                    else:
                        # For unknown encoding
                        if isinstance(payload, bytes):
                            text = payload.decode(charset, errors='ignore')
                        else:
                            text = str(payload)
                    
                    if text.strip():
                        msg_text_parts.append(text.strip())
                        
                except Exception as e:
                    msg_text_parts.append(str(payload))

        return "\n\n".join(msg_text_parts)

    def get_email_attachments(self, msg: MailMessage) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Splits attachments into two lists:
        1. Small (<10MB) - stored in RAM
        2. Large (≥10MB) - stored in temporary files
        
        Returns:
            Tuple[List[dict], List[dict]]: (in_memory_attachments, temp_file_attachments)
        """
        in_memory_attachments = []
        temp_file_attachments = []
        
        for part in msg.walk():
            # Skip non-attachments (email body and multipart containers)
            if part.get_content_maintype() == 'multipart':
                continue
            
            # Get filename
            filename = self._get_decoded_filename(part)
            if not filename:
                continue
            
            # Get attachment content (bytes)
            file_data = part.get_payload(decode=True)
            if not file_data:
                continue
            
            # Determine file size
            file_size = len(file_data)
            
            # Split by size
            if file_size < 10 * 1024 * 1024:  # < 10MB
                # Store in memory
                in_memory_attachments.append({
                    'filename': filename,
                    'content': file_data,  # Bytes in memory
                    'size': file_size,
                    'content_type': part.get_content_type(),
                    'content_disposition': part.get('Content-Disposition', ''),
                    'in_memory': True
                })
            else:
                # Save to temporary file
                temp_path = self._save_to_temp_file(file_data, filename)
                if temp_path:
                    temp_file_attachments.append({
                        'filename': filename,
                        'temp_path': temp_path,  # Path to temp file
                        'size': file_size,
                        'content_type': part.get_content_type(),
                        'content_disposition': part.get('Content-Disposition', ''),
                        'in_memory': False
                    })
                
                # Free memory (optional, Python handles this automatically)
                del file_data
        
        return in_memory_attachments, temp_file_attachments

    async def send_to_telegram(self,
        message_text: str,
        attachments: List[Dict[str, Any]] = list(),
        temp_files: List[Dict[str, Any]] = list(),
        pin: bool = False
    ) -> None:
        """
        Send message with files to Telegram.
        
        Args:
            message_text: Text message to send
            attachments: In-memory attachments list
            temp_files: Temporary files list
            pin: Whether to pin the message
        """

        # Prepare send parameters
        send_params = {'chat_id': self.group_id}
        if self.thread_id is not None:
            send_params['message_thread_id'] = self.thread_id

        all_files = attachments + temp_files

        # Send text message
        sent_message = await self.bot.send_message(
            text=message_text,
            parse_mode='Markdown',
            **send_params
        )

        if all_files:
            # Separate files into images and other types
            image_extensions = ('.png', '.jpg', '.jpeg')
            images = [f for f in all_files if f['filename'].lower().endswith(image_extensions)]
            other_files = [f for f in all_files if not f['filename'].lower().endswith(image_extensions)]
            
            # Send images in media groups (max 10 per group)
            if images:
                MAX_GROUP_SIZE = 10
                for i in range(0, len(images), MAX_GROUP_SIZE):
                    group = images[i:i + MAX_GROUP_SIZE]
                    media = []
                    
                    for file_info in group:
                        file_obj = BufferedInputFile(file_info['content'], file_info['filename']) if file_info.get('in_memory', True) else FSInputFile(file_info['temp_path'], file_info['filename'])
                        media.append(InputMediaPhoto(media=file_obj))
                    
                    await self.bot.send_media_group(media=media, **send_params)
                    
                    # Add delay between groups if not the last group
                    if i + MAX_GROUP_SIZE < len(images):
                        await asyncio.sleep(1)
            
            # Send other files one by one
            for file_info in other_files:
                file_obj = BufferedInputFile(file_info['content'], file_info['filename']) if file_info.get('in_memory', True) else FSInputFile(file_info['temp_path'], file_info['filename'])
                
                await self.bot.send_document(document=file_obj, parse_mode='Markdown', **send_params)
                
                # Add delay between document sends
                if other_files.index(file_info) < len(other_files) - 1:
                    await asyncio.sleep(2)

        # Pin message if requested
        if pin and sent_message:
            try:
                await sent_message.pin()
            except Exception:
                self.bot.audit.warning("Could not pin message")


    async def process_email(self, msg: "MailMessage") -> None:
        """
        Processes a single email message for Telegram forwarding.
        
        Extracts sender, subject, body, and attachments from an email,
        formats them for Telegram, and sends to the configured chat.
        
        Args:
            msg: Email message object to process
        """

        temp_files = {}
        try:
            subject_text = self.get_email_subject(msg)
            sender_text = self.get_email_sender(msg)
            body_text = self.get_email_body(msg)
            attachments, temp_files = self.get_email_attachments(msg)

            # Format message for Telegram
            msg_escaped = self.escape_markdown(body_text[:1000])
            ellipsis = "..." if len(body_text) > 1000 else ""
            message_text = self.msg_template.format(
                'new_email',
                sender=self.escape_markdown(sender_text),
                subject=self.escape_markdown(subject_text),
                message=msg_escaped,
                ellipsis=ellipsis
            )
            
            await self.send_to_telegram(message_text, attachments, temp_files, pin=True)
                    
        except Exception as e:
            self.bot.audit.error(f"Failed to process email: {e}")
            await self.send_to_telegram(self.msg_template.format('processing_error'))
        finally:
            # Clean up temporary files
            self.cleanup_temp_files(temp_files)
    
    async def check_new_mails(self) -> None:
        """Checks for new emails and forwards them to Telegram."""
        imap = None
        try:
            # Connect to mail server
            imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            imap.login(self.__login, self.__password)
            imap.select('INBOX')
            
            # Search for unread emails
            status, messages = imap.search(None, 'UNSEEN')
            if status != 'OK' or not messages[0]:
                # self.bot.audit.info("No new emails found")
                return
            
            msg_nums = messages[0].split()
            self.bot.audit.info(f"Found {len(msg_nums)} new email(s)")
            
            for msg_num in msg_nums:
                try:
                    # Fetch the email
                    status, msg_data = imap.fetch(msg_num, '(RFC822)')
                    if status != 'OK' or not msg_data[0]:
                        self.bot.audit.warning(f"Failed to fetch email {msg_num}")
                        await self.send_to_telegram(self.msg_template.format('fetch_error'))
                        continue
                    
                    # Parse email
                    msg = email.message_from_bytes(msg_data[0][1])
                    
                    # Process email
                    await self.process_email(msg)
                    
                    # Mark as read
                    imap.store(msg_num, '+FLAGS', '\\Seen')
                    
                    self.bot.audit.info(f"Successfully processed email {msg_num}")
                    
                except Exception as e:
                    self.bot.audit.error(f"(Global) Error processing email {msg_num}: {e}")
        
        except imaplib.IMAP4.error as e:
            self.bot.audit.error(f"IMAP connection error: {e}")
        except Exception as e:
            self.bot.audit.error(f"Unexpected error in email checking: {e}")
        
        finally:
            # Close connection
            if imap:
                try:
                    imap.close()
                    imap.logout()
                except Exception as e:
                    self.bot.audit.warning(f"Error during IMAP logout: {e}")
    
    async def start_monitoring(self) -> None:
        """Starts email monitoring using asyncio.Event"""
        # Clear the stop event in case it was set before
        self.stop_event.clear()
        
        self.bot.audit.info("Email monitoring started")
        
        while not self.stop_event.is_set():
            try:
                await self.check_new_mails()
            except asyncio.CancelledError:
                self.bot.audit.info("Monitoring task cancelled")
                break
            except Exception as e:
                self.bot.audit.error(f"Error in monitoring: {e}")
            
            # Wait for either interval timeout or stop event
            try:
                # Wait for stop event with timeout = check_interval
                # If stop event is set before timeout, wait_for will raise TimeoutError
                # If timeout occurs first, wait_for raises TimeoutError
                await asyncio.wait_for(
                    self.stop_event.wait(),
                    timeout=self.check_interval
                )
            except asyncio.TimeoutError:
                # Normal case: timeout occurred, continue monitoring
                continue
        
        self.bot.audit.info("Email monitoring stopped")
    
    async def stop(self) -> None:
        """Stops email monitoring"""
        if self.task and not self.task.done():
            # Set stop event to signal the monitoring loop to stop
            self.stop_event.set()
            
            # Wait for the task to complete (with timeout)
            try:
                await asyncio.wait_for(self.task, timeout=5.0)
                self.bot.audit.info("Monitoring stopped gracefully")
            except asyncio.TimeoutError:
                # Force cancel if graceful stop times out
                self.bot.audit.warning("Force cancelling monitoring task")
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    self.bot.audit.error(f"Error during forced stop: {e}")
        else:
            self.bot.audit.info("No active monitoring task to stop")

    @property
    def is_monitoring(self) -> bool:
        """Check if monitoring is active"""
        return not self.stop_event.is_set()


@router.message(Command("mail_status"))
async def mail_status_command(message: Message):
    """Shows email monitoring status."""
    
    # Check if mail forwarder is initialized
    if not hasattr(message.bot, '_mail_forwarder'):
        await message.answer("❌ Mail forwarding service is not initialized.")
        return
    
    # Get forwarder instance
    forwarder = message.bot._mail_forwarder
    
    if forwarder.is_monitoring:
        status_text = forwarder.msg_template.format(
            'mail_status_active',
            group_id=forwarder.group_id,
            check_interval=forwarder.check_interval
        )
    else:
        status_text = forwarder.msg_template.format(
            'mail_status_inactive',
            group_id=forwarder.group_id,
            check_interval=forwarder.check_interval
        )
    
    await message.answer(status_text)


@router.message(Command("mail_check"))
async def mail_check_command(message: Message):
    """Immediately checks for new emails."""
    
    # Check if mail forwarder is initialized
    if not hasattr(message.bot, '_mail_forwarder'):
        await message.answer("❌ Mail forwarding service is not initialized.")
        return
    
    forwarder = message.bot._mail_forwarder
    
    await message.answer(forwarder.msg_template.format('mail_check_started'))
    
    try:
        await forwarder.check_new_mails()
        await message.answer(forwarder.msg_template.format('mail_check_completed'))
        message.bot.audit.info(f"Email checking has started | {message.from_user.full_name} ({message.from_user.id})")
    except Exception as e:
        error_text = forwarder.msg_template.format('mail_check_error')
        message.bot.audit.error(f"Error during mail check: {e}")
        await message.answer(error_text)


def setup(bot: "TelegramMailBot"):
    """
    Initialization of the mail forwarding module.
    
    Requires environment variables:
    - MODULE_TEXT: Path to the messages file
    - IMAP_HOST: IP address or domain of the IMAP host
    - IMAP_PORT: IMAP port
    - MAIL_LOGIN: Email login
    - MAIL_PASSWORD: Email password
    - GROUP_ID: Chat ID for forwarding
    - THREAD_ID: Thread ID (optional)
    """

    # Check for required environment variables
    find_env = load_dotenv()
    env_dict = dotenv_values(".env")
    required_keys = ['MODULE_TEXT', 'IMAP_HOST', 'IMAP_PORT', 'MAIL_LOGIN', 'MAIL_PASSWORD', 'GROUP_ID']

    if find_env:
        missing_keys = [key for key in required_keys if not env_dict.get(key)]
        if missing_keys:
            bot.audit.error(f"Missing required environment variables: {', '.join(missing_keys)}")
            raise ValueError(f"Missing required environment variables: {', '.join(missing_keys)}")
    else:
        bot.audit.error("\".env\" file not found.")
        raise FileNotFoundError("\".env\" file not found.")

    
    module_text = env_dict.get('MODULE_TEXT')
    imap_host = env_dict.get('IMAP_HOST')
    imap_port = env_dict.get('IMAP_PORT')
    mail_login = env_dict.get('MAIL_LOGIN')
    mail_password = env_dict.get('MAIL_PASSWORD')
    group_id = env_dict.get('GROUP_ID')
    thread_id = env_dict.get('THREAD_ID')
    
    # Group ID validator
    if not group_id.startswith('-'):
        raise ValueError(f"Invalid GROUP_ID: {group_id}. Must be negative for groups/channels")
    
    if thread_id is not None and not group_id.startswith('-100'):
        raise ValueError(
            f"Cannot use THREAD_ID in basic group. "
            f"GROUP_ID must start with '-100' for supergroups with topics. "
            f"Got: {group_id}"
        )
    
    if group_id.startswith('-100') and thread_id is None:
        bot.audit.info("Using supergroup without topics. Thread ID is optional.")
    
    # Convert group data to int
    try:
        group_id = int(group_id.strip())
        if thread_id and thread_id.strip():
            thread_id = int(thread_id.strip())
    except ValueError:
        bot.audit.error(f"Invalid data: {group_id} | {thread_id}")
        raise ValueError(f"Invalid data: {group_id} | {thread_id}")
    
    forwarder = MailForwarder(
        bot=bot,
        group_id=group_id,
        login=mail_login,
        password=mail_password,
        text_path=module_text,
        thread_id=thread_id,
        imap_host=imap_host,
        imap_port=imap_port
    )
    
    # Start forwarder
    bot._mail_forwarder = forwarder
    forwarder.task = asyncio.create_task(forwarder.start_monitoring())
    bot.dp.include_router(router)
    
    bot.audit.info(f"Mail forwarding module loaded. Login: {mail_login}, Group: {group_id}")


async def teardown(bot: "TelegramMailBot"):
    """Clean up mail forwarding module resources."""
    if not hasattr(bot, '_mail_forwarder'):
        return
    
    forwarder = bot._mail_forwarder
    
    if forwarder.task and not forwarder.task.done():
        try:
            # Try graceful shutdown with 3 second timeout
            await asyncio.wait_for(forwarder.stop(), timeout=3.0)
        except asyncio.TimeoutError:
            # Force cancel on timeout
            forwarder.task.cancel()
            try:
                await forwarder.task
            except asyncio.CancelledError:
                pass
    
    if hasattr(bot, '_mail_forwarder'):
        delattr(bot, '_mail_forwarder')