import asyncio
import logging
from aiogram import Bot, Dispatcher
from handlers import router
from database import init_db

async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    bot = Bot(token='')
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
