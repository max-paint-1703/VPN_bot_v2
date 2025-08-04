### Полное руководство по развертыванию Telegram бота для выдачи WireGuard конфигов в Docker

---

#### 1. Структура проекта
```
/wireguard-bot
├── /configs
│   ├── /available         # Исходные конфиги (.conf файлы)
│   └── /used              # Использованные конфиги (создается автоматически)
├── /data
│   └── bot.log            # Файл логов (создается автоматически)
├── .env                   # Конфигурационные переменные
├── bot.py                 # Основной код бота
├── Dockerfile             # Конфигурация Docker
├── docker-compose.yml     # Конфигурация Docker Compose
└── requirements.txt       # Зависимости Python
```

---

#### 2. Файлы конфигурации

**.env** (замените значения на свои):
```ini
TOKEN=ваш_токен_от_BotFather
ADMIN_ID=ваш_telegram_id
```

**requirements.txt**:
```
python-telegram-bot==20.3
python-dotenv==1.0.0
```

**Dockerfile**:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/configs/available /app/configs/used /app/data

CMD ["python", "bot.py"]
```

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  telegram-bot:
    build: .
    container_name: wireguard-bot
    restart: unless-stopped
    volumes:
      - ./configs:/app/configs
      - ./data:/app/data
    env_file:
      - .env
```

---

#### 3. Код бота (bot.py)

```python
import os
import shutil
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler
)

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv('TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')

# Пути к директориям
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AVAILABLE_DIR = os.path.join(BASE_DIR, 'configs', 'available')
USED_DIR = os.path.join(BASE_DIR, 'configs', 'used')
LOG_FILE = os.path.join(BASE_DIR, 'data', 'bot.log')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename=LOG_FILE
)
logger = logging.getLogger(__name__)

# Словарь для хранения ожидающих запросов
pending_requests = {}

def check_configs():
    """Проверка наличия доступных конфигов"""
    if not os.path.exists(AVAILABLE_DIR):
        os.makedirs(AVAILABLE_DIR)
    if not os.path.exists(USED_DIR):
        os.makedirs(USED_DIR)
    
    configs = [f for f in os.listdir(AVAILABLE_DIR) if f.endswith('.conf')]
    logger.info(f"Доступно конфигов: {len(configs)}")
    return configs

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user = update.message.from_user
    logger.info(f"Пользователь {user.id} запустил бота")
    
    keyboard = [[InlineKeyboardButton("🔑 Запросить конфиг", callback_data='request_config')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Привет, {user.first_name}!\n"
        "Я бот для выдачи конфигураций WireGuard VPN\n\n"
        "⚠️ Для работы бота необходимо:\n"
        "1. Начать приватный чат со мной (@KaratVpn_bot)\n"
        "2. Не блокировать бота\n"
        "3. Ожидать подтверждения администратора",
        reply_markup=reply_markup
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия кнопок"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'request_config':
        await get_config(update, context)

async def get_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса конфига"""
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user = query.from_user if query else update.message.from_user
    
    logger.info(f"Запрос конфига от {user.id}")
    
    try:
        await context.bot.send_chat_action(chat_id=user.id, action='typing')
    except Exception as e:
        logger.error(f"Чат с пользователем {user.id} недоступен: {e}")
        message = "⚠️ Для выдачи конфига напишите мне в личные сообщения @KaratVpn_bot"
        if query:
            await query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return
    
    configs = check_configs()
    if not configs:
        message = "⚠️ Все ключи временно закончились. Администратор уведомлен."
        if query:
            await query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        await notify_admin(context, "⚠️ ВНИМАНИЕ! Закончились доступные конфиги!")
        return
    
    config_file = configs[0]
    pending_requests[user.id] = config_file
    
    username = f"@{user.username}" if user.username else "нет username"
    request_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    admin_message = (
        f"🆕 Новый запрос конфига:\n"
        f"👤 Имя: {user.full_name}\n"
        f"📌 Username: {username}\n"
        f"🆔 ID: {user.id}\n"
        f"🕒 Время: {request_time}\n"
        f"📁 Файл: {config_file}"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Принять", callback_data=f"approve_{user.id}"),
         InlineKeyboardButton("❌ Отказать", callback_data=f"reject_{user.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_message,
            reply_markup=reply_markup
        )
        message = "✅ Ваш запрос отправлен администратору. Ожидайте решения."
        if query:
            await query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения администратору: {e}")
        message = "⚠️ Ошибка при обработке запроса. Попробуйте позже."
        if query:
            await query.edit_message_text(message)
        else:
            await update.message.reply_text(message)

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий администратора"""
    query = update.callback_query
    await query.answer()
    
    try:
        action, user_id = query.data.split('_')
        user_id = int(user_id)
        config_file = pending_requests.get(user_id)
        
        if not config_file:
            await query.edit_message_text("⚠️ Запрос не найден или уже обработан")
            return
        
        try:
            await context.bot.send_chat_action(chat_id=user_id, action='typing')
        except Exception as e:
            logger.error(f"Чат с пользователем {user_id} недоступен: {e}")
            await query.edit_message_text(f"❌ Не удалось отправить конфиг пользователю {user_id}")
            del pending_requests[user_id]
            return
        
        if action == "approve":
            src_path = os.path.join(AVAILABLE_DIR, config_file)
            dest_path = os.path.join(USED_DIR, config_file)
            
            try:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=open(src_path, 'rb'),
                    caption=f"Ваш конфиг: {config_file}"
                )
                shutil.move(src_path, dest_path)
                await query.edit_message_text(f"✅ Конфиг выдан пользователю ID: {user_id}")
                logger.info(f"Конфиг {config_file} выдан {user_id}")
            except Exception as e:
                logger.error(f"Ошибка выдачи конфига {user_id}: {e}")
                await query.edit_message_text(f"🚫 Ошибка выдачи конфига: {e}")
            finally:
                if user_id in pending_requests:
                    del pending_requests[user_id]
        
        elif action == "reject":
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Ваш запрос отклонён администратором"
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")
            
            await query.edit_message_text(f"❌ Запрос пользователя ID: {user_id} отклонён")
            if user_id in pending_requests:
                del pending_requests[user_id]
    
    except Exception as e:
        logger.error(f"Ошибка в обработке callback: {e}")
        await query.edit_message_text("⚠️ Ошибка при обработке запроса")

async def notify_admin(context: ContextTypes.DEFAULT_TYPE, message: str):
    """Уведомление администратора"""
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=message
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления администратора: {e}")

def main():
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("get_config", get_config))
    application.add_handler(CallbackQueryHandler(handle_button, pattern='^request_config$'))
    application.add_handler(CallbackQueryHandler(handle_admin_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("Используйте /start или кнопку запроса")))
    
    configs = check_configs()
    if not configs:
        logger.warning("Нет доступных конфигов!")
    
    logger.info("Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()
```

