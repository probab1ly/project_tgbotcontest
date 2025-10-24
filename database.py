from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload
from sqlalchemy.future import select
from sqlalchemy import func, and_, desc, delete, text
from models import Base, User, Profile, Rating, ProfileView
from datetime import datetime
import logging
import asyncio
import os

POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'tgevaluation')

# URL для подключения к PostgreSQL (или SQLite для тестирования)
USE_POSTGRESQL = os.getenv('USE_POSTGRESQL', 'false').lower() == 'true'

if USE_POSTGRESQL:
    DATABASE_URL = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
else:
    DATABASE_URL = "sqlite+aiosqlite:///bot.db"

logger = logging.getLogger(__name__)

engine = None
async_session = None

async def init_db():
    """Инициализация базы данных PostgreSQL"""
    global engine, async_session
    
    try:
        # Создаем движок для PostgreSQL
        engine = create_async_engine(DATABASE_URL, echo=True)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        # Создаем базу данных с правильной схемой
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("PostgreSQL база данных инициализирована с правильной схемой")
            
    except Exception as e:
        logger.error(f"Ошибка при инициализации PostgreSQL базы данных: {e}")
        raise

# Инициализируем переменные, если они еще не созданы
if engine is None:
    engine = create_async_engine(DATABASE_URL, echo=True)
if async_session is None:
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_user(telegram_id: int):
    async with async_session() as session:
        print(f"DEBUG: get_user вызвана для telegram_id {telegram_id}")
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            print(f"DEBUG: Пользователь с telegram_id {telegram_id} не найден в базе")
        else:
            print(f"DEBUG: Найден пользователь user_id={user.id}, telegram_id={telegram_id}")
        return user

