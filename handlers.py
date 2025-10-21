from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
import logging
from datetime import datetime
from keyboards import (
    get_main_keyboard, get_rating_keyboard, get_profile_verification_keyboard,
    get_profile_edit, get_moderation_keyboard, get_moderation_profile
)
from database import (
    get_user, create_user, create_profile, get_random_profile,
    create_rating, delete_ex_profiles, get_profile_info, get_user_profile,
    edit_profile, delete_profile, get_user_profile_with_rating,
    verify_profile, reject_profile, get_need_profiles, get_profile_for_moderation,
    verify_profile, reject_profile, mark_profile_as_viewed,
    get_unviewed_profiles_count, get_winner_profile
)
from typing import Callable, Awaitable
import time

# # Глобальный кэш: (user_id, media_group_id) -> timestamp
# warned_media_groups_cache = {}

# def cleanup_warned_cache(ttl=60):
#     now = time.time()
#     to_delete = [key for key, t in warned_media_groups_cache.items() if now - t > ttl]
#     for key in to_delete:
#         del warned_media_groups_cache[key]

# async def warn_once_for_media_group(message: Message, warn_text: str, ttl=60) -> bool:
#     if message.media_group_id is not None:
#         cleanup_warned_cache(ttl)
#         key = (message.from_user.id, message.media_group_id)
#         if key in warned_media_groups_cache:
#             return True
#         await message.answer(warn_text)
#         warned_media_groups_cache[key] = time.time()
#         return True
#     return False

logger = logging.getLogger(__name__)
router = Router()

def get_display_username(username: str | None) -> str:
    """Безопасно получает username для отображения"""
    if username:
        return f"@{username}"
    return "Пользователь без username"

# Telegram ограничения: caption до ~1024 символов, текст до ~4096
CAPTION_LIMIT = 1000
TEXT_LIMIT = 4000

def truncate_text(text: str, max_length: int) -> str:
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."

def build_profile_text_for_caption(lines: list[str], for_caption: bool = True) -> str:
    # Склеиваем строки и обрезаем под лимит
    text = "".join(lines)
    limit = CAPTION_LIMIT if for_caption else TEXT_LIMIT
    return truncate_text(text, limit)

class ProfileStates(StatesGroup):
    waiting_for_description = State()
    waiting_for_category = State()
    waiting_for_video = State()
    waiting_for_edit_description = State()
    waiting_for_edit_category = State()
    waiting_for_edit_video = State()

class RatingStates(StatesGroup):
    waiting_for_rating = State()
    waiting_for_comment = State()

class ModerationStates(StatesGroup):
    view_profiles = State()

class ProfileViewStates(StatesGroup):
    view_profiles = State()

async def show_profile_for_moderation(message: Message, profile_id):
    profile = await get_profile_for_moderation(profile_id)
    if not profile or not profile.user:
        await message.answer("⚠️ Ошибка: не удалось загрузить данные анкеты.")
        return
    
    profile_text = (
        f"📝 Анкета на модерацию:\n\n"
        f"👤 Пользователь: {get_display_username(profile.user.username)}\n"
        f"📝 Описание: {profile.description}\n"
        f"✨ Категория: {profile.category}\n"
        f"📅 Создана: {profile.created_at.strftime('%d.%m.%Y %H:%M') if profile.created_at else 'неизвестно'}"
    )
    if profile.video_id:
        await message.answer_video(
            video=profile.video_id,
            caption=profile_text,
            reply_markup=get_moderation_profile(profile.id)
        )
    elif profile.photo_id:
        await message.answer_photo(
            photo=profile.photo_id,
            caption=profile_text,
            reply_markup=get_moderation_profile(profile.id)
        )
    else:
        await message.answer(
            profile_text,
            reply_markup=get_moderation_profile(profile.id)
        )

async def next_profile(callback: CallbackQuery, state: FSMContext):#moderation
    if callback.from_user.id != 1653541807:
        await callback.answer("⚠️ У вас нет прав для этого действия")
        return
    data = await state.get_data()
    if not data:
        await callback.answer("Ошибка: данные не найдены")
        return

    profiles = data['profiles']
    current_index = data['current_index']
    if current_index >= len(profiles)-1:
        await callback.answer("❗️ Это последняя анкета")
        await state.clear()
        await callback.message.answer(
            "👨‍💼 Панель модерации\n\n"
            "Все анкеты обработаны. Выберите действие:",
            reply_markup=get_moderation_keyboard()
        )
        return
    current_index += 1
    await state.update_data(current_index=current_index)
    profile_id = profiles[current_index]
    await callback.message.delete()
    await show_profile_for_moderation(callback.message, profile_id)

