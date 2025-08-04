import os
import shutil
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup
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

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
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
    
    # Создаем клавиатуру с кнопкой
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
    
    # Проверка доступности чата
    try:
        await context.bot.send_chat_action(chat_id=user.id, action='typing')
    except Exception as e:
        logger.error(f"Чат с пользователем {user.id} недоступен: {e}")
        message = (
            f"⚠️ Для выдачи конфига необходимо начать приватный чат с ботом.\n"
            f"Пожалуйста, напишите мне в личные сообщения @KaratVpn_bot"
        )
        if query:
            await query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return
    
    configs = check_configs()
    if not configs:
        message = (
            "⚠️ Извините, все ключи временно закончились.\n"
            "Администратор уже уведомлен, попробуйте позже."
        )
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
        f"📁 Файл: {config_file}\n"
        f"Всего активных запросов: {len(pending_requests)}"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Принять", callback_data=f"approve_{user.id}"),
            InlineKeyboardButton("❌ Отказать", callback_data=f"reject_{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_message,
            reply_markup=reply_markup
        )
        message = (
            "✅ Ваш запрос отправлен администратору на проверку.\n"
            "Ожидайте решения в течение нескольких минут."
        )
        if query:
            await query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        logger.info(f"Запрос от {user.id} отправлен администратору")
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения администратору: {e}")
        message = "⚠️ Произошла ошибка при обработке вашего запроса. Попробуйте позже."
        if query:
            await query.edit_message_text(message)
        else:
            await update.message.reply_text(message)

# ... (остальные функции остаются без изменений, как в предыдущей версии)

def main():
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("get_config", get_config))
    application.add_handler(CallbackQueryHandler(handle_button, pattern='^request_config$'))
    application.add_handler(CallbackQueryHandler(handle_admin_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Проверка начальных условий
    configs = check_configs()
    if not configs:
        logger.warning("На старте нет доступных конфигов!")
    
    # Запуск бота
    logger.info("Бот запускается...")
    application.run_polling()
    logger.info("Бот остановлен")

if __name__ == "__main__":
    main()