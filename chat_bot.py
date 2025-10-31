import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Настройка базы данных
def init_db():
    with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                nickname TEXT UNIQUE,
                age INTEGER,
                gender TEXT,
                bio TEXT,
                current_room TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                room_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                room_name TEXT,
                message_text TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS private_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER,
                receiver_id INTEGER,
                message_text TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Добавляем комнаты, если их нет
        default_rooms = [
            ("Москва", "Чат для жителей Москвы"),
            ("Питер", "Чат для питерцев"),
            ("Знакомства", "Знакомства и общение"),
            ("О жизни", "Обсуждение всего на свете")
        ]
        cursor.executemany(
            "INSERT OR IGNORE INTO rooms (name, description) VALUES (?, ?)",
            default_rooms
        )
        conn.commit()

init_db()

def save_message(user_id, room_name, message_text):
    with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (user_id, room_name, message_text) VALUES (?, ?, ?)",
            (user_id, room_name, message_text)
        )
        conn.commit()

def save_private_message(sender_id, receiver_id, message_text):
    with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO private_messages (sender_id, receiver_id, message_text) VALUES (?, ?, ?)",
            (sender_id, receiver_id, message_text)
        )
        conn.commit()

# Функция для уведомления пользователей в комнате
async def notify_room_users(context: ContextTypes.DEFAULT_TYPE, room_name: str, user_id: int, message: str):
    with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id FROM users WHERE current_room = ? AND user_id != ?",
            (room_name, user_id)
        )
        recipients = cursor.fetchall()

        if recipients:
            for (recipient_id,) in recipients:
                try:
                    await context.bot.send_message(
                        recipient_id,
                        message
                    )
                except Exception as e:
                    print(f"Failed to send notification to {recipient_id}: {e}")

# Текст приветствия
WELCOME_MESSAGE = """
Привет! Добро пожаловать в наш чат-бот.

Здесь ты можешь:
- Общаться в различных тематических комнатах.
- Отправлять текстовые сообщения, изображения и гифки.
- Просматривать биографии других пользователей.
- Редактировать свою анкету.

Начни с команды /start, чтобы создать свой профиль и войти в комнату.
"""

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

    if user:
        # Если пользователь уже зарегистрирован, показываем его текущую комнату
        current_room = user[5]
        if current_room:
            await update.message.reply_text(
                f"Вы уже в комнате «{current_room}». Просто напишите сообщение, "
                "и его увидят другие участники комнаты.\n"
                "Чтобы сменить комнату, используйте /rooms"
            )
        else:
            await show_rooms(update, context)
    else:
        await update.message.reply_text(
            "Привет! Давай создадим твой профиль.\n"
            "Введи свой никнейм:"
        )
        context.user_data["state"] = "waiting_nickname"

# Команда /welcome - показать приветственное сообщение
async def welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_MESSAGE)