async def get_user_profile(telegram_id: int):
    async with async_session() as session:
        # Сначала ищем одобренную анкету
        result = await session.execute(
            select(Profile)
            .options(selectinload(Profile.user), selectinload(Profile.received_ratings))
            .join(User, Profile.user_id == User.id)
            .where(User.telegram_id == telegram_id, Profile.is_verified == True)
            .order_by(Profile.created_at.desc())
        )
        profile = result.scalars().first()
        if profile:
            return profile
        # Если одобренной нет — возвращаем последнюю любую анкету
        result = await session.execute(
            select(Profile)
            .options(selectinload(Profile.user), selectinload(Profile.received_ratings))
            .join(User, Profile.user_id == User.id)
            .where(User.telegram_id == telegram_id)
            .order_by(Profile.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def create_user(telegram_id: int, username: str | None):
    async with async_session() as session:
        try:
            existing_user_result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            existing_user = existing_user_result.scalar_one_or_none()
            if existing_user:
                logger.info(f"Пользователь уже существует: telegram_id={telegram_id}")
                return existing_user
            
            # Убеждаемся, что username может быть None
            user = User(telegram_id=telegram_id, username=username)
            session.add(user)
            await session.commit()
            logger.info(f"Создан новый пользователь: id={user.id}, telegram_id={telegram_id}, username={username}")
            return user
        except Exception as e:
            logger.error(f"Ошибка при создании пользователя {telegram_id}: {e}")
            await session.rollback()
            raise

async def create_profile(user_id: int, description: str, category: str, video_id: str | None, photo_id: str | None):
    async with async_session() as session:
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            logger.error(f"Пользователь не найден: user_id={user_id}")
            return None
        
        profile = Profile(user_id=user_id, description=description, category=category, video_id=video_id, photo_id=photo_id, is_verified=False)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        logger.info(f"Создана новая анкета: id={profile.id}, user_id={user_id}")
        return profile

async def get_random_profile(ex_user_id: int):
    async with async_session() as session:
        # Получаем пользователя
        user_result = await session.execute(
            select(User).where(User.telegram_id == ex_user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            print(f"DEBUG: Пользователь не найден: telegram_id={ex_user_id}")
            return None
        
        # Получаем ID просмотренных анкет
        viewed_profiles_result = await session.execute(
            select(ProfileView.profile_id).where(ProfileView.viewer_id == user.id)
        )
        viewed_profile_ids = [row[0] for row in viewed_profiles_result.fetchall()]
        
        # Отладочная информация
        all_profiles_result = await session.execute(
            select(Profile).where(Profile.is_verified == True)
        )
        all_profiles = all_profiles_result.scalars().all()
        print(f"DEBUG: Всего одобренных анкет в базе: {len(all_profiles)}")
        for p in all_profiles:
            print(f"DEBUG: Анкета profile_id={p.id}, user_id={p.user_id}, is_verified={p.is_verified}")
        
        # Формируем условия для выборки
        conditions = [
            Profile.is_verified == True,
            Profile.user_id != user.id
        ]
        if viewed_profile_ids:
            conditions.append(~Profile.id.in_(viewed_profile_ids))
        
        query = select(Profile).options(
            selectinload(Profile.user), 
            selectinload(Profile.received_ratings)
        ).where(
            and_(*conditions)
        ).order_by(func.random()).limit(1)
        
        result = await session.execute(query)
        profile = result.scalars().first()
        
        if profile:
            # Принудительно загружаем связанные данные в рамках текущей сессии
            await session.refresh(profile, attribute_names=['user', 'received_ratings'])
            print(f"DEBUG: Возвращена анкета для пользователя {ex_user_id}: profile_id={profile.id}, user_id={profile.user_id}")
        else:
            print(f"DEBUG: Нет доступных анкет для пользователя {ex_user_id}")
            print(f"DEBUG: Причины: user_id={user.id}, просмотренные={viewed_profile_ids}")
        
        return profile

async def get_random_profile_by_category(ex_user_id: int, category: str = None):
    """Получить случайную анкету для оценивания по категории"""
    async with async_session() as session:
        # Сначала получаем внутренний ID пользователя по telegram_id
        user_result = await session.execute(
            select(User).where(User.telegram_id == ex_user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            return None
        
        conditions = [
            Profile.is_verified == True,
            Profile.user_id != user.id  # Используем внутренний ID пользователя
        ]
        
        if category and category != "Все":
            conditions.append(Profile.category == category)
        
        # Исключаем уже просмотренные анкеты
        viewed_profiles = await session.execute(
            select(ProfileView.profile_id).where(ProfileView.viewer_id == user.id)
        )
        viewed_profile_ids = [row[0] for row in viewed_profiles.fetchall()]
        if viewed_profile_ids:
            conditions.append(Profile.id.notin_(viewed_profile_ids))
        
        query = select(Profile).options(
            selectinload(Profile.user), 
            selectinload(Profile.received_ratings)
        ).where(
            and_(*conditions)
        ).order_by(func.random()).limit(1)
        
        result = await session.execute(query)
        profile = result.scalars().first()
        
        if profile:
            # Принудительно загружаем связанные данные в рамках текущей сессии
            await session.refresh(profile, attribute_names=['user', 'received_ratings'])
            print(f"DEBUG: Возвращена анкета категории {category} для пользователя {ex_user_id}: profile_id={profile.id}, user_id={profile.user_id}")
        else:
            print(f"DEBUG: Нет доступных анкет категории {category} для пользователя {ex_user_id}")
        
        return profile

async def get_available_categories():
    """Получить список всех доступных категорий"""
    async with async_session() as session:
        result = await session.execute(
            select(Profile.category).where(Profile.is_verified == True).distinct()
        )
        categories = [row[0] for row in result.fetchall()]
        return ["Все"] + sorted(categories)

async def mark_profile_as_viewed(viewer_telegram_id: int, profile_id: int):
    async with async_session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == viewer_telegram_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            logger.error(f"Пользователь не найден: telegram_id={viewer_telegram_id}")
            return False
        # Используем user.id для поиска и создания ProfileView
        existing_view_result = await session.execute(
            select(ProfileView).where(
                and_(
                    ProfileView.viewer_id == user.id,
                    ProfileView.profile_id == profile_id
                )
            )
        )
        existing_view = existing_view_result.scalar_one_or_none()
        if existing_view:
            existing_view.viewed_at = datetime.utcnow()
            logger.info(f"Обновлен просмотр: пользователь {viewer_telegram_id}, анкета {profile_id}")
        else:
            profile_view = ProfileView(viewer_id=user.id, profile_id=profile_id)
            session.add(profile_view)
            logger.info(f"Создан новый просмотр: пользователь {viewer_telegram_id}, анкета {profile_id}")
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
            select(Profile).where(Profile.delete_at <= datetime.utcnow())
        )
        ex_profiles = result.scalars().all()
        for profile in ex_profiles:
            await session.execute(
                delete(Rating).where(Rating.profile_id == profile.id)
            )
            await session.execute(
                delete(ProfileView).where(ProfileView.profile_id == profile.id)
            )
            await session.delete(profile)
        await session.commit()
        return ex_profiles

async def get_profile_info(profile_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Profile).where(Profile.id == profile_id)
        )
        profile = result.scalars().first()
        if profile and profile.delete_at:
            days = (profile.delete_at - datetime.utcnow()).days
            return profile.delete_at, days
        else:
            return None, False
async def edit_profile(profile_id: int, description: str, category: str, video_id: str | None, photo_id: str | None): 
    async with async_session() as session:
        result = await session.execute(
            select(Profile).where(Profile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            # Удаляем все старые оценки и просмотры
            await session.execute(
                delete(Rating).where(Rating.profile_id == profile_id)
            )
            await session.execute(
                delete(ProfileView).where(ProfileView.profile_id == profile_id)
            )
            
            # Обновляем существующую анкету
            profile.description = description or profile.description
            profile.category = category or profile.category
            profile.video_id = video_id
            profile.photo_id = photo_id
            profile.is_verified = False  # Сбрасываем статус верификации
            profile.created_at = datetime.now()  # Обновляем время создания
            
            await session.commit()
            await session.refresh(profile)
            return profile
        return None
    
async def delete_profile(profile_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Profile).options(
                selectinload(Profile.user),
                selectinload(Profile.received_ratings)
            ).where(Profile.id == profile_id)
        )
        profile = result.scalars().first()
        if profile:
            # Принудительно загружаем связанные данные в рамках текущей сессии
            await session.refresh(profile, attribute_names=['user', 'received_ratings'])
            
            # Удаляем все связанные записи
            await session.execute(
                delete(Rating).where(Rating.profile_id == profile_id)
            )
            await session.execute(
                delete(ProfileView).where(ProfileView.profile_id == profile_id)
            )
            # Также удаляем записи, где пользователь является просматривающим
            await session.execute(
                delete(ProfileView).where(ProfileView.viewer_id == profile.user_id)
            )
            
            # Удаляем все оценки, которые пользователь поставил другим анкетам
            await session.execute(
                delete(Rating).where(Rating.rater_id == profile.user_id)
            )
            
            await session.delete(profile)
            # Не удаляем пользователя, чтобы избежать проблем с foreign key constraints
            # await session.delete(profile.user)
            await session.commit()
            return True
        return False
    
async def get_user_profile_with_rating(telegram_id: int):
    async with async_session() as session:
        user_result = await session.execute(
            select(User).options(
                selectinload(User.profiles).selectinload(Profile.received_ratings)
            ).where(User.telegram_id == telegram_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            logger.info(f"Пользователь не найден: telegram_id={telegram_id}")
            return None
        
        if user.profiles:
            # Возвращаем последний профиль (самый новый)
            latest_profile = max(user.profiles, key=lambda p: p.created_at)
            # Принудительно загружаем связанные данные в рамках текущей сессии
            await session.refresh(latest_profile, attribute_names=['received_ratings'])
            return latest_profile
        
        return None

async def verify_profile(profile_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Profile).options(
                selectinload(Profile.user),
                selectinload(Profile.received_ratings)
            ).where(Profile.id == profile_id)
        )
        profile = result.scalars().first()
        if profile:
            # Принудительно загружаем связанные данные в рамках текущей сессии
            await session.refresh(profile, attribute_names=['user', 'received_ratings'])
            user_telegram_id = profile.user.telegram_id
            user_username = profile.user.username
            profile.is_verified = True
            await session.commit()
            return {'id': profile.id, 'telegram_id': user_telegram_id, 'username': user_username}
        return None

async def reject_profile(profile_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Profile).where(Profile.id == profile_id)
        )
        profile = result.scalars().first()
        if profile and not profile.is_verified:
            await session.delete(profile)
            await session.commit()
            return True
        return False

async def get_need_profiles():
    async with async_session() as session:
        result = await session.execute(
            select(Profile).options(
                selectinload(Profile.user),
                selectinload(Profile.received_ratings)
            ).where(Profile.is_verified == False)
        )
        profiles = result.scalars().all()
        # Принудительно загружаем связанные данные для всех профилей
        for profile in profiles:
            await session.refresh(profile, attribute_names=['user', 'received_ratings'])
        return profiles

async def get_profile_for_moderation(profile_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Profile).options(
                selectinload(Profile.user),
                selectinload(Profile.received_ratings)
            ).where(Profile.id == profile_id)
        )
        profile = result.scalars().first()
        if profile:
            # Принудительно загружаем связанные данные в рамках текущей сессии
            await session.refresh(profile, attribute_names=['user', 'received_ratings'])
        return profile

async def get_unviewed_profiles_count(viewer_telegram_id: int):
    async with async_session() as session:
        # Получаем ID пользователя
        user_result = await session.execute(
            select(User).where(User.telegram_id == viewer_telegram_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            return False

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

async def get_winner_profile():
    async with async_session() as session:
        result = await session.execute(
            select(Profile)
            .options(selectinload(Profile.user), selectinload(Profile.received_ratings))
            .where(Profile.is_verified == True)
        )
        profiles = result.scalars().all()
        if not profiles:
            return None

        # Сначала пробуем строгие правила (>=5 оценок и разница в 0.3)
        winner = None
        max_avg = -1.0
        max_count = -1
        for profile in profiles:
            ratings = profile.received_ratings or []
            count = len(ratings)
            if count < 5:
                continue
            avg = sum(r.score for r in ratings) / count if ratings else 0
            if avg > max_avg + 0.3:
                winner = profile
                max_avg = avg
                max_count = count
            elif abs(avg - max_avg) <= 0.3:
                if count > max_count:
                    winner = profile
                    max_avg = avg
                    max_count = count

        if winner:
            return winner

        # Fallback: если нет профилей с >=5 оценками, выбираем лучшего из тех, у кого >=1
        fallback_winner = None
        fallback_max_avg = -1.0
        fallback_max_count = -1
        for profile in profiles:
            ratings = profile.received_ratings or []
            count = len(ratings)
            if count == 0:
                continue
            avg = sum(r.score for r in ratings) / count
            if avg > fallback_max_avg:
                fallback_winner = profile
                fallback_max_avg = avg
                fallback_max_count = count
            elif abs(avg - fallback_max_avg) < 1e-9:
                if count > fallback_max_count:
                    fallback_winner = profile
                    fallback_max_avg = avg
                    fallback_max_count = count
        return fallback_winner

async def periodic_delete():
    while True:
        await delete_ex_profiles()
        await asyncio.sleep(86400)

















