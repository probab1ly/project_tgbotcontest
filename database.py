from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload
from sqlalchemy.future import select
from sqlalchemy import func, and_, desc, delete
from models import Base, User, Profile, Rating, ProfileView
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
        existing_user_result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        existing_user = existing_user_result.scalar_one_or_none()
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
        existing_profile_result = await session.execute(
            select(Profile).where(Profile.id == user_id)
        )
        existing_profile = existing_profile_result.scalar_one_or_none()
        if existing_profile:
            logger.info(f"Пользователь уже существует: telegram_id={telegram_id}")
            return existing_profile
        profile = Profile(user_id=user_id, description=description, video_id=video_id)
        session.add(profile)
        await session.commit()
        return profile

async def get_random_profile(ex_user_id: int):
    async with async_session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == ex_user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user: #если нет user, значит нет анкеты
            query = select(Profile).options(selectinload(Profile.user), selectinload(Profile.received_ratings)).where(Profile.is_verified == True)
            result = await session.execute(query.order_by(func.random()).limit(1))
            return result.scalar_one_or_none()
        viewed_profiles_result = await session.execute(
            select(ProfileView.profile_id).where(ProfileView.viewer_id == user.id)
        )
        viewed_profile_ids = [row[0] for row in viewed_profiles_result.fetchall()]
        query = select(Profile).options(selectinload(Profile.user), selectinload(Profile.received_ratings)).where(
            and_(
                Profile.is_verified == True,
                Profile.user_id != user.id,
                ~Profile.id.in_(viewed_profile_ids) if viewed_profile_ids else True
            )
        ).order_by(func.random()).limit(1)
        result = await session.execute(query)
        return result.scalar_one_or_none()

async def mark_profile_as_viewed(viewer_telegram_id: int, profile_id: int):
    async with async_session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == viewer_telegram_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            logger.error(f"Пользователь не найден: telegram_id={viewer_telegram_id}")
            return False
        # Проверяем, не просматривал ли пользователь эту анкету уже
        existing_view_result = await session.execute(
            select(ProfileView).where(
                and_(
                    ProfileView.viewer_id == viewer_telegram_id,
                    ProfileView.profile_id == profile_id
                )
            )
        )
        existing_view = existing_view_result.scalar_one_or_none()
        if existing_view:
            existing_view.viewed_at = datetime.utcnow()
        else:
            profile_view = ProfileView(viewer_id=user.id, profile_id=profile_id)
            session.add(profile_view)
        await session.commit()
        return True
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
            user_telegram_id = profile.user.telegram_id
            user_username = profile.user.username
            profile.is_verified = True
            await session.commit()
            return {'id': profile.id, 'telegram_id': user_telegram_id, 'username': user_username}
        return None
async def reject_profile(profile_id: int):
    async with async_session() as session:
        result = await session.execute(
            delete(Profile).options(selectinload(Profile.user)).where(Profile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            user_telegram_id = profile.user.telegram_id
            user_username = profile.user.username
            await session.execute(
                delete(Rating).where(Rating.profile_id == profile_id)
            )
            await session.delete(profile)
            await session.commit()
            return {'id': profile.id, 'telegram_id': user_telegram_id, 'username': user_username}
        return None

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


async def get_unviewed_profiles_count(viewer_telegram_id: int):
    """Возвращает количество непросмотренных анкет для пользователя"""
    async with async_session() as session:
        # Получаем ID пользователя
        user_result = await session.execute(
            select(User).where(User.telegram_id == viewer_telegram_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            return 0

        # Получаем ID просмотренных анкет
        viewed_profiles_result = await session.execute(
            select(ProfileView.profile_id).where(ProfileView.viewer_id == user.id)
        )
        viewed_profile_ids = [row[0] for row in viewed_profiles_result.fetchall()]

        # Подсчитываем непросмотренные анкеты
        query = select(func.count(Profile.id)).where(
            and_(
                Profile.is_verified == True,
                Profile.user_id != user.id,
                ~Profile.id.in_(viewed_profile_ids) if viewed_profile_ids else True
            )
        )

        result = await session.execute(query)
        return result.scalar()






















