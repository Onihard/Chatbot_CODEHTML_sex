from flask import Flask, render_template, request, redirect, session, url_for, jsonify, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = "put_a_strong_secret_here"  # поменяй на что-то своё в продакшн

DB_PATH = "chat_bot.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_tables():
    """Создаёт недостающие таблицы (если их нет) — не затрагивая существующие."""
    conn = get_db_connection()
    cur = conn.cursor()
    # private_messages (если нет)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS private_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER,
        receiver_id INTEGER,
        message_text TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # auth таблица для веб-логина
    cur.execute("""
    CREATE TABLE IF NOT EXISTS auth (
        auth_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        nickname TEXT UNIQUE,
        password_hash TEXT
    )
    """)
    # Если users таблицы нет (маловероятно, у тебя уже есть бот), создать минимальную структуру
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        nickname TEXT UNIQUE,
        age INTEGER,
        gender TEXT,
        bio TEXT,
        current_room TEXT
    )
    """)
    # rooms таблица — если нет, создать и добавить пару дефолтных комнат
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        room_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        description TEXT
    )
    """)
    # messages таблица
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        room_name TEXT,
        message_text TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # вставляем дефолтные комнаты, если их нет
    default_rooms = [
        ("Москва", "Чат для жителей Москвы"),
        ("Питер", "Чат для питерцев"),
        ("Знакомства", "Знакомства и общение"),
        ("О жизни", "Обсуждение всего на свете")
    ]
    cur.executemany("INSERT OR IGNORE INTO rooms (name, description) VALUES (?, ?)", default_rooms)
    conn.commit()
    conn.close()

ensure_tables()

# ------------------------
# Утилиты для работы с пользователем (веб)
# ------------------------
def get_current_nickname():
    return session.get("nickname")

def get_current_user_row():
    nick = get_current_nickname()
    if not nick:
        return None
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE nickname = ?", (nick,)).fetchone()
    conn.close()
    return user

# ------------------------
# Главная: список комнат
# ------------------------
@app.route('/')
def index():
    if 'nickname' in session:
        logged = True
        nickname = session['nickname']
    else:
        logged = False
        nickname = None

    conn = get_db_connection()
    rooms = conn.execute("SELECT name, description FROM rooms").fetchall()
    # собираем count
    rooms_with_counts = []
    for r in rooms:
        cnt = conn.execute("SELECT COUNT(*) as c FROM users WHERE current_room = ?", (r['name'],)).fetchone()['c']
        rooms_with_counts.append({'name': r['name'], 'description': r['description'], 'count': cnt})
    conn.close()
    return render_template('index.html', rooms=rooms_with_counts, logged=logged, nickname=nickname)

# ------------------------
# Join room (войти в комнату)
# ------------------------
@app.route('/join/<room_name>', methods=['POST'])
def join_room(room_name):
    if 'nickname' not in session:
        flash("Войдите, чтобы войти в комнату.")
        return redirect(url_for('login'))

    nick = session['nickname']
    conn = get_db_connection()
    # Если в таблице users нет строки для этого ника, создадим (с user_id как max+1)
    u = conn.execute("SELECT * FROM users WHERE nickname = ?", (nick,)).fetchone()
    if not u:
        # генерируем user_id как max(user_id)+1 (или 100000 если пусто)
        maxid = conn.execute("SELECT COALESCE(MAX(user_id), 100000) as m FROM users").fetchone()['m']
        new_id = maxid + 1
        conn.execute("INSERT INTO users (user_id, nickname, age, gender, bio, current_room) VALUES (?, ?, NULL, NULL, NULL, ?)",
                     (new_id, nick, room_name))
    else:
        conn.execute("UPDATE users SET current_room = ? WHERE nickname = ?", (room_name, nick))
    conn.commit()
    conn.close()
    return redirect(url_for('room', room_name=room_name))

