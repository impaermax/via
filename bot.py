import telebot
from telebot import types
import sqlite3
from datetime import datetime
import os

# Инициализация бота
bot = telebot.TeleBot('7754190602:AAFvBqgVIikoskm_Xa5WVUBnw9KNwVY-Jqk')
banner_photo = None  # Глобальная переменная для хранения ID фото баннера

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    
    # Создание таблиц
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
    
    # Добавляем дефолтное приветственное сообщение если таблица пустая
    c.execute("SELECT COUNT(*) FROM welcome_message")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO welcome_message (message_text, photo_path) VALUES (?, ?)", 
                 ("Добро пожаловать в наш магазин!", "default_welcome.jpg"))
    
    conn.commit()
    conn.close()

init_db()

# Админские ID
ADMIN_IDS = [1200223081]  # Замените на реальные ID администраторов

# Стартовое сообщение
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Регистрация пользователя
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, reg_date, orders_count) VALUES (?, ?, ?, ?)",
              (user_id, username, datetime.now().strftime("%Y-%m-%d"), 0))
    
    # Получаем приветственное сообщение
    c.execute("SELECT message_text, photo_path FROM welcome_message ORDER BY id DESC LIMIT 1")
    welcome_data = c.fetchone()
    welcome_text = welcome_data[0]
    photo_path = welcome_data[1]
    
    conn.commit()
    conn.close()
    
    # Создание клавиатуры
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("Задать вопрос")
    btn2 = types.KeyboardButton("Выбрать товар")
    markup.add(btn1, btn2)
    
    # Инлайн кнопка для веб-магазина
    inline_markup = types.InlineKeyboardMarkup()
    web_btn = types.InlineKeyboardButton("Открыть веб магазин", url='YOUR_SHOP_URL')
    inline_markup.add(web_btn)
    
    # Отправка приветственного сообщения
    if os.path.exists(photo_path):
        bot.send_photo(message.chat.id, 
                      open(photo_path, 'rb'),
                      caption=welcome_text,
                      reply_markup=markup)
    else:
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup)
        
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=inline_markup)

# Обработка кнопки "Задать вопрос"
@bot.message_handler(func=lambda message: message.text == "Задать вопрос")
def ask_question(message):
    msg = bot.send_message(message.chat.id, "Отправьте ваш вопрос текстом или прикрепите файл/фото")
    bot.register_next_step_handler(msg, process_question)

def process_question(message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Отправка вопроса администратору
    for admin_id in ADMIN_IDS:
        if message.content_type == 'text':
            bot.send_message(admin_id, 
                           f"Вопрос от @{username} (ID: {user_id}):\n\n{message.text}")
        elif message.content_type in ['photo', 'document']:
            if message.content_type == 'photo':
                file_id = message.photo[-1].file_id
                bot.send_photo(admin_id, file_id,
                             caption=f"Вопрос от @{username} (ID: {user_id})")
            else:
                file_id = message.document.file_id
                bot.send_document(admin_id, file_id,
                                caption=f"Вопрос от @{username} (ID: {user_id})")
    
    bot.send_message(message.chat.id, "Ваш вопрос отправлен администратору!")

# Обработка кнопки "Выбрать товар"
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

# Обработка выбора категории и навигации по товарам
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith('cat_'):
        category_id = int(call.data.split('_')[1])
        show_product(call.message, category_id, 0)
    elif call.data == 'next':
        category_id, current_pos = map(int, call.data.split('_')[1:])
        show_product(call.message, category_id, current_pos + 1)
    elif call.data == 'prev':
        category_id, current_pos = map(int, call.data.split('_')[1:])
        show_product(call.message, category_id, current_pos - 1)
    elif call.data.startswith('order_'):
        product_id = int(call.data.split('_')[1])
        process_order(call.message, product_id)
    elif call.data == "edit_welcome":
        edit_welcome_message(call.message)

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
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn1 = types.KeyboardButton("📊 Выгрузка базы пользователей")
        btn2 = types.KeyboardButton("🏪 Управление магазином")
        btn3 = types.KeyboardButton("📨 Рассылка")
        markup.add(btn1, btn2, btn3)
        bot.send_message(message.chat.id, "Панель администратора:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "📊 Выгрузка базы пользователей")
def export_users(message):
    if message.from_user.id in ADMIN_IDS:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users")
        users = c.fetchall()
        conn.close()
        
        report = "ID | Username | Дата регистрации | Количество заказов\n"
        for user in users:
            report += f"{user[0]} | {user[1]} | {user[2]} | {user[3]}\n"
        
        with open('users_report.txt', 'w') as f:
            f.write(report)
        
        bot.send_document(message.chat.id, open('users_report.txt', 'rb'))
        os.remove('users_report.txt')

@bot.message_handler(func=lambda message: message.text == "🏪 Управление магазином")
def manage_shop(message):
    if message.from_user.id in ADMIN_IDS:
        markup = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Добавить категорию", callback_data="add_category")
        btn2 = types.InlineKeyboardButton("Удалить категорию", callback_data="del_category")
        btn3 = types.InlineKeyboardButton("Добавить товар", callback_data="add_product")
        btn4 = types.InlineKeyboardButton("Удалить товар", callback_data="del_product")
        btn5 = types.InlineKeyboardButton("Редактировать приветствие", callback_data="edit_welcome")
        markup.add(btn1, btn2, btn3, btn4, btn5)
        bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

def edit_welcome_message(message):
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
            except:
                continue
        
        bot.send_message(message.chat.id, "Рассылка выполнена!")

# Запуск бота
bot.polling(none_stop=True)
