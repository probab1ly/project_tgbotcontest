from aiogram import Bot, Dispatcher
from handlers import router
from database import init_db, periodic_delete
import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        raise ValueError("BOT_TOKEN не найден в переменных окружения! Установите его в .env файле или через export BOT_TOKEN=your_token")
    bot = Bot(token=bot_token)
    
    dp = Dispatcher()
    dp.include_router(router)
    asyncio.create_task(periodic_delete())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