# Обработка сообщений (регистрация и общение)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = context.user_data.get("state")

    if state == "waiting_nickname":
        nickname = update.message.text
        with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nickname FROM users WHERE nickname = ?", (nickname,))
            existing_user = cursor.fetchone()

        if existing_user:
            await update.message.reply_text("Этот никнейм уже занят. Пожалуйста, выберите другой никнейм:")
        else:
            context.user_data["nickname"] = nickname
            await update.message.reply_text("Отлично! Теперь укажи свой возраст:")
            context.user_data["state"] = "waiting_age"

    elif state == "waiting_age":
        text = update.message.text
        if text.isdigit():
            context.user_data["age"] = int(text)
            keyboard = [
                [InlineKeyboardButton("Мужской", callback_data="gender_m")],
                [InlineKeyboardButton("Женский", callback_data="gender_f")]
            ]
            await update.message.reply_text(
                "Выбери пол:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            context.user_data["state"] = "waiting_gender"
        else:
            await update.message.reply_text("Введи число!")

    elif state == "waiting_bio":
        text = update.message.text
        context.user_data["bio"] = text
        # Сохраняем пользователя в БД
        try:
            with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, NULL)",
                    (
                        user_id,
                        context.user_data["nickname"],
                        context.user_data["age"],
                        context.user_data["gender"],
                        text
                    )
                )
                conn.commit()
            await show_rooms(update, context)
            context.user_data["state"] = None  # Сбрасываем состояние
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            await update.message.reply_text("Произошла ошибка при сохранении профиля. Попробуйте еще раз.")

    elif state == "waiting_room_name":
        room_name = update.message.text
        context.user_data["room_name"] = room_name
        await update.message.reply_text("Введите описание комнаты:")
        context.user_data["state"] = "waiting_room_description"

    elif state == "waiting_room_description":
        room_description = update.message.text
        try:
            with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO rooms (name, description) VALUES (?, ?)",
                    (context.user_data["room_name"], room_description)
                )
                conn.commit()
            await update.message.reply_text(f"Комната «{context.user_data['room_name']}» успешно создана!")
            context.user_data["state"] = None  # Сбрасываем состояние
            await show_rooms(update, context)
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            await update.message.reply_text("Произошла ошибка при создании комнаты. Попробуйте еще раз.")

    elif state == "waiting_message_recipient":
        recipient_nickname = update.message.text
        with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE nickname = ?", (recipient_nickname,))
            recipient = cursor.fetchone()

        if recipient:
            context.user_data["recipient_id"] = recipient[0]
            await update.message.reply_text("Введите текст сообщения:")
            context.user_data["state"] = "waiting_message_text"
        else:
            await update.message.reply_text("Пользователь с таким никнеймом не найден. Пожалуйста, введите корректный никнейм:")

    elif state == "waiting_message_text":
        message_text = update.message.text
        try:
            with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT nickname FROM users WHERE user_id = ?",
                    (context.user_data["recipient_id"],)
                )
                recipient_nickname = cursor.fetchone()[0]

            save_private_message(user_id, context.user_data["recipient_id"], message_text)

            await context.bot.send_message(
                context.user_data["recipient_id"],
                f"Личное сообщение от пользователя {context.user_data['nickname']}:\n{message_text}"
            )
            await update.message.reply_text(f"Сообщение успешно отправлено пользователю {recipient_nickname}!")
            context.user_data["state"] = None  # Сбрасываем состояние
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            await update.message.reply_text("Произошла ошибка при отправке сообщения. Попробуйте еще раз.")

    else:
        # Обычное сообщение - пересылаем в комнату
        try:
            with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
                cursor = conn.cursor()
                # Получаем данные отправителя
                cursor.execute(
                    "SELECT nickname, current_room FROM users WHERE user_id = ?",
                    (user_id,)
                )
                user_data = cursor.fetchone()

                if user_data and user_data[1]:  # Если есть комната
                    nickname, room_name = user_data
                    # Получаем всех пользователей в комнате, кроме отправителя
                    cursor.execute(
                        "SELECT user_id FROM users WHERE current_room = ? AND user_id != ?",
                        (room_name, user_id)
                    )
                    recipients = cursor.fetchall()

                    if recipients:
                        if update.message.photo:
                            # Если сообщение содержит изображение
                            photo = update.message.photo[-1]  # Получаем самое большое изображение
                            for (recipient_id,) in recipients:
                                try:
                                    await context.bot.send_photo(
                                        recipient_id,
                                        photo=photo.file_id,
                                        caption=f"[Комната: {room_name}]\nНик: {nickname}"
                                    )
                                except Exception as e:
                                    print(f"Failed to send photo to {recipient_id}: {e}")
                                    # Удаляем пользователя из комнаты, если не удалось отправить сообщение
                                    cursor.execute(
                                        "UPDATE users SET current_room = NULL WHERE user_id = ?",
                                        (recipient_id,)
                                    )
                                    conn.commit()

                        elif update.message.document and update.message.document.mime_type == 'video/mp4':
                            # Если сообщение содержит гифку
                            gif = update.message.document
                            for (recipient_id,) in recipients:
                                try:
                                    await context.bot.send_document(
                                        recipient_id,
                                        document=gif.file_id,
                                        caption=f"[Комната: {room_name}]\nНик: {nickname}"
                                    )
                                except Exception as e:
                                    print(f"Failed to send gif to {recipient_id}: {e}")
                                    # Удаляем пользователя из комнаты, если не удалось отправить сообщение
                                    cursor.execute(
                                        "UPDATE users SET current_room = NULL WHERE user_id = ?",
                                        (recipient_id,)
                                    )
                                    conn.commit()

                        elif update.message.audio:
                            # Если сообщение содержит аудио
                            audio = update.message.audio
                            for (recipient_id,) in recipients:
                                try:
                                    await context.bot.send_audio(
                                        recipient_id,
                                        audio=audio.file_id,
                                        caption=f"[Комната: {room_name}]\nНик: {nickname}"
                                    )
                                except Exception as e:
                                    print(f"Failed to send audio to {recipient_id}: {e}")
                                    # Удаляем пользователя из комнаты, если не удалось отправить сообщение
                                    cursor.execute(
                                        "UPDATE users SET current_room = NULL WHERE user_id = ?",
                                        (recipient_id,)
                                    )
                                    conn.commit()

                        else:
                            # Если сообщение текстовое
                            text = update.message.text
                            for (recipient_id,) in recipients:
                                try:
                                    await context.bot.send_message(
                                        recipient_id,
                                        f"[Комната: {room_name}]\n"
                                        f"Ник: {nickname}\n"
                                        f"Сообщение: {text}"
                                    )
                                except Exception as e:
                                    print(f"Failed to send message to {recipient_id}: {e}")
                                    # Удаляем пользователя из комнаты, если не удалось отправить сообщение
                                    cursor.execute(
                                        "UPDATE users SET current_room = NULL WHERE user_id = ?",
                                        (recipient_id,)
                                    )
                                    conn.commit()
                    else:
                        await update.message.reply_text("В этой комнате пока никого нет.")
                    # Сохраняем сообщение в базу данных, если это текстовое сообщение
                    if update.message.text:
                        save_message(user_id, room_name, update.message.text)
                else:
                    await update.message.reply_text(
                        "Вы не в комнате. Выберите комнату с помощью /rooms"
                    )
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            await update.message.reply_text("Произошла ошибка. Попробуйте еще раз.")

