from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload
from sqlalchemy.future import select
from sqlalchemy import func, and_, desc, delete
from models import Base, User, Profile, Rating
from datetime import datetime
import logging
logger = logging.getLogger(__name__)
engine = create_async_engine('sqlite+aiosqlite:///bot.db', echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_user(telegram_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            logger.info(f"Пользователь не найден: telegram_id={telegram_id}")
        return user

async def get_user_profile(telegram_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Profile).options(selectinload(Profile.received_ratings)).join(User, Profile.user_id == User.id).where(User.telegram_id == telegram_id).order_by(desc(Profile.created_at)).limit(1)
        )
        profile = result.scalar_one_or_none()
        if profile:
            logger.info(f"Найден профиль пользователя: telegram_id={telegram_id}")
            return profile
        else:
            logger.info(f"Профиль не найден: telegram_id={telegram_id}")
            return None
async def create_user(telegram_id: int, username: str):
    async with async_session() as session:
        existing_user = await get_user(telegram_id)
        if existing_user:
            logger.info(f"Пользователь уже существует: telegram_id={telegram_id}")
            return existing_user
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.commit()
        logger.info(f"Создан новый пользователь: id={user.id}, telegram_id={telegram_id}")
        return user

async def create_profile(user_id: int, description: str, video_id: str):
    async with async_session() as session:
        profile = Profile(user_id=user_id, description=description, video_id=video_id)
        session.add(profile)
        await session.commit()
        return profile

async def get_random_profile(ex_user_id: int):
    async with async_session() as session:
        query = select(Profile).where(Profile.is_verified == True)
        if ex_user_id:
            query = query.where(Profile.user_id != ex_user_id)
        result = await session.execute(query.order_by(func.random()).limit(1))
        return result.scalar_one_or_none()

async def create_rating(rater_id: int, profile_id: int, score: float, comment: str):
    async with async_session() as session:
        rating = Rating(rater_id=rater_id, profile_id=profile_id, score=score, comment=comment)
        session.add(rating)
        await session.commit()
        return rating

async def delete_ex_profiles():
    async with async_session() as session:
        result = await session.execute(
            select(Profile).where(Profile.delete_at <= datetime.utcnow)
        )
        ex_profiles = result.scalars.all()
        for profile in ex_profiles:
            await session.execute(
                select(Rating).where(Rating.profile_id == profile_id).delete()
            )
            await session.delete(profile)
        await session.commit()
        return ex_profiles

async def get_profile_info(profile_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Profile).where(Profile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            days = (profile.delete_at - datetime.utcnow()).days
            return profile.delete_at, days
        else:
            return None, 0
async def edit_profile(profile_id: int, description: str, video_id: str):
    async with async_session() as session:
        result = await session.execute(
            select(Profile).where(Profile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            if description is not None:
                profile.description = description
            if video_id is not None:
                profile.video_id = video_id
            profile.is_verified = False
            await session.commit()
            return profile
        return None
async def delete_profile(profile_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Profile).where(Profile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            await session.execute(
                delete(Rating).where(Rating.profile_id == profile_id)
            )
            await session.delete(profile)
            await session.commit()
            return True
        return False
async def get_user_profile_with_rating(telegram_id: int):
    async with async_session() as session:
        user_result = await session.execute(
            select(User).options(selectinload(User.profile).selectinload(Profile.received_ratings)).where(User.telegram_id == telegram_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            logger.info(f"Пользователь не найден: telegram_id={telegram_id}")
            return None
        return user.profile

async def verify_profile(profile_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Profile).options(selectinload(Profile.user)).where(Profile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            profile.is_varified = True
            await session.commit()
            return profile
        return None
async def reject_profile(profile_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Profile).options(selectinload(Profile.user)).where(Profile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            session.delete(profile)
            await session.commit()
            return True
        return False

async def get_need_profiles():
    async with async_session() as session:
        result = await session.execute(
            select(Profile).options(selectinload(Profile.user)).where(Profile.is_verified == False)
        )
        return result.scalars().all()

async def get_profile_for_moderation(profile_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Profile).options(selectinload(Profile.user)).where(Profile.id == profile_id)
        )
        return result.scalar_one_or_none()























