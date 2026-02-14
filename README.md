# SMM Assistant 

Telegram-бот для SMM-специалистов, который собирает активную аудиторию из комментариев с '+' и делает рассылку.

## Функции
- Сбор пользователей, оставивших '+' под постом
- Автоматическая рассылка сообщений
- Статистика доставки
- Защита от спама

## Технологии
- Python 3.10
- python-telegram-bot
- Telethon
- asyncio

## Установка
```bash
git clone https://github.com/твой-логин/smm_assistant.git
cd smm_assist
pip install -r requirements.txt
# Вставь свои API данные в smm_assist.py (строки 20-23)
python smm_assist.py
