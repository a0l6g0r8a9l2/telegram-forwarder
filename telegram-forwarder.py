import os
import json
import logging
import asyncio
import re
from datetime import datetime
import requests
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("telegram_forwarder.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Конфигурация из переменных окружения
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://alexgruzdev.space/webhook-test/cebe55e0-2ed8-4b21-ad31-f3cee4f7d43f')
SESSION_NAME = os.getenv('SESSION_NAME', 'telegram_forwarder')
MAX_REQUESTS_PER_MINUTE = int(os.getenv('MAX_REQUESTS_PER_MINUTE', 20))
REQUEST_RETRY_COUNT = int(os.getenv('REQUEST_RETRY_COUNT', 2))
REQUEST_RETRY_DELAY = int(os.getenv('REQUEST_RETRY_DELAY', 1))

# Регулярное выражение для поиска URL в тексте
URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')

# Загрузить список телеграм чатов из json
def load_tg_chats_shortlist(file: str = 'tg-channels-short-list - crypto.json') -> list[dict]:
    try:
        shortlist = json.loads(file)
    except Exception as e:
        logger.error('Cant load tg chats shortlist')
    return shortlist

# Ограничитель запросов
class RateLimiter:
    def __init__(self, max_requests, time_window=60):
        self.max_requests = max_requests
        self.time_window = time_window  # в секундах
        self.requests_timestamps = []

    async def wait_if_needed(self):
        """Ожидает, если превышен лимит запросов"""
        now = datetime.now().timestamp()
        
        # Удаление устаревших временных меток
        self.requests_timestamps = [ts for ts in self.requests_timestamps 
                                   if now - ts < self.time_window]
        
        # Если достигнут лимит запросов, ожидаем
        if len(self.requests_timestamps) >= self.max_requests:
            oldest_timestamp = min(self.requests_timestamps)
            wait_time = self.time_window - (now - oldest_timestamp)
            if wait_time > 0:
                logger.info(f"Rate limit reached. Waiting for {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)
        
        # Добавление новой временной метки
        self.requests_timestamps.append(datetime.now().timestamp())

# Функция для отправки данных на API
async def send_to_webhook(data, rate_limiter):
    """Отправляет данные на указанный webhook с обработкой ошибок и повторными попытками"""
    await rate_limiter.wait_if_needed()
    
    for attempt in range(REQUEST_RETRY_COUNT + 1):
        try:
            logger.info(f"Sending data to webhook. Attempt {attempt + 1}")
            response = requests.post(
                WEBHOOK_URL,
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"Successfully sent data to webhook. Status code: {response.status_code}")
                return True
            else:
                logger.warning(f"Failed to send data. Status code: {response.status_code}, Response: {response.text}")
                
                if attempt < REQUEST_RETRY_COUNT:
                    logger.info(f"Retrying in {REQUEST_RETRY_DELAY} seconds...")
                    await asyncio.sleep(REQUEST_RETRY_DELAY)
                else:
                    logger.error("Max retry attempts reached. Giving up.")
                    return False
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception: {str(e)}")
            
            if attempt < REQUEST_RETRY_COUNT:
                logger.info(f"Retrying in {REQUEST_RETRY_DELAY} seconds...")
                await asyncio.sleep(REQUEST_RETRY_DELAY)
            else:
                logger.error("Max retry attempts reached. Giving up.")
                return False

async def extract_media_urls(message, client):
    """Извлекает URL-адреса из медиаконтента сообщения"""
    if not message.media:
        return []
    
    media_urls = []
    
    try:
        if isinstance(message.media, MessageMediaPhoto):
            # Для фото пытаемся получить ссылку на фото максимального размера
            if hasattr(message.media, 'photo'):
                media_urls.append({
                    "type": "photo",
                    "url": f"https://t.me/{message.chat.username}/{message.id}" if message.chat and hasattr(message.chat, 'username') else None,
                    "description": "Photo from Telegram"
                })
        
        elif isinstance(message.media, MessageMediaDocument):
            # Для документов (файлов, видео, аудио и т.д.)
            doc = message.media.document
            mime_type = doc.mime_type if hasattr(doc, 'mime_type') else "unknown"
            
            media_type = "document"
            if mime_type.startswith("video/"):
                media_type = "video"
            elif mime_type.startswith("audio/"):
                media_type = "audio"
            elif mime_type.startswith("image/"):
                media_type = "image"
            
            media_urls.append({
                "type": media_type,
                "url": f"https://t.me/{message.chat.username}/{message.id}" if message.chat and hasattr(message.chat, 'username') else None,
                "mime_type": mime_type,
                "description": f"{media_type.capitalize()} from Telegram"
            })
        
        elif isinstance(message.media, MessageMediaWebPage):
            # Для встроенных веб-страниц
            if hasattr(message.media.webpage, 'url'):
                media_urls.append({
                    "type": "webpage",
                    "url": message.media.webpage.url,
                    "description": getattr(message.media.webpage, 'title', 'Web page') or 'Web page'
                })
    
    except Exception as e:
        logger.error(f"Error extracting media URLs: {str(e)}")
    
    return media_urls

async def main():
    """Главная функция"""
    if not all([API_ID, API_HASH, PHONE_NUMBER]):
        logger.error("Missing required environment variables. Please check your .env file.")
        return

    logger.info("Starting Telegram Forwarder")
    
    # Создание клиента Telegram
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    # Создание ограничителя запросов
    rate_limiter = RateLimiter(MAX_REQUESTS_PER_MINUTE)
    
    try:
        # Запуск клиента
        await client.start(phone=PHONE_NUMBER)
        logger.info("Successfully connected to Telegram")
        
        # Обработчик новых сообщений
        @client.on(events.NewMessage)
        async def handle_new_message(event):
            # Идентификаторы каналов, сообщения по которым нуэно обрабатывать
            chats_shortlist = load_tg_chats_shortlist()
            chats_shortlist_ids = [i.get('channel_id') for i in chats_shortlist]

            try:
                # Получение сообщения
                message = event.message
                
                # Получение информации о чате
                chat = await event.get_chat()
                chat_id = event.chat_id

                if chat_id in chats_shortlist_ids:
                    chat_category = [c.get('category') for c in chats_shortlist if c.get('channel_id') == chat_id][0]

                    chat_title = getattr(chat, 'title', None) or f"Chat {chat_id}"
                
                    # Извлечение текста сообщения
                    text = message.text if message.text else ""

                    # Определение наличия медиа
                    has_media = message.media is not None
                    media_type = str(message.media.__class__.__name__) if has_media else None

                    # Извлечение URL из текста и создание объектов для них
                    text_urls = URL_PATTERN.findall(text)
                    url_objects = [{"type": "text_link", "url": url, "description": "URL from text"} for url in text_urls]

                    # Извлечение URL из медиаконтента
                    media_url_objects = await extract_media_urls(message, client) if has_media else []

                    # Объединение всех URL в один массив
                    all_urls = url_objects + media_url_objects

                    # Формирование данных для отправки
                    data = {
                        "channel_name": chat_title,
                        "channel_id": chat_id,
                        "chat_category": chat_category,
                        "message_text": text,
                        "urls": all_urls,
                        "has_media": has_media,
                        "media_type": media_type,
                        "timestamp": datetime.now().isoformat()
                    }

                    logger.info(f"New message from {chat_title} (ID: {chat_id})")

                    # Отправка данных на webhook
                    await send_to_webhook(data, rate_limiter)
                else:
                    logger.warning(f"Got message not from shortlist with id: {chat_id}")

                
                
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
        
        # Запуск обработки событий
        await client.run_until_disconnected()
        
    except SessionPasswordNeededError:
        logger.error("Two-factor authentication is enabled. Please disable it or handle it in your code.")
    except FloodWaitError as e:
        logger.error(f"Hit Telegram rate limit. Need to wait {e.seconds} seconds")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        if client.is_connected():
            await client.disconnect()
            logger.info("Disconnected from Telegram")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