async def show_next_profile(message: Message, state: FSMContext, user_id: int = None):#clients
    # Определяем ID пользователя (переданный или из сообщения)
    telegram_id = user_id if user_id is not None else message.from_user.id
    is_admin = telegram_id == 1653541807
    
    # Отладочная информация
    print(f"DEBUG: show_next_profile вызвана для пользователя {telegram_id}")
    
    profile = await get_random_profile(telegram_id)
    if not profile:
        print(f"DEBUG: get_random_profile вернул None для пользователя {telegram_id}")
        await message.answer(
            "😔 К сожалению, больше нет доступных анкет для оценки.\n"
            "Попробуйте позже!",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )
        await state.clear()
        return
    if not profile.user:
        print(f"DEBUG: profile.user равен None для profile_id {profile.id}")
        await message.answer(
            "⚠️ Ошибка: не удалось загрузить данные пользователя.",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )
        await state.clear()
        return

    print(f"DEBUG: Найдена анкета profile_id={profile.id}, user_id={profile.user_id}, username={get_display_username(profile.user.username)}")

    await state.set_state(ProfileViewStates.view_profiles)
    await state.update_data(current_profile_id=profile.id)
    
    # Безопасно обрабатываем рейтинги
    ratings = profile.received_ratings
    if not ratings:
        ratings = []
    elif not isinstance(ratings, list):
        ratings = [ratings]
    avg_rating = round(sum(r.score for r in ratings) / len(ratings), 2) if ratings else 0
    
    profile_text = build_profile_text_for_caption([
        f"👤 Анкета пользователя {get_display_username(profile.user.username)}\n\n",
        f"📝 Описание: {profile.description}\n",
        f"✨ Категория: {profile.category}\n",
        f"⭐️ Средняя оценка: {avg_rating}\n",
        f"📊 Количество оценок: {len(ratings)}"
    ], for_caption=True)
    if profile.video_id:
        await message.answer_video(
            video=profile.video_id,
            caption=profile_text,
            reply_markup=get_rating_keyboard()
        )
    elif profile.photo_id:
        await message.answer_photo(
            photo=profile.photo_id,
            caption=profile_text,
            reply_markup=get_rating_keyboard()
        )
    else:
        await message.answer(
            profile_text,
            reply_markup=get_rating_keyboard()
        )

@router.message(Command('start'))
async def start(message: Message):
    if message.from_user.id == 1653541807:
        is_admin=True
    else:
        is_admin=False
    user = await get_user(message.from_user.id)
    if not user: # Новый пользователь без анкеты
        user = await create_user(message.from_user.id, message.from_user.username)
    welcome = (
        "Добро пожаловать в бот анкет! 🎉\n"
        "Вы можете создать свою анкету или оценивать анкеты других пользователей.\n"
        "В анкетах мы можете дать советы пользователям по одной из предложенных тематик, а также самим найти советы по интересующим вас вопросам"
    )
    await message.answer(welcome, reply_markup=get_main_keyboard(is_admin=is_admin))

@router.message(F.text == '📝 Создать анкету')
async def create_profile_start(message: Message, state: FSMContext):
    if message.from_user.id == 1653541807:
        is_admin=True
    else:
        is_admin=False

    existing_profile = await get_user_profile(message.from_user.id)
    if existing_profile:
        await message.answer(
            "⚠️ У вас уже есть активная анкета!\n\n"
            "Вы можете:\n"
            "• Посмотреть свою анкету (кнопка '👤 Моя анкета')\n"
            "• Отредактировать анкету\n"
            "• Удалить текущую анкету и создать новую",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )
    else:
        await state.set_state(ProfileStates.waiting_for_category)
        await message.answer(
            "Выберите категорию вашего контента и отправьте её сообщением:\n"
            "🎮 Игры\n"
            "💻 Программирование\n"
            "🍲 Кулинария\n"
            "🖼 Искусство\n"
            "✨ Жизнь\n"
            "💼 Бизнес"
        )

@router.message(ProfileStates.waiting_for_description)
async def process_description(message: Message, state: FSMContext):
    if not message.text or message.content_type != 'text':
        await message.answer("⚠️ Пожалуйста, отправьте текстовое описание для вашей анкеты (не фото, не видео, не файл). Попробуйте ещё раз.")
        return
    await state.update_data(description=message.text)
    await state.set_state(ProfileStates.waiting_for_video)
    await message.answer("📷 Хорошо, теперь отправьте видео или фото для вашей анкеты (или напишите 'пропустить', если нет медиафайлов)")

@router.message(ProfileStates.waiting_for_category)
async def process_category(message: Message, state: FSMContext):
    if not message.text or message.text.lower() not in ['игры', 'программирование', 'кулинария', 'искусство', 'бизнес', 'жизнь']:
        await message.answer("⚠️ Пожалуйста, отправьте корректную категорию для вашей анкеты")
        return
    await state.update_data(category=message.text)
    await state.set_state(ProfileStates.waiting_for_description)
    await message.answer("✍️ Отлично! Теперь отправьте текстовое описание вашей анкеты")

