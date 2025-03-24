import telebot
from telebot import types
import sqlite3
from datetime import datetime
import os
import csv
from openai import OpenAI


client = OpenAI(
    api_key='sk-k5lFTaLbtMHtLjCINnkDRXiMpRumJkb0',
    base_url="https://api.proxyapi.ru/openai/v1",
)

# Инициализация бота
bot = telebot.TeleBot('7754190602:AAFvBqgVIikoskm_Xa5WVUBnw9KNwVY-Jqk')

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, username TEXT, reg_date TEXT, orders_count INTEGER)''')

    c.execute('''CREATE TABLE IF NOT EXISTS categories
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  category_id INTEGER,
                  name TEXT,
                  description TEXT,
                  photo TEXT,
                  FOREIGN KEY (category_id) REFERENCES categories (id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS welcome_message
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  message_text TEXT,
                  photo_path TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS questions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  username TEXT,
                  question_text TEXT,
                  question_type TEXT,
                  file_id TEXT,
                  timestamp TEXT,
                  status TEXT DEFAULT 'pending')''')

    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  username TEXT,
                  product_id INTEGER,
                  product_name TEXT,
                  quantity INTEGER,
                  address TEXT,
                  status TEXT DEFAULT 'pending',
                  timestamp TEXT)''')

    c.execute("SELECT COUNT(*) FROM welcome_message")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO welcome_message (message_text, photo_path) VALUES (?, ?)", 
                 ("Добро пожаловать в наш магазин!", "default_welcome.jpg"))

    conn.commit()
    conn.close()

init_db()

# Админские ID
ADMIN_IDS = [1200223081]

# Стартовое сообщение
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username

    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, reg_date, orders_count) VALUES (?, ?, ?, ?)",
              (user_id, username, datetime.now().strftime("%Y-%m-%d"), 0))

    c.execute("SELECT message_text, photo_path FROM welcome_message ORDER BY id DESC LIMIT 1")
    welcome_data = c.fetchone()
    welcome_text = welcome_data[0]
    photo_path = welcome_data[1]

    conn.commit()
    conn.close()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("Задать вопрос")
    btn2 = types.KeyboardButton("Выбрать товар")
    markup.add(btn1, btn2)

    inline_markup = types.InlineKeyboardMarkup()
    web_btn = types.InlineKeyboardButton("Открыть веб магазин", url='YOUR_SHOP_URL')
    inline_markup.add(web_btn)

    if os.path.exists(photo_path):
        bot.send_photo(message.chat.id, 
                      open(photo_path, 'rb'),
                      caption=welcome_text,
                      reply_markup=markup)
    else:
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=inline_markup)

# Обработка вопроса
@bot.message_handler(func=lambda message: message.text == "Задать вопрос")
def ask_question(message):
    msg = bot.send_message(message.chat.id, "Отправьте ваш вопрос текстом или прикрепите файл/фото")
    bot.register_next_step_handler(msg, process_question)

def process_question(message):
    user_id = message.from_user.id
    username = message.from_user.username

    conn = sqlite3.connect('shop.db')
    c = conn.cursor()

    if message.content_type == 'text':
        content_type = 'text'
        file_id = None
        content = message.text
    elif message.content_type == 'photo':
        content_type = 'photo'
        file_id = message.photo[-1].file_id
        content = message.caption or ''
    elif message.content_type == 'document':
        content_type = 'document'
        file_id = message.document.file_id
        content = message.caption or ''
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте текст, фото или документ.")
        return

    c.execute("INSERT INTO questions (user_id, username, question_text, question_type, file_id, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
             (user_id, username, content, content_type, file_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()

    for admin_id in ADMIN_IDS:
        if content_type == 'text':
            bot.send_message(admin_id, f"Новый вопрос от @{username} (ID: {user_id}):\n\n{content}")
        elif content_type == 'photo':
            bot.send_photo(admin_id, file_id, caption=f"Новый вопрос от @{username} (ID: {user_id}):\n\n{content}")
        elif content_type == 'document':
            bot.send_document(admin_id, file_id, caption=f"Новый вопрос от @{username} (ID: {user_id}):\n\n{content}")

# Обработка выбора товара
@bot.message_handler(func=lambda message: message.text == "Выбрать товар")
def show_categories(message):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT * FROM categories")
    categories = c.fetchall()
    conn.close()

    markup = types.InlineKeyboardMarkup()
    for category in categories:
        btn = types.InlineKeyboardButton(category[1], callback_data=f"cat_{category[0]}")
        markup.add(btn)

    bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=markup)

# Админская панель
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id in ADMIN_IDS:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        btn1 = types.KeyboardButton("📊 Выгрузка пользователей")
        btn2 = types.KeyboardButton("🏪 Управление магазином")
        btn3 = types.KeyboardButton("📨 Рассылка")
        btn4 = types.KeyboardButton("💬 Ответить пользователю")
        btn5 = types.KeyboardButton("📦 Управление заказами")
        markup.add(btn1, btn2, btn3, btn4, btn5)
        bot.send_message(message.chat.id, "Панель администратора:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "📊 Выгрузка пользователей")
def export_users(message):
    if message.from_user.id in ADMIN_IDS:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users")
        users = c.fetchall()
        conn.close()

        csv_filename = 'users_report.csv'
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'Username', 'Дата регистрации', 'Количество заказов'])
            for user in users:
                writer.writerow([user[0], user[1], user[2], user[3]])

        with open(csv_filename, 'rb') as f:
            bot.send_document(message.chat.id, f, caption="Выгрузка базы пользователей")
        os.remove(csv_filename)

