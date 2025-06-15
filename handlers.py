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
    verify_profile, reject_profile
)
logger = logging.getLogger(__name__)
router = Router()
class ProfileStates(StatesGroup):
    waiting_for_description = State()
    waiting_for_video = State()
    waiting_for_edit_description = State()
    waiting_for_edit_video = State()

class RatingStates(StatesGroup):
    waiting_for_rating = State()
    waiting_for_comment = State()

class ModerationStates(StatesGroup):
    view_profiles = State()

async def show_profile_for_moderation(message: Message, profile):
    profile_text = (
        f"📝 Анкета на модерацию:\n\n"
        f"👤 Пользователь: @{profile.user.username}\n"
        f"📝 Описание: {profile.description}\n"
        f"📅 Создана: {profile.created_at.strftime('%d.%m.%Y %H:%M')}"
    )
    await message.answer_video(
        video=profile.video_id,
        caption=profile_text,
        reply_markup=get_profile_moderation_keyboard(profile.id)
    )

@router.message(Command('start'))
async def start(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        user = await create_user(message.from_user.id, message.from_user.username)
    if message.from_user.id == 1653541807:
        is_admin=True
    else:
        is_admin=False
    await message.answer("Добро пожаловать в бот анкет! 🎉\n"
        "Вы можете создать свою анкету или оценивать анкеты других пользователей.",
                         reply_markup=get_main_keyboard(is_admin=is_admin))

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
async def process_video(message: Message, state: FSMContext, bot: Bot):
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

    admin_message = (
        f"📝 Новая анкета на модерацию:\n\n"
        f"👤 Пользователь: @{message.from_user.username}\n"
        f"📝 Описание: {data['description']}\n"
        f"📅 Создана: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    await bot.send_video(chat_id='1653541807',video=video_id, caption=admin_message, reply_markup=get_profile_verification_keyboard(profile.id))

@router.message(F.text=="👤 Моя анкета")
async def show_profile(message: Message):
    user = await get_user(message.from_user.id)
    profile = await get_user_profile(message.from_user.id)
    if not profile or not user:
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

@router.callback_query(F.data == 'edit_profile')
async def edit_profile_state(callback: CallbackQuery, state: FSMContext):
    profile = await get_user_profile_with_rating(callback.from_user.id)
    if not profile:
        await callback.answer("Анкета не найдена", show_alert=True)
        return
    await state.set_state(ProfileStates.waiting_for_edit_description)
    await state.update_data(profile_id=profile.id)
    await callback.message.answer("Введите новое описание для анкеты:")

@router.message(ProfileStates.waiting_for_edit_description)
async def process_edit_description(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data or 'profile_id' not in data:
        await message.answer("Произошла ошибка. Пожалуйста, попробуйте снова.")
        await state.clear()
        return
    await state.update_data(description=message.text)
    await state.set_state(ProfileStates.waiting_for_edit_video)
    await message.answer("Теперь отправьте новое видео для анкеты (или отправьте 'пропустить' для сохранения старого):")

@router.message(ProfileStates.waiting_for_edit_video)
async def process_edit_video(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if not data or 'profile_id' not in data or 'description' not in data:
        await message.answer("Произошла ошибка. Пожалуйста, попробуйте снова.")
        await state.clear()
        return
    profile_id = data['profile_id']
    new_description = data['description']
    video = message.video
    if video.file_size > 50 * 1024 * 1024 or video.duration > 240:
        await message.answer(
            "⚠️ Видео слишком большое или длинное. Максимальный размер: 50 МБ и длительность 4 минуты\n"
            "Пожалуйста, отправьте видео повторно или напишите 'пропустить'."
        )
    video_id = video.file_id
    profile = await edit_profile(
        profile_id=profile_id, description=new_description, video_id=video_id
    )
    if profile:
        admin_message = (
            f"📝 Обновленная анкета на модерацию:\n\n"
            f"👤 Пользователь: @{message.from_user.username}\n"
            f"📝 Описание: {new_description}\n"
        )
        await bot.send_video(chat_id='1653541807', video=profile.video_id, caption=admin_message, reply_markup=get_profile_edit())
        await message.answer('Анкета отправлена на модерацию', reply_markup=get_main_keyboard())
    else:
        await message.answer(
            "Произошла ошибка при обновлении анкеты. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
    await state.clear()

@router.callback_query(F.data == 'delete_profile')
async def delete_profile_handler(callback: CallbackQuery):
    profile = await get_user_profile_with_rating(callback.from_user.id)
    if not profile:
        await callback.answer("Анкета не найдена", show_alert=True)
        return
    await delete_profile(profile.id)
    await callback.answer('Анкета успешно удалена')

@router.message(F.text == '👨‍💼 Модерация анкет')
async def moderation_menu(message: Message):
    if message.from_user.id != 1653541807:
        await message.answer("У вас нет прав для доступа к этому разделу.")
        return
    await message.answer(
        "👨‍💼 Панель модерации\n\n"
        "Выберите действие:",
        reply_markup=get_moderation_keyboard()
    )

@router.message(F.text == '📋 Анкеты на модерации')
async def show_pending_profiles(message: Message, state: FSMContext):
    if message.from_user.id != 1653541807:
        await message.answer("У вас нет прав для доступа к этому разделу.")
        return
    profiles = await get_need_profiles()
    if not profiles:
        await message.answer("Нет анкет, ожидающих модерации.")
        return

    await state.set_state(ModerationStates.view_profiles)
    await state.update_data(profiles=[p.id for p in profiles], current_index=0)
    await show_profile_for_moderation(message, profiles[0])

@router.message(F.text == '🔙 Назад')
async def back_button(message: Message):
    if message.from_user.id != 1653541807:
        await message.answer("У вас нет прав для доступа к этому разделу.")
        return
    await message.answer('Вы переместились в главное меню', reply_markup=get_main_keyboard(is_admin=True))

@router.message(F.data == 'next_profile')
async def next_profile(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != 1653541807:
        await callback.answer("У вас нет прав для этого действия")
        return
    data = state.get_data()
    if not data:
        await callback.answer("Ошибка: данные не найдены")
        return

    profiles = data['profiles']
    current_index = data['current_index']
    if current_index >= len(profiles)-1:
        await callback.answer("Это последняя анкета")
        return
    current_index += 1
    await state.update_data(current_idnex=current_index)
    profile = await get_profile_for_moderation(profiles[current_index])
    if profile:
        await callback.message.delete()
        await show_profile_for_moderation(callback.message, profile)
    else:
        await callback.answer("Ошибка при загрузке анкеты")

















































