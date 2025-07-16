import asyncio
import logging
from aiogram import Bot, Dispatcher
# from sqlitestorage.storage import SQLiteStorage
from handlers import router
from database import init_db
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    bot = Bot(token='')
    dp = Dispatcher() #storage=SQLiteStorage(path='states.db')
    dp.include_router(router)
    await dp.start_polling(bot)
if __name__ == '__main__':
    asyncio.run(main())