# ------------------------
# Leave room (выйти)
# ------------------------
@app.route('/leave', methods=['POST'])
def leave_room():
    if 'nickname' not in session:
        return redirect(url_for('index'))
    nick = session['nickname']
    conn = get_db_connection()
    conn.execute("UPDATE users SET current_room = NULL WHERE nickname = ?", (nick,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

# ------------------------
# Страница комнаты
# ------------------------
@app.route('/room/<room_name>')
def room(room_name):
    conn = get_db_connection()
    messages = conn.execute(
        "SELECT users.nickname, messages.message_text, messages.timestamp "
        "FROM messages JOIN users ON messages.user_id = users.user_id "
        "WHERE room_name = ? ORDER BY timestamp ASC LIMIT 200",
        (room_name,)
    ).fetchall()
    conn.close()
    nickname = session.get('nickname')
    return render_template('room.html', room_name=room_name, messages=messages, nickname=nickname)

# JSON endpoint для автообновления
@app.route('/get_messages/<room_name>')
def get_messages(room_name):
    conn = get_db_connection()
    messages = conn.execute(
        "SELECT users.nickname as nickname, messages.message_text as text, messages.timestamp as time "
        "FROM messages JOIN users ON messages.user_id = users.user_id "
        "WHERE room_name = ? ORDER BY timestamp ASC LIMIT 200",
        (room_name,)
    ).fetchall()
    conn.close()
    out = [{'nickname': m['nickname'], 'text': m['text'], 'time': m['time']} for m in messages]
    return jsonify(out)

# ------------------------
# Отправка сообщения в комнату
# ------------------------
@app.route('/send_message/<room_name>', methods=['POST'])
def send_message(room_name):
    if 'nickname' not in session:
        flash("Нужно войти в систему, чтобы отправлять сообщения.")
        return redirect(url_for('login'))

    text = request.form.get('message', '').strip()
    if not text:
        return redirect(url_for('room', room_name=room_name))

    nick = session['nickname']
    conn = get_db_connection()
    user = conn.execute("SELECT user_id FROM users WHERE nickname = ?", (nick,)).fetchone()
    if not user:
        # створим юзера если вдруг
        maxid = conn.execute("SELECT COALESCE(MAX(user_id), 100000) as m FROM users").fetchone()['m']
        new_id = maxid + 1
        conn.execute("INSERT INTO users (user_id, nickname, age, gender, bio, current_room) VALUES (?, ?, NULL, NULL, NULL, ?)",
                     (new_id, nick, room_name))
        user_id = new_id
    else:
        user_id = user['user_id']

    conn.execute(
        "INSERT INTO messages (user_id, room_name, message_text, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, room_name, text, datetime.now())
    )
    conn.commit()
    conn.close()
    return redirect(url_for('room', room_name=room_name))

# ------------------------
# Личные сообщения — просмотр
# ------------------------
@app.route('/dm')
def dm_index():
    if 'nickname' not in session:
        return redirect(url_for('login'))
    nick = session['nickname']
    conn = get_db_connection()
    # список всех пользователей кроме текущего
    users = conn.execute("SELECT nickname FROM users WHERE nickname != ?", (nick,)).fetchall()
    conn.close()
    return render_template('dm_index.html', users=users, nickname=nick)

@app.route('/dm/<target_nick>')
def dm_view(target_nick):
    if 'nickname' not in session:
        return redirect(url_for('login'))
    nick = session['nickname']
    conn = get_db_connection()
    # Получаем id sender и receiver
    sender = conn.execute("SELECT user_id FROM users WHERE nickname = ?", (nick,)).fetchone()
    receiver = conn.execute("SELECT user_id FROM users WHERE nickname = ?", (target_nick,)).fetchone()
    # Если кого-то нет в users — показываем подсказку
    if not sender or not receiver:
        conn.close()
        flash("Один из пользователей не зарегистрирован в веб-интерфейсе (через бота/веб).")
        return redirect(url_for('dm_index'))

    sender_id = sender['user_id']
    receiver_id = receiver['user_id']

    msgs = conn.execute("""
        SELECT pm.*, us.nickname as sender_nick, ur.nickname as receiver_nick
        FROM private_messages pm
        JOIN users us ON pm.sender_id = us.user_id
        JOIN users ur ON pm.receiver_id = ur.user_id
        WHERE (pm.sender_id = ? AND pm.receiver_id = ?)
           OR (pm.sender_id = ? AND pm.receiver_id = ?)
        ORDER BY pm.timestamp DESC
        LIMIT 200
    """, (sender_id, receiver_id, receiver_id, sender_id)).fetchall()
    conn.close()
    return render_template('dm_view.html', messages=msgs, nick=nick, target=target_nick)

@app.route('/dm/send/<target_nick>', methods=['POST'])
def dm_send(target_nick):
    if 'nickname' not in session:
        return redirect(url_for('login'))
    text = request.form.get('message', '').strip()
    if not text:
        return redirect(url_for('dm_view', target_nick=target_nick))
    nick = session['nickname']
    conn = get_db_connection()
    sender = conn.execute("SELECT user_id FROM users WHERE nickname = ?", (nick,)).fetchone()
    receiver = conn.execute("SELECT user_id FROM users WHERE nickname = ?", (target_nick,)).fetchone()
    if not sender or not receiver:
        conn.close()
        flash("Пользователь у кого-то нет записи в users.")
        return redirect(url_for('dm_index'))

    conn.execute(
        "INSERT INTO private_messages (sender_id, receiver_id, message_text, timestamp) VALUES (?, ?, ?, ?)",
        (sender['user_id'], receiver['user_id'], text, datetime.now())
    )
    conn.commit()
    conn.close()
    return redirect(url_for('dm_view', target_nick=target_nick))

# ------------------------
# Просмотр входящих личных сообщений (как в боте /mail)
# ------------------------
@app.route('/mail')
def mail():
    if 'nickname' not in session:
        return redirect(url_for('login'))
    nick = session['nickname']
    conn = get_db_connection()
    user = conn.execute("SELECT user_id FROM users WHERE nickname = ?", (nick,)).fetchone()
    if not user:
        conn.close()
        flash("Ваша учётная запись не найдена.")
        return redirect(url_for('index'))
    user_id = user['user_id']
    msgs = conn.execute("""
        SELECT pm.message_text, pm.timestamp, us.nickname as sender
        FROM private_messages pm
        JOIN users us ON pm.sender_id = us.user_id
        WHERE pm.receiver_id = ?
        ORDER BY pm.timestamp DESC
    """, (user_id,)).fetchall()
    conn.close()
    return render_template('mail.html', messages=msgs)

# ------------------------
# Регистрация и логин
# ------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nickname = request.form.get('nickname').strip()
        password = request.form.get('password')
        if not nickname or not password:
            flash("Нужно указать ник и пароль.")
            return redirect(url_for('register'))

        conn = get_db_connection()
        # проверяем, есть ли ник в auth или users
        exists = conn.execute("SELECT * FROM auth WHERE nickname = ?", (nickname,)).fetchone()
        if exists:
            conn.close()
            flash("Такой ник уже занят.")
            return redirect(url_for('register'))

        # Если в users нет строки, создадим её с новым user_id
        user = conn.execute("SELECT * FROM users WHERE nickname = ?", (nickname,)).fetchone()
        if not user:
            maxid = conn.execute("SELECT COALESCE(MAX(user_id), 100000) as m FROM users").fetchone()['m']
            new_id = maxid + 1
            conn.execute("INSERT INTO users (user_id, nickname, age, gender, bio, current_room) VALUES (?, ?, NULL, NULL, NULL, NULL)",
                         (new_id, nickname))
            user_id = new_id
        else:
            user_id = user['user_id']

        pw_hash = generate_password_hash(password)
        conn.execute("INSERT INTO auth (user_id, nickname, password_hash) VALUES (?, ?, ?)",
                     (user_id, nickname, pw_hash))
        conn.commit()
        conn.close()

        session['nickname'] = nickname
        flash("Регистрация прошла успешно!")
        return redirect(url_for('index'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nickname = request.form.get('nickname').strip()
        password = request.form.get('password')
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM auth WHERE nickname = ?", (nickname,)).fetchone()
        conn.close()
        if row and check_password_hash(row['password_hash'], password):
            session['nickname'] = nickname
            flash("Вход выполнен.")
            return redirect(url_for('index'))
        else:
            flash("Неверный ник или пароль.")
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('nickname', None)
    flash("Вышли из системы.")
    return redirect(url_for('index'))

# ------------------------
# Запуск
# ------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
