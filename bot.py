import telebot
from telebot import types
import sqlite3
from datetime import datetime
import os
import csv

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

# Обработка callback-запросов
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "export_users":
        export_users(call.message)
    elif call.data == "manage_shop":
        manage_shop(call.message)
    elif call.data == "broadcast":
        broadcast_message(call.message)
    elif call.data == "reply_user":
        show_pending_questions(call.message)
    elif call.data.startswith("reply_to_"):
        question_id = int(call.data.split("_")[2])
        start_reply_process(call.message, question_id)
    elif call.data.startswith('cat_'):
        category_id = int(call.data.split('_')[1])
        show_product(call.message, category_id, 0)
    elif call.data.startswith('next'):
        category_id, current_pos = map(int, call.data.split('_')[1:])
        show_product(call.message, category_id, current_pos + 1)
    elif call.data.startswith('prev'):
        category_id, current_pos = map(int, call.data.split('_')[1:])
        show_product(call.message, category_id, current_pos - 1)
    elif call.data == "add_category":
        add_category(call.message)
    elif call.data == "add_product":
        add_product_start(call.message)

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
    order_btn = types.InlineKeyboardButton("Заказать", callback_data=f"order_{product[0]}")
    next_btn = types.InlineKeyboardButton("▶️", callback_data=f"next_{category_id}_{position}")
    markup.add(prev_btn, order_btn, next_btn)
    
    with open(product[4], 'rb') as photo:
        bot.edit_message_media(
            media=types.InputMediaPhoto(photo, caption=f"{product[2]}\n\n{product[3]}"),
            chat_id=message.chat.id,
            message_id=message.message_id,
            reply_markup=markup
        )

# Админские команды
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id in ADMIN_IDS:
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn1 = types.InlineKeyboardButton("📊 Выгрузка пользователей", callback_data="export_users")
        btn2 = types.InlineKeyboardButton("🏪 Управление магазином", callback_data="manage_shop")
        btn3 = types.InlineKeyboardButton("📨 Рассылка", callback_data="broadcast")
        btn4 = types.InlineKeyboardButton("💬 Ответить пользователю", callback_data="reply_user")
        markup.add(btn1, btn2, btn3, btn4)
        bot.send_message(message.chat.id, "Панель администратора:", reply_markup=markup)

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

def manage_shop(message):
    if message.from_user.id in ADMIN_IDS:
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("➕ Категория", callback_data="add_category")
        btn2 = types.InlineKeyboardButton("➖ Категория", callback_data="del_category")
        btn3 = types.InlineKeyboardButton("➕ Товар", callback_data="add_product")
        btn4 = types.InlineKeyboardButton("➖ Товар", callback_data="del_product")
        btn5 = types.InlineKeyboardButton("✏️ Приветствие", callback_data="edit_welcome")
        markup.add(btn1, btn2, btn3, btn4, btn5)
        bot.edit_message_text("Управление магазином:", message.chat.id, message.message_id, reply_markup=markup)

# Добавление категории
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

# Добавление товара
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

@bot.callback_query_handler(func=lambda call: call.data.startswith('prod_cat_'))
def add_product_category_selected(call):
    if call.from_user.id in ADMIN_IDS:
        category_id = int(call.data.split('_')[2])
        msg = bot.send_message(call.message.chat.id, 
                             "Отправьте данные о товаре в формате:\nНазвание\nОписание\nФото")
        bot.register_next_step_handler(msg, lambda m: save_product(m, category_id))

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

def show_pending_questions(message):
    if message.from_user.id in ADMIN_IDS:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("SELECT * FROM questions WHERE status = 'pending'")
        questions = c.fetchall()
        conn.close()
        
        if not questions:
            bot.edit_message_text("Нет неотвеченных вопросов", message.chat.id, message.message_id)
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for q in questions:
            btn_text = f"@{q[2]} ({q[6][:16]})"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"reply_to_{q[0]}"))
        
        bot.edit_message_text("Неотвеченные вопросы:", message.chat.id, message.message_id, reply_markup=markup)

def start_reply_process(message, question_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
    question = c.fetchone()
    conn.close()
    
    if question[4] == 'text':
        bot.edit_message_text(f"Вопрос от @{question[2]} (ID: {question[1]}):\n{question[3]}\n\nНапишите ответ:",
                            message.chat.id, message.message_id)
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

# Запуск бота
bot.polling(none_stop=True)