@router.message(ProfileStates.waiting_for_video, F.video)
async def process_video(message: Message, state: FSMContext, bot: Bot):
    if message.media_group_id is not None:
        await message.answer("⚠️ Пожалуйста, отправьте только одно видео для анкеты")
        return
    if message.from_user.id == 1653541807:
        is_admin=True
    else:
        is_admin=False
    data = await state.get_data()
    if not data or 'description' not in data:
        logger.error('Отсутствуют данные описания в состоянии')
        await message.answer('⚠️ Произошла ошибка. Пожалуйста, создайте анкету заново')
        await state.clear()
        return

    user = await get_user(message.from_user.id)
    if not user:
        user = await create_user(message.from_user.id, message.from_user.username)
    
    video = message.video
    if not video:
        logger.error("Объект видео не найден в сообщении")
        await message.answer("⚠️ Не удалось обработать видео. Пожалуйста, попробуйте отправить фото")
        return

    if video.file_size > 50*1024*1024 or video.duration > 240:
        await message.answer(
            "⚠️ Видео слишком большое или длинное. Максимальный размер: 50 МБ и длительность 4 минуты\n"
            "Пожалуйста, отправьте видео повторно"
        )
        return

    video_id = video.file_id
    logger.info(f"Получен file_id видео: {video_id}, тип: {type(video_id)}")
    # if hasattr(video, 'thumbnail') and video.thumbnail:
    #     photo_id = video.thumbnail.file_id
    if not video_id:
        logger.error("Не удалось получить file_id из видео")
        await message.answer(
            "⚠️ Не удалось обработать видео. Пожалуйста, попробуйте отправить другое видео"
        )
        return

    profile = await create_profile(
        user_id=user.id,
        description=data['description'],
        category=data['category'],
        video_id=video_id,
        photo_id=None
    )
    if profile:
        delete_at, days = await get_profile_info(profile.id)
        if delete_at:
            date_str = delete_at.strftime('%d.%m.%Y %H:%M')
        else:
            date_str = 'неизвестно'
        await state.update_data(warned_media_groups=[])
        await state.clear()

        await message.answer(
            "Ваша анкета успешно создана и отправлена на модерацию! "
            f"После проверки она появится в ленте для оценки.\n\n"
            f"⚠️ Анкета будет автоматически удалена через {days} дней",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )

        admin_message = (
            f"📝 Новая анкета на модерацию:\n\n"
            f"👤 Пользователь: {get_display_username(message.from_user.username)}\n"
            f"📝 Описание: {data['description']}\n"
            f"✨ Категория: {profile.category}\n"
            f"📅 Создана: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        await bot.send_video(chat_id='1653541807',video=video_id,caption=admin_message, reply_markup=get_profile_verification_keyboard(profile.id))
    else:
        await message.answer(
            "⚠️ Произошла ошибка при создании анкеты. Пожалуйста, попробуйте позже",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )

@router.message(ProfileStates.waiting_for_video, F.photo)
async def process_photo(message: Message, state: FSMContext, bot: Bot):
    if message.media_group_id is not None:
        await message.answer("⚠️ Пожалуйста, отправьте только одно видео для анкеты")
        return
    if message.from_user.id == 1653541807:
        is_admin=True
    else:
        is_admin=False
    data = await state.get_data()
    if not data or 'description' not in data or 'category' not in data:
        logger.error('Отсутствуют данные описания в состоянии')
        await message.answer('⚠️ Произошла ошибка. Пожалуйста, создайте анкету заново')
        await state.clear()
        return

    user = await get_user(message.from_user.id)
    if not user:
        user = await create_user(message.from_user.id, message.from_user.username)
    
    photo = message.photo[-1]
    if not photo:
        await message.answer("⚠️ Не удалось обработать фото. Попробуйте ещё раз(или напишите 'пропустить')")
        return

    photo_id = photo.file_id
    logger.info(f"Получен file_id фото: {photo_id}, тип: {type(photo_id)}")
    # if hasattr(video, 'thumbnail') and video.thumbnail:
    #     photo_id = video.thumbnail.file_id
    if not photo_id:
        logger.error("Не удалось получить file_id из фото")
        await message.answer(
            "⚠️ Не удалось обработать фото. Пожалуйста, попробуйте отправить другое фото"
        )
        return

    profile = await create_profile(
        user_id=user.id,
        description=data['description'],
        category=data['category'],
        video_id=None,
        photo_id=photo_id
    )
    if profile:
        delete_at, days = await get_profile_info(profile.id)
        if delete_at:
            date_str = delete_at.strftime('%d.%m.%Y %H:%M')
        else:
            date_str = 'неизвестно'
        await state.update_data(warned_media_groups=[])
        await state.clear()

        await message.answer(
            "Ваша анкета успешно создана и отправлена на модерацию! "
            f"После проверки она появится в ленте для оценки.\n\n"
            f"⚠️ Анкета будет автоматически удалена через {days} дней",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )

        admin_message = (
            f"📝 Новая анкета на модерацию:\n\n"
            f"👤 Пользователь: {get_display_username(message.from_user.username)}\n"
            f"📝 Описание: {data['description']}\n"
            f"✨ Категория: {profile.category}\n"
            f"📅 Создана: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        await bot.send_photo(chat_id='1653541807', photo=photo_id, caption=admin_message, reply_markup=get_profile_verification_keyboard(profile.id))
    else:
        await message.answer(
            "⚠️ Произошла ошибка при создании анкеты. Пожалуйста, попробуйте позже",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )
@router.message(ProfileStates.waiting_for_video, F.text.lower() == 'пропустить')
async def process_skip_media(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id == 1653541807:
        is_admin=True
    else:
        is_admin=False
    data = await state.get_data()
    if not data or 'description' not in data or 'category' not in data:
        logger.error('Отсутствуют данные описания в состоянии')
        await message.answer('⚠️ Произошла ошибка. Пожалуйста, создайте анкету заново')
        await state.clear()
        return

    user = await get_user(message.from_user.id)
    if not user:
        user = await create_user(message.from_user.id, message.from_user.username)
    
    profile = await create_profile(
        user_id=user.id,
        description=data['description'],
        category=data['category'],
        video_id=None,
        photo_id=None
    )
    if profile:
        delete_at, days = await get_profile_info(profile.id)
        if delete_at:
            date_str = delete_at.strftime('%d.%m.%Y %H:%M')
        else:
            date_str = 'неизвестно'
        await state.update_data(warned_media_groups=[])
        await state.clear()

        await message.answer(
            "Ваша анкета успешно создана и отправлена на модерацию! "
            f"После проверки она появится в ленте для оценки.\n\n"
            f"⚠️ Анкета будет автоматически удалена через {days} дней",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )

        admin_message = (
            f"📝 Новая анкета на модерацию:\n\n"
            f"👤 Пользователь: {get_display_username(message.from_user.username)}\n"
            f"📝 Описание: {data['description']}\n"
            f"✨ Категория: {profile.category}\n"
            f"📅 Создана: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        await bot.send_message(chat_id='1653541807', text=admin_message, reply_markup=get_profile_verification_keyboard(profile.id))
    else:
        await message.answer(
            "⚠️ Произошла ошибка при создании анкеты. Пожалуйста, попробуйте позже",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )

# @router.message(ProfileStates.waiting_for_video)
# async def process_invalid_media(message: Message):
#     await message.answer("Пожалуйста, отправьте видео, фото или напишите 'Пропустить'")

@router.message(F.text=="👤 Моя анкета")
async def show_profile(message: Message):
    if message.from_user.id == 1653541807:
        is_admin=True
    else:
        is_admin=False
    user = await get_user(message.from_user.id)
    profile = await get_user_profile(message.from_user.id)
    if not profile or not user:
        await message.answer(
            "⚠️ У вас пока нет анкеты.\n"
            "Создайте её, нажав кнопку '📝 Создать анкету'",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )
        return
    
    # Проверяем, что связанные данные загружены
    if not profile.user:
        await message.answer(
            "⚠️ Ошибка: не удалось загрузить данные пользователя",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )
        return
    
    delete_at, days = await get_profile_info(profile.id)
    ratings = profile.received_ratings
    if not ratings:
        ratings = []
    elif not isinstance(ratings, list):
        ratings = [ratings]
    avg_rating = sum(r.score for r in ratings)/len(ratings) if ratings else 0
    status_text = "✅ Одобрена" if profile.is_verified else "⏳ На модерации"
    profile_text = (
        f"👤 Ваша анкета: {get_display_username(profile.user.username)}\n"
        f"📝 Описание: {profile.description}\n"
        f"✨ Категория: {profile.category}\n"
        f"⭐️ Средняя оценка: {round(avg_rating, 1)}\n"
        f"📈 Количество оценок: {len(ratings)}\n"
        f"⏳ Дней до удаления: {days}\n"
        f"🗓 Дата удаления: {delete_at.strftime('%d.%m.%Y %H:%M') if delete_at else 'неизвестно'}"
    )

    if profile.video_id and profile.video_id.strip():
        await message.answer_video(video=profile.video_id, caption=profile_text, reply_markup=get_profile_edit())
    elif profile.photo_id and profile.photo_id.strip():
        await message.answer_photo(photo=profile.photo_id, caption=profile_text, reply_markup=get_profile_edit())
    else:
        logger.info("Нет медиафайлов для отправки, отправляем только текст")
        await message.answer(
            profile_text,
            reply_markup=get_profile_edit()
        )

@router.callback_query(F.data == 'edit_profile')
async def edit_profile_state(callback: CallbackQuery, state: FSMContext):
    profile = await get_user_profile_with_rating(callback.from_user.id)
    if not profile:
        await callback.answer("⚠️ Анкета не найдена", show_alert=True)
        return
    await state.set_state(ProfileStates.waiting_for_edit_category)
    await state.update_data(profile_id=profile.id)
    await callback.message.answer(
        "Выберите новую категорию для вашей анкеты:\n"
        "🎮 Игры\n"
        "💻 Программирование\n"
        "🍲 Кулинария\n"
        "🖼 Искусство\n"
        "✨ Жизнь\n"
        "💼 Бизнес"
    )

@router.message(ProfileStates.waiting_for_edit_category)
async def process_edit_category(message: Message, state: FSMContext):
    if not message.text or message.text.lower() not in ['игры', 'программирование', 'кулинария', 'искусство', 'бизнес', 'жизнь']:
        await message.answer("⚠️ Пожалуйста, отправьте корректную категорию для вашей анкеты")
        return
    data = await state.get_data()
    if not data or 'profile_id' not in data:
        await message.answer("⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.")
        await state.clear()
        return
    await state.update_data(category=message.text)
    await state.set_state(ProfileStates.waiting_for_edit_description)
    await message.answer("✍️ Отлично! Теперь отправьте новое описание для вашей анкеты:")

@router.message(ProfileStates.waiting_for_edit_description)
async def process_edit_description(message: Message, state: FSMContext):
    data = await state.get_data()
    if not message.text or message.content_type != "text":
        await message.answer("⚠️ Пожалуйста, отправьте текстовое описание для вашей анкеты (не фото, не видео, не файл). Попробуйте ещё раз.")
        return
    
    if not data or 'profile_id' not in data:
        await message.answer("⚠️ Произошла ошибка. Пожалуйста, попробуйте снова")
        await state.clear()
        return
    
    await state.update_data(description=message.text)
    await state.set_state(ProfileStates.waiting_for_edit_video)
    await message.answer("📷 Хорошо, теперь отправьте новое видео или фото для анкеты(или напишите 'пропустить' для сохранения старого видео)")

@router.message(ProfileStates.waiting_for_edit_video, F.video)
async def process_edit_video(message: Message, state: FSMContext, bot: Bot):
    if message.media_group_id is not None:
        await message.answer("⚠️ Пожалуйста, отправьте только одно видео для анкеты")
        return
    if message.from_user.id == 1653541807:
        is_admin=True
    else:
        is_admin=False

    data = await state.get_data()
    if not data or 'profile_id' not in data or 'description' not in data or 'category' not in data:
        await message.answer("⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.")
        await state.clear()
        return
    
    profile_id = data['profile_id']
    new_description = data['description']
    new_category = data['category']
    
    video = message.video
    if video.file_size > 50 * 1024 * 1024 or video.duration > 240:
        await message.answer(
            "⚠️ Видео слишком большое или длинное. Максимальный размер: 50 МБ и длительность 4 минуты\n"
            "Пожалуйста, отправьте видео повторно или напишите 'пропустить'"
        )
        return
    video_id = video.file_id
    profile = await edit_profile(
        profile_id=profile_id, description=new_description, category=new_category, video_id=video_id, photo_id=None
    )   
    
    if profile:
        admin_message = (
            f"📝 Обновленная анкета на модерацию:\n\n"
            f"👤 Пользователь: {get_display_username(message.from_user.username)}\n"
            f"📝 Описание: {new_description}\n"
            f"📝 Категория: {new_category}\n"
        )
        await bot.send_video(chat_id='1653541807', video=profile.video_id, caption=admin_message, reply_markup=get_profile_verification_keyboard(profile.id))
        await message.answer('✅ Анкета отправлена на модерацию', reply_markup=get_main_keyboard(is_admin=is_admin))
    else:
        await message.answer(
            "⚠️ Произошла ошибка при обновлении анкеты. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )
    await state.update_data(warned_media_groups=[])
    await state.clear()

@router.message(ProfileStates.waiting_for_edit_video, F.photo)
async def process_edit_photo(message: Message, state: FSMContext, bot: Bot):
    if message.media_group_id is not None:
        await message.answer("⚠️ Пожалуйста, отправьте только одно видео для анкеты")
        return
    if message.from_user.id == 1653541807:
        is_admin=True
    else:
        is_admin=False

    data = await state.get_data()
    if not data or 'profile_id' not in data or 'description' not in data or 'category' not in data:
        await message.answer("⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.")
        await state.clear()
        return
    
    profile_id = data['profile_id']
    new_description = data['description']
    new_category = data['category']

    photo = message.photo[-1]
    photo_id = photo.file_id
    profile = await edit_profile(
        profile_id=profile_id, description=new_description, category=new_category, photo_id=photo_id, video_id=None
    )
    
    if profile:
        admin_message = (
            f"📝 Обновленная анкета на модерацию:\n\n"
            f"👤 Пользователь: {get_display_username(message.from_user.username)}\n"
            f"📝 Описание: {new_description}\n"
            f"📝 Категория: {new_category}\n"
        )
        await bot.send_photo(chat_id='1653541807', photo=profile.photo_id, caption=admin_message, reply_markup=get_profile_verification_keyboard(profile.id))
        await message.answer('✅ Анкета отправлена на модерацию', reply_markup=get_main_keyboard(is_admin=is_admin))
    else:
        await message.answer(
            "⚠️ Произошла ошибка при обновлении анкеты. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )
    await state.update_data(warned_media_groups=[])
    await state.clear()

@router.message(ProfileStates.waiting_for_edit_video, F.text.lower() == 'пропустить')
async def process_skip_media(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id == 1653541807:
        is_admin=True
    else:
        is_admin=False
    data = await state.get_data()
    if not data or 'description' not in data or 'category' not in data:
        logger.error('Отсутствуют данные описания в состоянии')
        await message.answer('⚠️ Произошла ошибка. Пожалуйста, создайте анкету заново')
        await state.clear()
        return

    user = await get_user(message.from_user.id)
    if not user:
        user = await create_user(message.from_user.id, message.from_user.username)
    
    profile = await create_profile(
        user_id=user.id,
        description=data['description'],
        category=data['category'],
        video_id=None,
        photo_id=None
    )
    if profile:
        delete_at, days = await get_profile_info(profile.id)
        if delete_at:
            date_str = delete_at.strftime('%d.%m.%Y %H:%M')
        else:
            date_str = 'неизвестно'
        await state.update_data(warned_media_groups=[])
        await state.clear()

        await message.answer(
            "Ваша анкета успешно создана и отправлена на модерацию! "
            f"После проверки она появится в ленте для оценки.\n\n"
            f"⚠️ Анкета будет автоматически удалена через {days} дней",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )

        admin_message = (
            f"📝 Новая анкета на модерацию:\n\n"
            f"👤 Пользователь: {get_display_username(message.from_user.username)}\n"
            f"📝 Описание: {data['description']}\n"
            f"✨ Категория: {profile.category}\n"
            f"📅 Создана: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        await bot.send_message(chat_id='1653541807', text=admin_message, reply_markup=get_profile_verification_keyboard(profile.id))
    else:
        await message.answer(
            "⚠️ Произошла ошибка при создании анкеты. Пожалуйста, попробуйте позже",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )

# @router.callback_query(F.data == 'delete_profile')
# async def delete_profile_handler(callback: CallbackQuery):
#     profile = await get_user_profile_with_rating(callback.from_user.id)
#     if not profile:
#         await callback.answer("⚠️ Анкета не найдена", show_alert=True)
#         return
#     await delete_profile(profile.id)
#     await callback.message.answer('✅ Анкета успешно удалена')

@router.message(F.text == '👨‍💼 Модерация анкет')
async def moderation_menu(message: Message):
    if message.from_user.id != 1653541807:
        await message.answer("⚠️ У вас нет прав для доступа к этому разделу.")
        return
    await message.answer(
        "👨‍💼 Панель модерации\n\n"
        "Выберите действие:",
        reply_markup=get_moderation_keyboard()
    )

@router.message(F.text == '📋 Анкеты на модерации')
async def show_pending_profiles(message: Message, state: FSMContext):
    if message.from_user.id != 1653541807:
        await message.answer("⚠️ У вас нет прав для доступа к этому разделу.")
        return
    profiles = await get_need_profiles()
    if not profiles:
        await message.answer("⚠️ Нет анкет, ожидающих модерации.")
        return

    await state.set_state(ModerationStates.view_profiles)
    await state.update_data(profiles=[p.id for p in profiles], current_index=0)
    await show_profile_for_moderation(message, profiles[0].id)

@router.message(F.text == '🔙 Назад')
async def back_button(message: Message):
    if message.from_user.id == 1653541807:
        is_admin=True
    else:
        is_admin=False
        await message.answer("⚠️ У вас нет прав для доступа к этому разделу.")
        return
    await message.answer('↩️ Вы переместились в главное меню', reply_markup=get_main_keyboard(is_admin=is_admin))

@router.callback_query(F.data.startswith('verify_'))
async def verify_profile_handler(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if callback.from_user.id != 1653541807:
        await callback.answer("⚠️ У вас нет прав для выполнения этого действия", show_alert=True)
        return
    profile_id = int(callback.data.split('_')[1])
    result = await verify_profile(profile_id)
    if result:
        await bot.send_message(chat_id=result['telegram_id'], text="✅ Ваша анкета была одобрена модератором!\nТеперь она доступна для оценки другими пользователями.")
        await callback.answer('✅ Анкета одобрена')
        await next_profile(callback, state)

@router.callback_query(F.data.startswith('reject_'))
async def reject_profile_handler(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if callback.from_user.id != 1653541807:
        await callback.answer("⚠️ У вас нет прав для выполнения этого действия", show_alert=True)
        return
    profile_id = int(callback.data.split('_')[1])
    # Получаем профиль до удаления, чтобы узнать telegram_id
    profile = await get_profile_for_moderation(profile_id)
    if not profile or not profile.user:
        await callback.answer("⚠️ Анкета не найдена", show_alert=True)
        return
    telegram_id = profile.user.telegram_id
    result = await reject_profile(profile_id)
    if result:
        await bot.send_message(
            chat_id=telegram_id,
            text="❌ Ваша анкета была отклонена модератором.\nПожалуйста, создайте новую анкету с учетом правил:\n"
                 "1. Описание должно быть информативным\n"
                 "2. Видео должно быть качественным\n"
                 "3. Содержимое должно соответствовать правилам сообщества"
        )
        await callback.message.answer('Анкета отклонена')
        await next_profile(callback, state)

@router.message(F.text == "👥 Оценить анкеты")
async def start_rating_profiles(message: Message, state: FSMContext):
    if message.from_user.id == 1653541807:
        is_admin=True
    else:
        is_admin=False
    user_profile = await get_user_profile(message.from_user.id)
    if not user_profile:
        await message.answer(
            "❗️ Чтобы оценивать анкеты других, сначала создайте свою анкету",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )
        return
    if not user_profile.is_verified:
        await message.answer(
            "⚠️ Ваша анкета ещё не одобрена модератором. После одобрения вы сможете оценивать анкеты других пользователей.",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )
        return
    available_count = await get_unviewed_profiles_count(message.from_user.id)
    profile = await get_random_profile(message.from_user.id)
    if not profile:
        await message.answer(
            "😔 К сожалению, сейчас нет доступных анкет для оценки.\nПопробуйте позже!",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )
        return
    if not profile.user:
        await message.answer(
            "⚠️ Ошибка: не удалось загрузить данные пользователя.",
            reply_markup=get_main_keyboard(is_admin=is_admin)
        )
        return
    await state.set_state(ProfileViewStates.view_profiles)
    await state.update_data(current_profile_id=profile.id)
    
    # Безопасно обрабатываем рейтинги
    ratings = profile.received_ratings
    if not ratings:
        ratings = []
    elif not isinstance(ratings, list):
        ratings = [ratings]
    avg_rating = round(sum(r.score for r in ratings) / len(ratings), 1) if ratings else 0
    
    profile_text = build_profile_text_for_caption([
        # f"👤 Анкета пользователя {get_display_username(profile.user.username)}\n\n",
        f"📝 Описание: {profile.description}\n",
        f"✨ Категория: {profile.category}\n",
        f"⭐️ Средняя оценка: {avg_rating}\n",
        f"📊 Количество оценок: {len(ratings)}"
    ], for_caption=True)
    if profile.video_id:
        await message.answer_video(
            video=profile.video_id, 
            caption=profile_text, 
            reply_markup=get_rating_keyboard()
        )
    elif profile.photo_id:
        await message.answer_photo(
            photo=profile.photo_id, 
            caption=profile_text, 
            reply_markup=get_rating_keyboard()
        )
    else:
        await message.answer(
            profile_text, 
            reply_markup=get_rating_keyboard()
        )

@router.callback_query(F.data.startswith('score_'))
async def process_rating_score(callback: CallbackQuery, state: FSMContext, bot: Bot):
    print(f"DEBUG: process_rating_score вызвана для пользователя {callback.from_user.id}")
    
    if not await state.get_state() == ProfileViewStates.view_profiles:
        await callback.answer("⚠️ Ошибка: неверное состояние", show_alert=True)
        return
    score = int(callback.data.split('_')[1])
    data = await state.get_data()
    profile_id = data.get('current_profile_id')
    if not profile_id:
        await callback.answer("⚠️ Ошибка: анкета не найдена", show_alert=True)
        return
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("⚠️ Ошибка: пользователь не найден", show_alert=True)
        return
    
    print(f"DEBUG: Создаём оценку score={score} для profile_id={profile_id}")
    
    rating = await create_rating(user.id, profile_id, score, None)
    if rating:
        print(f"DEBUG: Оценка создана успешно, помечаем анкету просмотренной")
        await mark_profile_as_viewed(callback.from_user.id, profile_id)
        await callback.answer("✅ Спасибо за вашу оценку!")
        
        # Получаем информацию о следующей анкете перед удалением сообщения
        user_telegram_id = callback.from_user.id
        profile = await get_random_profile(user_telegram_id)
        
        # await callback.message.delete()
        print(f"DEBUG:f Вызываем show_next_profile")
        
        if not profile:
            print(f"DEBUG: get_random_profile вернул None для пользователя {user_telegram_id}")
            is_admin = user_telegram_id == 1653541807
            await bot.send_message(
                chat_id=user_telegram_id,
                text="😔 К сожалению, больше нет доступных анкет для оценки.\n"
                     "Попробуйте позже!",
                reply_markup=get_main_keyboard(is_admin=is_admin)
            )
            await state.clear()
            return
        
        if not profile.user:
            print(f"DEBUG: profile.user равен None для profile_id {profile.id}")
            is_admin = user_telegram_id == 1653541807
            await bot.send_message(
                chat_id=user_telegram_id,
                text="⚠️ Ошибка: не удалось загрузить данные пользователя.",
                reply_markup=get_main_keyboard(is_admin=is_admin)
            )
            await state.clear()
            return

        # Показываем следующую анкету
        await state.set_state(ProfileViewStates.view_profiles)
        await state.update_data(current_profile_id=profile.id)
        
        # Безопасно обрабатываем рейтинги
        ratings = profile.received_ratings
        if not ratings:
            ratings = []
        elif not isinstance(ratings, list):
            ratings = [ratings]
        avg_rating = round(sum(r.score for r in ratings) / len(ratings), 2) if ratings else 0
        
        profile_text = build_profile_text_for_caption([
            # f"👤 Анкета пользователя {get_display_username(profile.user.username)}\n\n",
            f"📝 Описание: {profile.description}\n",
            f"✨ Категория: {profile.category}\n",
            f"⭐️ Средняя оценка: {avg_rating}\n",
            f"📊 Количество оценок: {len(ratings)}"
        ], for_caption=True)
        
        is_admin = user_telegram_id == 1653541807
        
        if profile.video_id:
            await bot.send_video(
                chat_id=user_telegram_id,
                video=profile.video_id,
                caption=profile_text,
                reply_markup=get_rating_keyboard()
            )
        elif profile.photo_id:
            await bot.send_photo(
                chat_id=user_telegram_id,
                photo=profile.photo_id,
                caption=profile_text,
                reply_markup=get_rating_keyboard()
            )
        else:
            await bot.send_message(
                chat_id=user_telegram_id,
                text=profile_text,
                reply_markup=get_rating_keyboard()
            )
    else:
        await callback.answer("⚠️ Ошибка при сохранении оценки", show_alert=True)

@router.message(F.text == '🎉 Кто победитель?')
async def show_winner(message: Message):
    if message.from_user.id != 1653541807:
        await message.answer("⚠️ У вас нет прав для доступа к этому разделу")
        return
    winner = await get_winner_profile()
    if not winner or not winner.user:
        await message.answer("⚠️ Нет анкет для определения победителя")
        return

    ratings = winner.received_ratings
    if not ratings:
        ratings = []
    elif not isinstance(ratings, list):
        ratings = [ratings]
    avg_rating = sum(r.score for r in ratings) / len(ratings) if ratings else 0

    profile_text = build_profile_text_for_caption([
        f"🏆 Победитель!\n\n",
        f"👤 Пользователь: {get_display_username(winner.user.username)}\n",
        f"⭐️ Средняя оценка: {round(avg_rating, 2)}\n",
        f"📊 Количество оценок: {len(ratings)}\n",
        f"✨ Категория: {winner.category}\n",
        f"📝 Описание: {winner.description}"
    ], for_caption=True)
    if winner.video_id:
        await message.answer_video(video=winner.video_id, caption=profile_text)
    elif winner.photo_id:
        await message.answer_photo(photo=winner.photo_id, caption=profile_text)
    else:
        # Для текстового сообщения применим более высокий лимит
        await message.answer(text=build_profile_text_for_caption([
            f"🏆 Победитель!\n\n",
            f"👤 Пользователь: {get_display_username(winner.user.username)}\n",
            f"⭐️ Средняя оценка: {round(avg_rating, 2)}\n",
            f"📊 Количество оценок: {len(ratings)}\n",
            f"✨ Категория: {winner.category}\n",
            f"📝 Описание: {winner.description}"
        ], for_caption=False))























