@bot.message_handler(func=lambda message: message.text == "🏪 Управление магазином")
def manage_shop(message):
    if message.from_user.id in ADMIN_IDS:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        btn1 = types.KeyboardButton("➕ Добавить категорию")
        btn2 = types.KeyboardButton("➖ Удалить категорию")
        btn3 = types.KeyboardButton("➕ Добавить товар")
        btn4 = types.KeyboardButton("➖ Удалить товар")
        btn5 = types.KeyboardButton("✏️ Редактировать приветствие")
        btn6 = types.KeyboardButton("🔙 Назад")
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
        bot.send_message(message.chat.id, "Управление магазином:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "➕ Добавить категорию")
def add_category(message):
    if message.from_user.id in ADMIN_IDS:
        msg = bot.send_message(message.chat.id, "Введите название новой категории:")
        bot.register_next_step_handler(msg, save_category)

def save_category(message):
    if message.from_user.id in ADMIN_IDS:
        category_name = message.text
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("INSERT INTO categories (name) VALUES (?)", (category_name,))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"Категория '{category_name}' добавлена!")
        manage_shop(message)

@bot.message_handler(func=lambda message: message.text == "➖ Удалить категорию")
def delete_category(message):
    if message.from_user.id in ADMIN_IDS:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("SELECT * FROM categories")
        categories = c.fetchall()
        conn.close()

        if not categories:
            bot.send_message(message.chat.id, "Нет категорий для удаления!")
            manage_shop(message)
            return

        markup = types.InlineKeyboardMarkup()
        for category in categories:
            markup.add(types.InlineKeyboardButton(category[1], callback_data=f"del_cat_{category[0]}"))
        bot.send_message(message.chat.id, "Выберите категорию для удаления:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "➕ Добавить товар")
def add_product_start(message):
    if message.from_user.id in ADMIN_IDS:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("SELECT * FROM categories")
        categories = c.fetchall()
        conn.close()

        if not categories:
            bot.send_message(message.chat.id, "Сначала добавьте хотя бы одну категорию!")
            manage_shop(message)
            return

        markup = types.InlineKeyboardMarkup()
        for category in categories:
            markup.add(types.InlineKeyboardButton(category[1], callback_data=f"prod_cat_{category[0]}"))
        bot.send_message(message.chat.id, "Выберите категорию для нового товара:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "➖ Удалить товар")
def delete_product_start(message):
    if message.from_user.id in ADMIN_IDS:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("SELECT * FROM categories")
        categories = c.fetchall()
        conn.close()

        if not categories:
            bot.send_message(message.chat.id, "Нет категорий с товарами!")
            manage_shop(message)
            return

        markup = types.InlineKeyboardMarkup()
        for category in categories:
            markup.add(types.InlineKeyboardButton(category[1], callback_data=f"del_prod_cat_{category[0]}"))
        bot.send_message(message.chat.id, "Выберите категорию для удаления товара:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "✏️ Редактировать приветствие")
def edit_welcome_message(message):
    if message.from_user.id in ADMIN_IDS:
        msg = bot.send_message(message.chat.id, "Отправьте новый текст приветственного сообщения и фото (если нужно)")
        bot.register_next_step_handler(msg, save_welcome_message)

def save_welcome_message(message):
    if message.from_user.id in ADMIN_IDS:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()

        if message.content_type == 'photo':
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            photo_path = f'welcome_photos/welcome_{datetime.now().strftime("%Y%m%d_%H%M%S")}.jpg'
            os.makedirs('welcome_photos', exist_ok=True)
            with open(photo_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            c.execute("INSERT INTO welcome_message (message_text, photo_path) VALUES (?, ?)",
                     (message.caption or "Добро пожаловать в наш магазин!", photo_path))
        else:
            c.execute("INSERT INTO welcome_message (message_text, photo_path) VALUES (?, ?)",
                     (message.text, "default_welcome.jpg"))

        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, "Приветственное сообщение обновлено!")
        manage_shop(message)

@bot.message_handler(func=lambda message: message.text == "📨 Рассылка")
def broadcast_message(message):
    if message.from_user.id in ADMIN_IDS:
        msg = bot.send_message(message.chat.id, "Отправьте сообщение для рассылки (текст или фото)")
        bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    if message.from_user.id in ADMIN_IDS:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = c.fetchall()
        conn.close()

        for user in users:
            try:
                if message.content_type == 'text':
                    bot.send_message(user[0], message.text)
                elif message.content_type == 'photo':
                    bot.send_photo(user[0], message.photo[-1].file_id, caption=message.caption)
            except Exception as e:
                print(f"Ошибка при отправке пользователю {user[0]}: {e}")
                continue

        bot.send_message(message.chat.id, "Рассылка выполнена!")
        admin_panel(message)

@bot.message_handler(func=lambda message: message.text == "💬 Ответить пользователю")
def show_pending_questions(message):
    if message.from_user.id in ADMIN_IDS:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("SELECT * FROM questions WHERE status = 'pending'")
        questions = c.fetchall()
        conn.close()

        if not questions:
            bot.send_message(message.chat.id, "Нет неотвеченных вопросов!")
            admin_panel(message)
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for q in questions:
            btn_text = f"@{q[2]} ({q[6][:16]})"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"reply_to_{q[0]}"))
        bot.send_message(message.chat.id, "Неотвеченные вопросы:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "📦 Управление заказами")
def manage_orders(message):
    if message.from_user.id in ADMIN_IDS:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("SELECT * FROM orders WHERE status = 'pending'")
        orders = c.fetchall()
        conn.close()

        if not orders:
            bot.send_message(message.chat.id, "Нет активных заказов!")
            admin_panel(message)
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for order in orders:
            btn_text = f"Заказ #{order[0]} - @{order[2]} - {order[4]} ({order[5]} шт.)"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"manage_order_{order[0]}"))
        bot.send_message(message.chat.id, "Активные заказы:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🔙 Назад")
