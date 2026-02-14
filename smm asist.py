"""
Бот для сбора плюсиков в телеграм-каналах
"""

import logging
import asyncio
import re
from datetime import datetime
from typing import Dict, List, Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from telethon import TelegramClient
from telethon.errors import FloodWaitError

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
)
logger = logging.getLogger(__name__)

# Состояния для диалога
WAITING_FOR_POST, WAITING_FOR_MESSAGE = range(2)

# ===== ВСТАВЬ СВОИ ДАННЫЕ СЮДА =====
API_ID = 1234567  # Замени на свой API_ID (с my.telegram.org)
API_HASH = 'abcdef1234567890abcdef1234567890'  # Замени на свой API_HASH
BOT_TOKEN = '8481820454:AAE6WqHNN2VZd-oEYp5Aw-8Ck45UE2PtEgc'  # Твой токен от @BotFather
PHONE_NUMBER = '+79123456789'  # Твой номер телефона
# ====================================

# Клиент Telethon
telethon_client = None


async def get_telethon_client():
    """Ленивая инициализация Telethon клиента"""
    global telethon_client
    if telethon_client is None:
        telethon_client = TelegramClient('tg_plus_bot_session', API_ID, API_HASH)
        await telethon_client.start(phone=PHONE_NUMBER)
    return telethon_client


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /start"""
    user = update.effective_user
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я помогу собрать всех, кто поставил '+' под постом в канале.\n"
        "Потом можно будет сделать им рассылку.\n\n"
        "📌 Просто отправь /rassylka и перешли мне пост."
    )
    await update.message.reply_text(welcome_text)


async def rassylka(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинаем процесс рассылки"""
    await update.message.reply_text(
        "🔍 Ок, ищем комментарии с '+'\n\n"
        "📎 Перешли мне пост из канала (где люди писали + в комментах)\n\n"
        "❌ Если передумал - /cancel"
    )
    return WAITING_FOR_POST


