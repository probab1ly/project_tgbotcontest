from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from keyboards import get_main_keyboard, get_rating_keyboard, get_profile_verification_keyboard, get_profile_edit
import asyncio
import logging
from datetime import datetime
from database import (
    get_user, create_user, create_profile, get_random_profile,
    create_rating, delete_ex_profiles, get_profile_info, get_user_profile
)
logger = logging.getLogger(__name__)
router = Router()
class ProfileStates(StatesGroup):
    waiting_for_description = State()
    waiting_for_video = State()

class RatingStates(StatesGroup):
    waiting_for_rating = State()
    waiting_for_comment = State()

@router.message(Command('start'))
async def start(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        user = await create_user(message.from_user.id, message.from_user.username)

    await message.answer("Добро пожаловать в бот анкет! 🎉\n"
        "Вы можете создать свою анкету или оценивать анкеты других пользователей.",
                         reply_markup=get_main_keyboard())

@router.message(F.text == '📝 Создать анкету')
async def create_profile_start(message: Message, state: FSMContext):
    await state.set_state(ProfileStates.waiting_for_description)
    await message.answer("Пожалуйста, напишите описание для вашей анкеты:")

@router.message(ProfileStates.waiting_for_description)
async def process_description(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое описание для вашей анкеты.")
        return
    await state.update_data(description=message.text)
    await state.set_state(ProfileStates.waiting_for_video)
    await message.answer("Теперь отправьте видео для вашей анкеты:")

@router.message(ProfileStates.waiting_for_video, F.video)
async def process_video(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data or 'description' not in data:
        logger.error('Отсутствуют данные описания в состоянии')
        await message.answer('Произошла ошибка. Пожалуйста, создайте анкету заново.')
        await state.clear()
        return

    user = await get_user(message.from_user.id)
    if not user:
        logger.error(f"Пользователь не найден при создании анкеты: {message.from_user.id}")
        await message.answer("Пожалуйста, сначала используйте команду /start")
        await state.clear()
        return

    video = message.video
    if not video:
        logger.error("Объект видео не найден в сообщении")
        await message.answer("Не удалось обработать видео. Пожалуйста, попробуйте отправить фото.")
        return

    if video.file_size > 50*1024*1024 or video.duration>240:
        await message.answer(
            "⚠️ Видео слишком большое или длинное. Максимальный размер: 50 МБ и длительность 4 минуты\n"
            "Пожалуйста, отправьте видео повторно."
        )
        return

    video_id = video.file_id
    logger.info(f"Получен file_id видео: {video_id}, тип: {type(video_id)}")
    # if hasattr(video, 'thumbnail') and video.thumbnail:
    #     photo_id = video.thumbnail.file_id
    if not video_id:
        logger.error("Не удалось получить file_id из видео")
        await message.answer(
            "Не удалось обработать видео. Пожалуйста, попробуйте отправить другое видео."
        )
        return

    profile = await create_profile(
        user_id=user.id,
        description=data['description'],
        video_id=video_id,
    )
    delete_at, days = await get_profile_info(profile.id)
    await state.clear()
    await message.answer(
        "Ваша анкета успешно создана и отправлена на модерацию! "
        f"После проверки она появится в ленте для оценки.\n\n"
        f"⚠️ Анкета будет автоматически удалена через {days} дней"
        f"({delete_at.strftime('%d.%m.%Y %H:%M')})",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text=="👤 Моя анкета")
async def show_profile(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer(
            "У вас пока нет анкеты.\n"
            "Создайте её, нажав кнопку '📝 Создать анкету'",
            reply_markup=get_main_keyboard()
        )
    profile = await get_user_profile(message.from_user.id)
    if not profile:
        await message.answer(
            "У вас пока нет анкеты.\n"
            "Создайте её, нажав кнопку '📝 Создать анкету'",
            reply_markup=get_main_keyboard()
        )
    delete_at, days = await get_profile_info(profile.id)
    ratings = profile.received_ratings
    avg_rating = sum(r.score for r in ratings)/len(ratings) if ratings else 0
    status_text = "✅ Одобрена" if profile.is_verified else "⏳ На модерации"
    profile_text = (
        f"👤 Ваша анкета:\n\n"
        f"📝 Описание: {profile.description}\n"
        f"📊 Статус: {status_text}\n"
        f"⭐️ Средняя оценка: {round(avg_rating, 1)}\n"
        f"📈 Количество оценок: {len(ratings)}\n"
        f"⏳ Дней до удаления: {days}\n"
        f"🗓 Дата удаления: {delete_at.strftime('%d.%m.%Y %H:%M')}"
    )

    if profile.video_id and profile.video_id.strip():
        await message.answer_video(video=profile.video_id, caption=profile_text, reply_markup=get_profile_edit())
    else:
        logger.info("Нет медиафайлов для отправки, отправляем только текст")
        await message.answer(
            profile_text,
            reply_markup=get_profile_edit()
        )