def back_to_admin_panel(message):
    if message.from_user.id in ADMIN_IDS:
        admin_panel(message)

# Обработка callback-запросов
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    print(f"Callback received: {call.data}")  # Отладочный вывод
    try:
        if call.data.startswith('cat_'):
            category_id = int(call.data.split('_')[1])
            show_product(call.message, category_id, 0)
        elif call.data.startswith('next_'):
            category_id, current_pos = map(int, call.data.split('_')[1:])
            show_product(call.message, category_id, current_pos + 1)
        elif call.data.startswith('prev_'):
            category_id, current_pos = map(int, call.data.split('_')[1:])
            show_product(call.message, category_id, current_pos - 1)
        elif call.data.startswith('order_'):
            parts = call.data.split('_')
            if len(parts) == 2:  # Начало заказа: order_{product_id}
                product_id = int(parts[1])
                start_order(call, product_id)
            elif parts[1] == 'qty':  # Выбор количества: order_qty_{product_id}_{quantity}
                product_id, quantity = map(int, parts[2:])
                confirm_order_quantity(call.message, product_id, quantity)
            elif parts[1] == 'confirm':  # Подтверждение заказа: order_confirm_{product_id}_{quantity}
                product_id, quantity = map(int, parts[2:])
                request_delivery_address(call.message, product_id, quantity)
        elif call.data.startswith('manage_order_'):
            order_id = int(call.data.split('_')[2])
            show_order_details(call.message, order_id)
        elif call.data.startswith('pay_'):
            order_id = int(call.data.split('_')[1])
            send_payment_details(call.message, order_id)
        elif call.data.startswith('prod_cat_'):
            category_id = int(call.data.split('_')[2])
            msg = bot.send_message(call.message.chat.id, 
                                 "Отправьте данные о товаре в формате:\nНазвание\nОписание\nФото")
            bot.register_next_step_handler(msg, lambda m: save_product(m, category_id))
        elif call.data.startswith('del_cat_'):
            category_id = int(call.data.split('_')[2])
            delete_category_confirm(call.message, category_id)
        elif call.data.startswith('del_prod_cat_'):
            category_id = int(call.data.split('_')[2])
            show_products_for_deletion(call.message, category_id)
        elif call.data.startswith('del_prod_'):
            product_id = int(call.data.split('_')[2])
            delete_product_confirm(call.message, product_id)
        elif call.data.startswith('reply_to_'):
            question_id = int(call.data.split('_')[2])
            start_reply_process(call.message, question_id)
    except Exception as e:
        print(f"Ошибка в callback_handler: {e}")
        bot.send_message(call.message.chat.id, "Произошла ошибка, попробуйте позже.")