# Обработка кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("gender_"):
        gender = "Мужской" if query.data == "gender_m" else "Женский"
        context.user_data["gender"] = gender
        await query.edit_message_text(f"Пол: {gender}\nТеперь напиши пару слов о себе:")
        context.user_data["state"] = "waiting_bio"

    elif query.data.startswith("join_"):
        room_name = query.data.replace("join_", "")
        user_id = update.effective_user.id
        try:
            with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET current_room = ? WHERE user_id = ?",
                    (room_name, user_id)
                )
                conn.commit()

                # Получаем никнейм, биографию пользователя и описание комнаты
                cursor.execute(
                    "SELECT nickname, bio FROM users WHERE user_id = ?",
                    (user_id,)
                )
                user_data = cursor.fetchone()
                nickname = user_data[0] if user_data else "Unknown"
                bio = user_data[1] if user_data else "Биография отсутствует"

                cursor.execute(
                    "SELECT description FROM rooms WHERE name = ?",
                    (room_name,)
                )
                room_description = cursor.fetchone()[0]

                # Уведомляем пользователей в комнате
                await notify_room_users(
                    context,
                    room_name,
                    user_id,
                    f"Пользователь {nickname} вошел в комнату «{room_name}».\nБиография: {bio}"
                )

            await query.edit_message_text(
                f"Ты в комнате «{room_name}».\nОписание комнаты: {room_description}\n"
                f"Пиши сообщения — их увидят другие участники!\n"
                f"Чтобы выйти из комнаты, используйте /leave"
            )
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            await query.edit_message_text("Произошла ошибка при входе в комнату. Попробуйте еще раз.")

    elif query.data == "create_room":
        await query.edit_message_text("Введите название комнаты:")
        context.user_data["state"] = "waiting_room_name"

# Показать список комнат
async def show_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, description FROM rooms")
            rooms = cursor.fetchall()

        # Получаем количество пользователей в каждой комнате
        rooms_with_counts = []
        for name, desc in rooms:
            with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM users WHERE current_room = ?",
                    (name,)
                )
                user_count = cursor.fetchone()[0]
                rooms_with_counts.append((name, desc, user_count))

        # Сортируем комнаты по количеству пользователей
        rooms_with_counts.sort(key=lambda x: x[2], reverse=True)

        keyboard = []
        for name, desc, user_count in rooms_with_counts:
            keyboard.append([InlineKeyboardButton(f"{name} ({user_count})", callback_data=f"join_{name}")])

        # Добавляем кнопку для создания комнаты
        keyboard.append([InlineKeyboardButton("Создать комнату", callback_data="create_room")])

        if isinstance(update, Update):
            await context.bot.send_message(
                update.effective_chat.id,
                "Выбери комнату:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Если update пришел от callback_query
            await update.message.reply_text(
                "Выбери комнату:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        await context.bot.send_message(
            update.effective_chat.id,
            "Произошла ошибка при загрузке комнат. Попробуйте позже."
        )

# Команда /rooms - показать комнаты
async def rooms_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_rooms(update, context)

# Команда /leave - покинуть комнату
async def leave_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT current_room, nickname FROM users WHERE user_id = ?",
                (user_id,)
            )
            user_data = cursor.fetchone()

            if user_data and user_data[0]:
                room_name = user_data[0]
                nickname = user_data[1]
                cursor.execute(
                    "UPDATE users SET current_room = NULL WHERE user_id = ?",
                    (user_id,)
                )
                conn.commit()

                # Уведомляем пользователей в комнате
                await notify_room_users(
                    context,
                    room_name,
                    user_id,
                    f"Пользователь {nickname} вышел из комнаты «{room_name}»"
                )

                await update.message.reply_text(
                    "Вы вышли из комнаты. Чтобы войти в другую комнату, используйте /rooms"
                )
            else:
                await update.message.reply_text(
                    "Вы не в комнате. Чтобы войти в комнату, используйте /rooms"
                )
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        await update.message.reply_text("Произошла ошибка при выходе из комнаты.")