async def handle_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем пересланный пост"""
    try:
        message = update.message
        
        if not message.forward_origin:
            await update.message.reply_text("❌ Это не пересланное сообщение. Нужно именно переслать пост.")
            return WAITING_FOR_POST
        
        if message.forward_origin.type != "channel":
            await update.message.reply_text("❌ Это не из канала. Перешли пост из канала.")
            return WAITING_FOR_POST
        
        origin = message.forward_origin
        chat_id = origin.chat.id
        message_id = origin.message_id
        chat_title = origin.chat.title
        
        context.user_data['post'] = {
            'chat_id': chat_id,
            'message_id': message_id,
            'chat_title': chat_title,
            'chat_username': origin.chat.username,
        }
        
        await update.message.reply_text(
            f"✅ Пост из канала \"{chat_title}\" получен\n"
            f"🔍 Начинаю сбор комментариев...\n"
            f"⏳ Это может занять несколько секунд"
        )
        
        plus_users = await find_plus_commentators(chat_id, message_id)
        
        if not plus_users:
            await update.message.reply_text(
                "😕 Никого с '+' не нашлось. Может, в другом посте?"
            )
            return ConversationHandler.END
        
        context.user_data['plus_users'] = plus_users
        context.user_data['found_count'] = len(plus_users)
        
        preview = f"✅ Нашёл {len(plus_users)} человек с '+'\n\n"
        
        for i, user in enumerate(plus_users[:5], 1):
            name = user.get('name', 'Без имени')
            username = f" (@{user['username']})" if user.get('username') else ""
            preview += f"{i}. {name}{username}\n"
        
        if len(plus_users) > 5:
            preview += f"...и ещё {len(plus_users) - 5}\n"
        
        preview += "\n📝 Теперь напиши текст для рассылки"
        
        await update.message.reply_text(preview)
        return WAITING_FOR_MESSAGE
        
    except Exception as e:
        logger.exception("Ошибка в handle_post")
        await update.message.reply_text(
            "❌ Что-то пошло не так. Попробуй ещё раз с /rassylka"
        )
        return ConversationHandler.END


async def find_plus_commentators(chat_id: int, message_id: int) -> List[Dict]:
    """Ищем комментарии с плюсиками"""
    users = []
    
    try:
        client = await get_telethon_client()
        channel = await client.get_entity(chat_id)
        
        async for comment in client.iter_messages(
            channel,
            reply_to=message_id,
            limit=500
        ):
            if not comment.sender_id or not comment.text:
                continue
            
            if '+' in comment.text or '➕' in comment.text:
                try:
                    sender = await client.get_entity(comment.sender_id)
                    
                    first = getattr(sender, 'first_name', '')
                    last = getattr(sender, 'last_name', '')
                    name = f"{first} {last}".strip()
                    
                    users.append({
                        'id': sender.id,
                        'name': name or "Пользователь",
                        'username': getattr(sender, 'username', None),
                        'comment': comment.text[:100],
                    })
                    
                except Exception as e:
                    logger.warning(f"Не смог получить юзера {comment.sender_id}: {e}")
                    continue
        
        unique_users = {u['id']: u for u in users}.values()
        return list(unique_users)
        
    except FloodWaitError as e:
        logger.error(f"Флуд контроль, ждём {e.seconds}с")
        await asyncio.sleep(e.seconds)
        return await find_plus_commentators(chat_id, message_id)
        
    except Exception as e:
        logger.exception("Ошибка в find_plus_commentators")
        return []


async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляем рассылку"""
    try:
        message_text = update.message.text
        users = context.user_data.get('plus_users', [])
        post_info = context.user_data.get('post', {})
        
        if not users:
            await update.message.reply_text("❌ Нет пользователей для рассылки")
            return ConversationHandler.END
        
        status_msg = await update.message.reply_text(
            f"📤 Начинаю рассылку {len(users)} пользователям...\n"
            f"⏳ Это может занять некоторое время"
        )
        
        success = 0
        failed = 0
        blocked = 0
        
        for i, user in enumerate(users, 1):
            try:
                await context.bot.send_message(
                    chat_id=user['id'],
                    text=message_text,
                    disable_notification=False
                )
                success += 1
                
                if i % 5 == 0:
                    await status_msg.edit_text(
                        f"📤 Прогресс: {i}/{len(users)}\n"
                        f"✅ Отправлено: {success}\n"
                        f"❌ Ошибок: {failed}"
                    )
                
                await asyncio.sleep(0.3)
                
            except Exception as e:
                failed += 1
                error_text = str(e).lower()
                
                if 'blocked' in error_text or 'forbidden' in error_text:
                    blocked += 1
                
                logger.debug(f"Ошибка отправки юзеру {user['id']}: {e}")
        
        report = (
            f"📊 Рассылка завершена!\n\n"
            f"👥 Всего в списке: {len(users)}\n"
            f"✅ Успешно: {success}\n"
            f"❌ Неудачно: {failed}\n"
            f"🚫 Заблокировали бота: {blocked}\n\n"
        )
        
        if failed > 0:
            report += (
                "💡 Советы:\n"
                "• Проверь, что бот не заблокирован\n"
                "• Убедись, что пользователи могут писать боту\n"
                "• Возможно, кто-то удалил аккаунт"
            )
        
        await status_msg.edit_text(report)
        
        try:
            with open('broadcast_stats.txt', 'a', encoding='utf-8') as f:
                f.write(
                    f"{datetime.now()}: {context.user_data.get('found_count', 0)} найдено, "
                    f"{success} ок, {failed} нет, {blocked} заблокировано\n"
                )
        except:
            pass
        
    except Exception as e:
        logger.exception("Ошибка в handle_broadcast")
        await update.message.reply_text("❌ Ошибка при рассылке")
    
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text("🚫 Отменил. Если что - /rassylka")
    return ConversationHandler.END


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ Произошла ошибка. Разработчик уже знает о проблеме."
            )
    except:
        pass


def main():
    """Запуск бота"""
    print("🟢 Запускаю бота...")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('rassylka', rassylka)],
        states={
            WAITING_FOR_POST: [
                MessageHandler(filters.FORWARDED & ~filters.COMMAND, handle_post)
            ],
            WAITING_FOR_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)
    
    print("✅ Бот готов к работе. Нажми Ctrl+C для остановки")
    app.run_polling()


if __name__ == '__main__':
    main()