def show_product(message, category_id, position):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE category_id = ?", (category_id,))
    products = c.fetchall()
    conn.close()

    if not products:
        bot.edit_message_text("В данной категории пока нет товаров",
                            message.chat.id,
                            message.message_id)
        return

    if position < 0:
        position = len(products) - 1
    elif position >= len(products):
        position = 0

    product = products[position]

    markup = types.InlineKeyboardMarkup(row_width=3)
    prev_btn = types.InlineKeyboardButton("◀️", callback_data=f"prev_{category_id}_{position}")
    order_btn = types.InlineKeyboardButton(f"Заказать ({product[2]})", callback_data=f"order_{product[0]}")
    next_btn = types.InlineKeyboardButton("▶️", callback_data=f"next_{category_id}_{position}")
    markup.add(prev_btn, order_btn, next_btn)

    with open(product[4], 'rb') as photo:
        bot.edit_message_media(
            media=types.InputMediaPhoto(photo, caption=f"{product[2]}\n\n{product[3]}"),
            chat_id=message.chat.id,
            message_id=message.message_id,
            reply_markup=markup
        )

def save_product(message, category_id):
    if message.from_user.id in ADMIN_IDS:
        if message.content_type != 'photo':
            bot.send_message(message.chat.id, "Необходимо отправить фото товара!")
            return

        name, description = message.caption.split('\n', 1) if '\n' in message.caption else (message.caption, '')

        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        photo_path = f'products/product_{datetime.now().strftime("%Y%m%d_%H%M%S")}.jpg'

        os.makedirs('products', exist_ok=True)
        with open(photo_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("INSERT INTO products (category_id, name, description, photo) VALUES (?, ?, ?, ?)",
                 (category_id, name, description, photo_path))
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, f"Товар '{name}' добавлен в категорию!")
        manage_shop(message)