# Команда /who - показать количество людей в комнате
async def who_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT current_room FROM users WHERE user_id = ?",
                (user_id,)
            )
            user_data = cursor.fetchone()

            if user_data and user_data[0]:
                room_name = user_data[0]
                cursor.execute(
                    "SELECT nickname FROM users WHERE current_room = ?",
                    (room_name,)
                )
                users_in_room = cursor.fetchall()

                if users_in_room:
                    users_list = "\n".join([user[0] for user in users_in_room])
                    await update.message.reply_text(
                        f"В комнате «{room_name}» находятся следующие пользователи:\n{users_list}"
                    )
                else:
                    await update.message.reply_text(
                        f"В комнате «{room_name}» пока никого нет."
                    )
            else:
                await update.message.reply_text(
                    "Вы не в комнате. Чтобы войти в комнату, используйте /rooms"
                )
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        await update.message.reply_text("Произошла ошибка при получении списка пользователей в комнате.")

# Команда /message - отправить личное сообщение
async def message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

    if user:
        await update.message.reply_text("Введите никнейм получателя:")
        context.user_data["state"] = "waiting_message_recipient"
        context.user_data["nickname"] = user[0]
    else:
        await update.message.reply_text(
            "У вас нет анкеты. Сначала создайте её с помощью /start"
        )

# Команда /mail - показать список присланных сообщений
async def mail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sender_id, message_text, timestamp FROM private_messages WHERE receiver_id = ?",
                (user_id,)
            )
            messages = cursor.fetchall()

        if messages:
            messages_list = []
            for sender_id, message_text, timestamp in messages:
                cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (sender_id,))
                sender_nickname = cursor.fetchone()[0]
                messages_list.append(f"От: {sender_nickname}\nСообщение: {message_text}\nВремя: {timestamp}\n")

            await update.message.reply_text(
                f"Ваши личные сообщения:\n\n" + "\n".join(messages_list)
            )
        else:
            await update.message.reply_text(
                "У вас нет личных сообщений."
            )
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        await update.message.reply_text("Произошла ошибка при получении списка личных сообщений.")

# Команда /help - показать список команд
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
    Доступные команды:
    /start - Начать работу с ботом
    /rooms - Показать список комнат
    /leave - Покинуть текущую комнату
    /edit_profile - Редактировать анкету
    /bio *ник пользователя* - Показать биографию пользователя
    /who - Показать список пользователей в комнате
    /message - Отправить личное сообщение
    /mail - Показать список присланных сообщений
    /help - Показать список команд
    """
    await update.message.reply_text(help_text)

# Команда /edit_profile - редактировать анкету
async def edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

    if user:
        context.user_data["state"] = "waiting_nickname"
        context.user_data["nickname"] = user[1]
        context.user_data["age"] = user[2]
        context.user_data["gender"] = user[3]
        context.user_data["bio"] = user[4]

        await update.message.reply_text(
            "Редактирование анкеты.\n"
            "Введи новый никнейм (или оставь текущий):"
        )
    else:
        await update.message.reply_text(
            "У вас нет анкеты. Сначала создайте её с помощью /start"
        )

# Команда /bio - показать биографию пользователя
async def bio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        nickname = context.args[0]
        with sqlite3.connect("chat_bot.db", check_same_thread=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT bio FROM users WHERE nickname = ?", (nickname,))
            bio = cursor.fetchone()

        if bio:
            await update.message.reply_text(f"Биография пользователя {nickname}:\n{bio[0]}")
        else:
            await update.message.reply_text(f"Пользователь {nickname} не найден или у него нет биографии.")
    except IndexError:
        await update.message.reply_text("Пожалуйста, укажите ник пользователя. Пример: /bio Имя")

def main():
    application = Application.builder().token("8185736979:AAF_qI8WiQgDYnmNI-PAzI76g0N491h__EU").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("welcome", welcome_command))
    application.add_handler(CommandHandler("rooms", rooms_command))
    application.add_handler(CommandHandler("leave", leave_room))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("edit_profile", edit_profile))
    application.add_handler(CommandHandler("bio", bio_command))
    application.add_handler(CommandHandler("who", who_command))
    application.add_handler(CommandHandler("message", message_command))
    application.add_handler(CommandHandler("mail", mail_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_message))
    application.add_handler(MessageHandler(filters.AUDIO, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()