---

#### 4. Пошаговая инструкция по запуску

1. **Подготовка сервера**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install docker.io docker-compose -y
   sudo systemctl enable docker
   ```

2. **Создание структуры проекта**:
   ```bash
   mkdir -p wireguard-bot/{configs/available,data}
   cd wireguard-bot
   touch .env Dockerfile docker-compose.yml requirements.txt bot.py
   ```

3. **Поместите все WireGuard конфиги** в папку `configs/available`

4. **Настройте .env файл** как указано выше

5. **Соберите и запустите контейнер**:
   ```bash
   docker-compose up -d --build
   ```

6. **Проверьте работу бота**:
   ```bash
   docker logs -f wireguard-bot
   ```

---

#### 5. Дополнительные команды

- **Остановка бота**:
  ```bash
  docker-compose down
  ```

- **Перезапуск с обновлениями**:
  ```bash
  docker-compose up -d --build
  ```

- **Просмотр логов**:
  ```bash
  docker logs -f wireguard-bot
  # Или в файле:
  tail -f data/bot.log
  ```

- **Добавление новых конфигов**:
  ```bash
  # Просто скопируйте новые .conf файлы в:
  wireguard-bot/configs/available/
  # Затем перезапустите бота:
  docker-compose restart
  ```

---

#### 6. Важные особенности

1. **Автозапуск при перезагрузке**:
   - Docker Compose с политикой `restart: unless-stopped` обеспечивает автоматический запуск

2. **Хранение данных**:
   - Все конфиги и логи сохраняются на хосте и не теряются при обновлении контейнера

3. **Безопасность**:
   - Убедитесь, что файл `.env` не доступен публично
   - Ограничьте права доступа: `chmod 600 .env`

4. **Мониторинг**:
   - Регулярно проверяйте логи в `data/bot.log`
   - Настройте алерты при ошибках

5. **Резервное копирование**:
   - Регулярно копируйте папки `configs` и `data`

---
