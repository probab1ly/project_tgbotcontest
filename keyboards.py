from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, KeyboardButton, InlineKeyboardButton
def get_main_keyboard(is_admin: bool = False):
    keyboard = [
        [
            KeyboardButton(text="📝 Создать анкету"),
            KeyboardButton(text="👤 Моя анкета")
        ],
        [
            KeyboardButton(text="👥 Оценить анкеты")        
        ]
    ]

    if is_admin:
        keyboard.append(
        [
            KeyboardButton(text="👨‍💼 Модерация анкет"),
            KeyboardButton(text="🎉 Кто победитель?")
        ]
        )

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_moderation_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard = [
            [
                KeyboardButton(text="📋 Анкеты на модерации"),
                KeyboardButton(text="🔙 Назад")
            ]
        ], resize_keyboard=True
    )
    return keyboard

def get_moderation_profile(profile_id: int):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard = [
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"verify_{profile_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{profile_id}")
            ]
        ]
    )
    return keyboard

def get_rating_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text='1⭐', callback_data='score_1'),
                InlineKeyboardButton(text='2⭐', callback_data='score_2'),
                InlineKeyboardButton(text='3⭐', callback_data='score_3'),
                InlineKeyboardButton(text='4⭐', callback_data='score_4'),
                InlineKeyboardButton(text='5⭐', callback_data='score_5'),
            ]
        ]
    )
    return keyboard

def get_profile_edit():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard = [
            [
                InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_profile")
                # InlineKeyboardButton(text="🗑 Удалить", callback_data="delete_profile")
            ]
        ]
    )
    return keyboard

def get_profile_verification_keyboard(profile_id: int):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text='✅ Одобрить', callback_data=f'verify_{profile_id}'),
                InlineKeyboardButton(text='❌ Отклонить', callback_data=f'reject_{profile_id}')
            ]
        ]
    )
    return keyboard

def get_category_selection_keyboard(categories: list):
    """Создает клавиатуру для выбора категории анкет"""
    keyboard = []
    for i in range(0, len(categories), 2):  # По 2 кнопки в ряду
        row = []
        for j in range(2):
            if i + j < len(categories):
                category = categories[i + j]
                row.append(InlineKeyboardButton(
                    text=category, 
                    callback_data=f"select_category_{category}"
                ))
        keyboard.append(row)
    
    # Добавляем кнопку "Сменить категорию" в конце
    keyboard.append([
        InlineKeyboardButton(text="🔄 Сменить категорию", callback_data="change_category")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