def delete_category_confirm(message, category_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
    category_name = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM products WHERE category_id = ?", (category_id,))
    products_count = c.fetchone()[0]
    conn.close()

    if products_count > 0:
        bot.send_message(message.chat.id, f"Нельзя удалить категорию '{category_name}', так как в ней есть товары ({products_count})!")
        manage_shop(message)
        return

    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()

    bot.send_message(message.chat.id, f"Категория '{category_name}' удалена!")
    manage_shop(message)

def show_products_for_deletion(message, category_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE category_id = ?", (category_id,))
    products = c.fetchall()
    conn.close()

    if not products:
        bot.send_message(message.chat.id, "В этой категории нет товаров!")
        manage_shop(message)
        return

    markup = types.InlineKeyboardMarkup()
    for product in products:
        markup.add(types.InlineKeyboardButton(product[2], callback_data=f"del_prod_{product[0]}"))
    bot.send_message(message.chat.id, "Выберите товар для удаления:", reply_markup=markup)

def delete_product_confirm(message, product_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT name, photo FROM products WHERE id = ?", (product_id,))
    product = c.fetchone()
    c.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

    if os.path.exists(product[1]):
        os.remove(product[1])

    bot.send_message(message.chat.id, f"Товар '{product[0]}' удален!")
    manage_shop(message)

def start_reply_process(message, question_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
    question = c.fetchone()
    conn.close()

    if question[4] == 'text':
        bot.send_message(message.chat.id, f"Вопрос от @{question[2]} (ID: {question[1]}):\n{question[3]}\n\nНапишите ответ:")
    elif question[4] == 'photo':
        bot.send_photo(message.chat.id, question[5], 
                      caption=f"Вопрос от @{question[2]} (ID: {question[1]}):\n{question[3]}\n\nНапишите ответ:")
    elif question[4] == 'document':
        bot.send_document(message.chat.id, question[5],
                         caption=f"Вопрос от @{question[2]} (ID: {question[1]}):\n{question[3]}\n\nНапишите ответ:")

    bot.register_next_step_handler(message, lambda msg: send_reply(msg, question_id, question[1]))

def send_reply(message, question_id, user_id):
    if message.from_user.id in ADMIN_IDS:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()

        if message.content_type == 'text':
            bot.send_message(user_id, f"Ответ от администратора:\n\n{message.text}")
        elif message.content_type == 'photo':
            bot.send_photo(user_id, message.photo[-1].file_id,
                          caption=f"Ответ от администратора:\n\n{message.caption or ''}")
        elif message.content_type == 'document':
            bot.send_document(user_id, message.document.file_id,
                            caption=f"Ответ от администратора:\n\n{message.caption or ''}")

        c.execute("UPDATE questions SET status = 'answered' WHERE id = ?", (question_id,))
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, "Ответ отправлен пользователю!")
        admin_panel(message)

def start_order(call, product_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT name FROM products WHERE id = ?", (product_id,))
    product_name = c.fetchone()[0]
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=5)
    for i in range(1, 6):
        markup.add(types.InlineKeyboardButton(str(i), callback_data=f"order_qty_{product_id}_{i}"))
    bot.edit_message_text(f"Выберите количество товара '{product_name}':", 
                         chat_id=call.message.chat.id, 
                         message_id=call.message.message_id, 
                         reply_markup=markup)

def confirm_order_quantity(message, product_id, quantity):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT name FROM products WHERE id = ?", (product_id,))
    product_name = c.fetchone()[0]
    conn.close()

    markup = types.InlineKeyboardMarkup()
    confirm_btn = types.InlineKeyboardButton("Оформить заказ", callback_data=f"order_confirm_{product_id}_{quantity}")
    markup.add(confirm_btn)

    bot.edit_message_text(f"Вы выбрали '{product_name}' в количестве {quantity} шт. Подтвердите заказ:",
                         chat_id=message.chat.id, message_id=message.message_id, reply_markup=markup)

def request_delivery_address(message, product_id, quantity):
    msg = bot.send_message(message.chat.id, "Введите адрес доставки:")
    bot.register_next_step_handler(msg, lambda m: finalize_order(m, product_id, quantity))

def finalize_order(message, product_id, quantity):
    user_id = message.from_user.id
    username = message.from_user.username
    address = message.text

    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT name FROM products WHERE id = ?", (product_id,))
    product_name = c.fetchone()[0]
    c.execute("INSERT INTO orders (user_id, username, product_id, product_name, quantity, address, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
             (user_id, username, product_id, product_name, quantity, address, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    order_id = c.lastrowid
    c.execute("UPDATE users SET orders_count = orders_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    bot.send_message(message.chat.id, "Заказ успешно сформирован! Данные для оплаты сейчас отправим.")

    order_info = f"Новый заказ #{order_id}\nОт: @{username} (ID: {user_id})\nТовар: {product_name}\nКоличество: {quantity} шт.\nАдрес: {address}"
    for admin_id in ADMIN_IDS:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Отправить реквизиты", callback_data=f"pay_{order_id}"))
        bot.send_message(admin_id, order_info, reply_markup=markup)

def show_order_details(message, order_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = c.fetchone()
    conn.close()

    order_info = (f"Заказ #{order[0]}\n"
                  f"От: @{order[2]} (ID: {order[1]})\n"
                  f"Товар: {order[4]}\n"
                  f"Количество: {order[5]} шт.\n"
                  f"Адрес: {order[6]}\n"
                  f"Статус: {order[7]}\n"
                  f"Время: {order[8]}")

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Отправить реквизиты", callback_data=f"pay_{order_id}"))
    bot.edit_message_text(order_info, chat_id=message.chat.id, message_id=message.message_id, reply_markup=markup)

def send_payment_details(message, order_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
    user_id = c.fetchone()[0]
    conn.close()

    msg = bot.send_message(message.chat.id, "Отправьте реквизиты для оплаты клиенту:")
    bot.register_next_step_handler(msg, lambda m: send_payment_to_user(m, user_id, order_id))

def send_payment_to_user(message, user_id, order_id):
    if message.from_user.id in ADMIN_IDS:
        if message.content_type == 'text':
            bot.send_message(user_id, f"Реквизиты для оплаты вашего заказа #{order_id}:\n\n{message.text}")
        elif message.content_type == 'photo':
            bot.send_photo(user_id, message.photo[-1].file_id,
                          caption=f"Реквизиты для оплаты вашего заказа #{order_id}:\n\n{message.caption or ''}")

        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("UPDATE orders SET status = 'awaiting_payment' WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, "Реквизиты отправлены клиенту!")
        manage_orders(message)


# ... (оставьте весь существующий код инициализации базы данных и других функций)

# Функция для получения ответа от нейросети
def get_ai_response(prompt):
    try:
        # Добавляем контекст из базы знаний
        with open("knowledge_base.txt", "r", encoding="utf-8") as f:
            knowledge_base = f.read()
        
        system_prompt = (
            "Ты полезный ассистент интернет-магазина. Отвечай на вопросы клиентов вежливо и профессионально. "
            "Используй следующую информацию о магазине:\n\n"
            f"{knowledge_base}\n\n"
            "Если ответ не содержится в документе, отвечай на основе своих знаний."
        )
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Ошибка при запросе к нейросети: {e}")
        return "Извините, возникла ошибка при обработке вашего запроса."

# Обработка вопроса с использованием нейросети
@bot.message_handler(func=lambda message: message.text == "Задать вопрос")
def ask_question(message):
    msg = bot.send_message(message.chat.id, 
                           "Задайте ваш вопрос или выберите тип обращения:", 
                           reply_markup=get_question_type_keyboard())
    bot.register_next_step_handler(msg, process_question)

def get_question_type_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("Общий вопрос")
    btn2 = types.KeyboardButton("Вопрос по товару")
    btn3 = types.KeyboardButton("Отмена")
    markup.add(btn1, btn2, btn3)
    return markup

def process_question(message):
    if message.text == "Отмена":
        start(message)
        return
    
    question_type = message.text
    msg = bot.send_message(message.chat.id, 
                           "Пожалуйста, опишите ваш вопрос подробнее:")
    bot.register_next_step_handler(msg, lambda m: handle_question(m, question_type))

def handle_question(message, question_type):
    user_id = message.from_user.id
    username = message.from_user.username
    user_question = message.text
    
    # Получаем ответ от нейросети
    ai_response = get_ai_response(user_question)
    
    # Сохраняем вопрос в базу данных
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("INSERT INTO questions (user_id, username, question_text, question_type, timestamp) VALUES (?, ?, ?, ?, ?)",
              (user_id, username, user_question, question_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    # Отправляем ответ пользователю
    bot.send_message(message.chat.id, ai_response)
    
    # Уведомляем администраторов
    for admin_id in ADMIN_IDS:
        bot.send_message(admin_id, 
                         f"Новый вопрос от @{username} (ID: {user_id}) [{question_type}]:\n{user_question}\n\nОтвет ИИ:\n{ai_response}")

# Модифицированный процесс заказа с участием ИИ
@bot.callback_query_handler(func=lambda call: call.data.startswith('order_'))
def handle_order(call):
    parts = call.data.split('_')
    if len(parts) == 2:  # Начало заказа
        product_id = int(parts[1])
        start_order_with_ai(call, product_id)
    elif parts[1] == 'qty':  # Выбор количества
        product_id, quantity = map(int, parts[2:])
        confirm_order_quantity_with_ai(call.message, product_id, quantity)
    elif parts[1] == 'confirm':  # Подтверждение заказа
        product_id, quantity = map(int, parts[2:])
        request_delivery_address_with_ai(call.message, product_id, quantity)

def start_order_with_ai(call, product_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT name FROM products WHERE id = ?", (product_id,))
    product_name = c.fetchone()[0]
    conn.close()
    
    # Спрашиваем у ИИ как лучше уточнить детали
    ai_response = get_ai_response(f"Пользователь хочет заказать {product_name}. Как лучше уточнить количество?")
    
    markup = types.InlineKeyboardMarkup(row_width=5)
    for i in range(1, 6):
        markup.add(types.InlineKeyboardButton(str(i), callback_data=f"order_qty_{product_id}_{i}"))
    
    bot.edit_message_text(ai_response,
                          chat_id=call.message.chat.id,
                          message_id=call.message.message_id,
                          reply_markup=markup)

def confirm_order_quantity_with_ai(message, product_id, quantity):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT name FROM products WHERE id = ?", (product_id,))
    product_name = c.fetchone()[0]
    conn.close()
    
    # Спрашиваем у ИИ как лучше подтвердить заказ
    ai_response = get_ai_response(f"Пользователь выбрал {quantity} шт. товара {product_name}. Как лучше подтвердить заказ?")
    
    markup = types.InlineKeyboardMarkup()
    confirm_btn = types.InlineKeyboardButton("Оформить заказ", callback_data=f"order_confirm_{product_id}_{quantity}")
    markup.add(confirm_btn)
    
    bot.edit_message_text(ai_response,
                          chat_id=message.chat.id,
                          message_id=message.message_id,
                          reply_markup=markup)

def request_delivery_address_with_ai(message, product_id, quantity):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT name FROM products WHERE id = ?", (product_id,))
    product_name = c.fetchone()[0]
    conn.close()
    
    # Спрашиваем у ИИ как лучше запросить адрес
    ai_response = get_ai_response(f"Пользователь заказал {quantity} шт. товара {product_name}. Как лучше запросить адрес доставки?")
    
    msg = bot.send_message(message.chat.id, ai_response)
    bot.register_next_step_handler(msg, lambda m: finalize_order_with_ai(m, product_id, quantity))

def finalize_order_with_ai(message, product_id, quantity):
    user_id = message.from_user.id
    username = message.from_user.username
    address = message.text
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    
    # Получаем название товара
    c.execute("SELECT name FROM products WHERE id = ?", (product_id,))
    product_name = c.fetchone()[0]
    
    # Сохраняем заказ в базу данных
    c.execute("INSERT INTO orders (user_id, username, product_id, product_name, quantity, address, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
             (user_id, username, product_id, product_name, quantity, address, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    order_id = c.lastrowid
    
    # Обновляем счетчик заказов пользователя
    c.execute("UPDATE users SET orders_count = orders_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    # Спрашиваем у ИИ как лучше оформить подтверждение заказа
    order_summary = (
        f"Ваш заказ:\n"
        f"Товар: {product_name}\n"
        f"Количество: {quantity} шт.\n"
        f"Адрес доставки: {address}"
    )
    ai_response = get_ai_response(f"Подтверди заказ:\n{order_summary}")
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("Да")
    btn2 = types.KeyboardButton("Нет")
    markup.add(btn1, btn2)
    
    msg = bot.send_message(message.chat.id, ai_response, reply_markup=markup)
    bot.register_next_step_handler(msg, lambda m: confirm_final_order(m, order_id, order_summary))

def confirm_final_order(message, order_id, order_summary):
    if message.text.lower() == "да":
        user_id = message.from_user.id
        
        # Уведомляем администраторов
        for admin_id in ADMIN_IDS:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Отправить реквизиты", callback_data=f"pay_{order_id}"))
            bot.send_message(admin_id, f"Новый заказ #{order_id}\n{order_summary}", reply_markup=markup)
        
        # Спрашиваем у ИИ как лучше сообщить реквизиты
        payment_info = get_ai_response("Предоставь реквизиты для оплаты заказа")
        bot.send_message(message.chat.id, payment_info)
        
    else:
        bot.send_message(message.chat.id, "Заказ отменён.")

# Обработка оплаты
@bot.message_handler(func=lambda message: "оплатил" in message.text.lower())
def process_payment(message):
    user_id = message.from_user.id
    
    # Спрашиваем у ИИ как лучше подтвердить оплату
    confirmation_message = get_ai_response("Подтверди получение оплаты от клиента")
    
    # Уведомляем администраторов
    for admin_id in ADMIN_IDS:
        bot.send_message(admin_id, 
                         f"Пользователь @{message.from_user.username} (ID: {user_id}) сообщил об оплате.\n\n{confirmation_message}")
    
    bot.send_message(message.chat.id, confirmation_message)

# Основной запуск бота
if __name__ == "__main__":
    bot.polling(none_stop=True)
