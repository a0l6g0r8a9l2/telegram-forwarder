# Telegram Forwarder

Приложение для мониторинга сообщений из Telegram каналов и групп с пересылкой информации на внешний API.

## Описание

Приложение получает новые сообщения из Telegram каналов и групп, в которых состоит пользователь, и отправляет их на указанный webhook. Для каждого сообщения формируется JSON с данными о канале, тексте сообщения и найденных URL-адресах.

## Функциональность

- Мониторинг новых сообщений в каналах и группах Telegram
- Извлечение текста сообщений и URL-адресов
- Определение наличия медиа-контента и получение ссылок на медиафайлы
- Отправка данных на указанный webhook
- Ограничение количества запросов для избежания блокировок
- Повторные попытки при ошибках запросов
- Подробное логирование всех действий

## Требования

- Python 3.7+
- Docker (для контейнеризации)
- Telegram API credentials (api_id и api_hash)

## Установка и настройка

### Шаг 1: Получение Telegram API credentials

1. Перейдите на сайт [my.telegram.org](https://my.telegram.org/)
2. Войдите в свой аккаунт Telegram
3. Перейдите в раздел "API development tools"
4. Создайте новое приложение, заполнив необходимые поля
5. Получите `api_id` и `api_hash`

### Шаг 2: Настройка переменных окружения

Создайте файл `.env` на основе примера:

```
# Telegram API credentials
API_ID=your_api_id
API_HASH=your_api_hash
PHONE_NUMBER=+79001234567

# Webhook configuration
WEBHOOK_URL=https://alexgruzdev.space/webhook-test/cebe55e0-2ed8-4b21-ad31-f3cee4f7d43f

# Application settings
SESSION_NAME=telegram_forwarder
MAX_REQUESTS_PER_MINUTE=20
REQUEST_RETRY_COUNT=2
REQUEST_RETRY_DELAY=1
```

Замените значения `your_api_id`, `your_api_hash` и `+79001234567` на свои данные.

### Шаг 3: Запуск с использованием Docker

#### Сборка Docker образа

```bash
docker build -t telegram-forwarder .
```

#### Запуск контейнера

```bash
docker run --env-file .env -v $(pwd)/session:/app/session -v $(pwd)/logs:/app/logs telegram-forwarder
```

При первом запуске вам может потребоваться авторизация в Telegram. В этом случае следуйте инструкциям в консоли.

### Шаг 4: Запуск без Docker (опционально)

1. Установите зависимости:

```bash
pip install -r requirements.txt
```

2. Запустите приложение:

```bash
python main.py
```

## Формат данных, отправляемых на webhook

```json
{
  "channel_name": "Название канала или группы",
  "channel_id": 1234567890,
  "message_text": "Текст сообщения",
  "urls": [
    {
      "type": "text_link",
      "url": "https://example.com",
      "description": "URL from text"
    },
    {
      "type": "photo",
      "url": "https://t.me/channel_name/12345",
      "description": "Photo from Telegram"
    },
    {
      "type": "video",
      "url": "https://t.me/channel_name/12346",
      "mime_type": "video/mp4",
      "description": "Video from Telegram"
    }
  ],
  "has_media": true,
  "media_type": "MessageMediaPhoto",
  "timestamp": "2023-08-15T14:30:00.000000"
}
```

## Обработка URL и медиафайлов

Приложение обрабатывает следующие типы URL:

1. URL из текста сообщения - извлекаются с помощью регулярного выражения
2. URL медиафайлов - извлекаются из медиа-контента сообщения
3. URL встроенных веб-страниц

Каждый URL представлен в виде объекта со следующими полями:
- `type`: тип URL (text_link, photo, video, audio, document, webpage)
- `url`: сам URL-адрес
- `description`: описание URL
- `mime_type`: тип MIME для медиафайлов (опционально)

## Логирование

Логи сохраняются в файл `telegram_forwarder.log` и дублируются в консоль. Вы можете изменить настройки логирования в файле `main.py`.

## Настройка производительности

В файле `.env` можно настроить следующие параметры:

- `MAX_REQUESTS_PER_MINUTE`: Максимальное количество запросов к webhook в минуту
- `REQUEST_RETRY_COUNT`: Количество повторных попыток при ошибке запроса
- `REQUEST_RETRY_DELAY`: Задержка между повторными попытками (в секундах)

## Дополнительные настройки

### Автоматический перезапуск

Для обеспечения непрерывной работы приложения можно настроить автоматический перезапуск контейнера при сбоях:

```bash
docker run --restart=always --env-file .env -v $(pwd)/session:/app/session -v $(pwd)/logs:/app/logs telegram-forwarder
```

### Запуск как сервис (systemd)

Для запуска приложения как системный сервис в Linux:

1. Создайте файл `/etc/systemd/system/telegram-forwarder.service`:

```
[Unit]
Description=Telegram Forwarder Service
After=docker.service
Requires=docker.service

[Service]
Restart=always
ExecStart=/usr/bin/docker run --rm --name telegram-forwarder --env-file /path/to/.env -v /path/to/session:/app/session -v /path/to/logs:/app/logs telegram-forwarder
ExecStop=/usr/bin/docker stop telegram-forwarder

[Install]
WantedBy=multi-user.target
```

2. Активируйте и запустите сервис:

```bash
sudo systemctl enable telegram-forwarder
sudo systemctl start telegram-forwarder
```

## Устранение неполадок

### Проблемы с авторизацией

Если возникают проблемы с авторизацией в Telegram, убедитесь, что:
- Правильно указаны API_ID и API_HASH
- Номер телефона указан в международном формате (например, +79001234567)
- У вас не включена двухфакторная аутентификация (если включена, потребуется доработка кода)

### Ошибки подключения к Telegram API

Если возникают ошибки подключения к Telegram API:
- Проверьте интернет-соединение
- Убедитесь, что IP-адрес не заблокирован Telegram
- Проверьте ограничения на количество запросов

### Ошибки отправки на webhook

При ошибках отправки на webhook:
- Проверьте доступность URL
- Убедитесь, что формат данных соответствует ожидаемому
- Проверьте логи на наличие дополнительной информации об ошибках

## Ограничения

- Приложение не скачивает медиафайлы, а только извлекает ссылки на них
- Двухфакторная аутентификация не поддерживается по умолчанию
- Для работы необходим доступ к Telegram API

## Дальнейшие улучшения

- Добавление поддержки двухфакторной аутентификации
- Улучшение обработки различных типов медиа
- Добавление фильтрации каналов/групп
- Статистика по обработанным сообщениям
