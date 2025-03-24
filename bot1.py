import telebot
from telebot import types
import sqlite3
from datetime import datetime
import os
import csv
from openai import OpenAI
import logging

# Настройка логирования для отладки
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Инициализация OpenAI
client = OpenAI(
    api_key='sk-k5lFTaLbtMHtLjCINnkDRXiMpRumJkb0',  # Замените на ваш ключ
    base_url="https://api.proxyapi.ru/openai/v1",
)

# Инициализация бота
bot = telebot.TeleBot('7754190602:AAFvBqgVIikoskm_Xa5WVUBnw9KNwVY-Jqk')  # Замените на ваш токен
ADMIN_IDS = [1200223081]  # Список ID администраторов

# Глобальный словарь для хранения данных заказа
order_data = {}

# Инициализация базы данных
def init_db():
    try:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()

        # Таблица пользователей
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY, username TEXT, reg_date TEXT, orders_count INTEGER DEFAULT 0)''')

        # Таблица категорий
        c.execute('''CREATE TABLE IF NOT EXISTS categories
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)''')

        # Таблица товаров
        c.execute('''CREATE TABLE IF NOT EXISTS products
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, name TEXT, description TEXT, photo TEXT,
                      FOREIGN KEY (category_id) REFERENCES categories (id))''')

        # Таблица приветственных сообщений
        c.execute('''CREATE TABLE IF NOT EXISTS welcome_message
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, message_text TEXT, photo_path TEXT)''')

        # Таблица вопросов
        c.execute('''CREATE TABLE IF NOT EXISTS questions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, question_text TEXT,
                      question_type TEXT, file_id TEXT, timestamp TEXT, status TEXT DEFAULT 'pending')''')

        # Таблица заказов
        c.execute('''CREATE TABLE IF NOT EXISTS orders
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, product_id INTEGER,
                      product_name TEXT, quantity INTEGER, address TEXT, status TEXT DEFAULT 'pending', timestamp TEXT)''')

        # Добавление приветственного сообщения по умолчанию
        c.execute("INSERT OR IGNORE INTO welcome_message (message_text, photo_path) VALUES (?, ?)",
                  ("Добро пожаловать в наш магазин!", "default_welcome.jpg"))

        conn.commit()
        logging.info("База данных успешно инициализирована")
    except Exception as e:
        logging.error(f"Ошибка при инициализации базы данных: {e}")
    finally:
        conn.close()

# Получение ответа от ИИ
def get_ai_response(prompt):
    try:
        with open("knowledge_base.txt", "r", encoding="utf-8") as f:
            knowledge_base = f.read()
    except FileNotFoundError:
        knowledge_base = "Информация о магазине недоступна."

    system_prompt = (
        "Ты полезный ассистент интернет-магазина. Отвечай вежливо и профессионально.\n"
        f"База знаний:\n{knowledge_base}"
    )

    try:
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
        logging.error(f"Ошибка при запросе к OpenAI: {e}")
        return "Извините, возникла ошибка при обработке вашего запроса."

# Главное меню
def main_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Задать вопрос", "Выбрать товар")
    bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    chat_id = message.chat.id

    try:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, username, reg_date, orders_count) VALUES (?, ?, ?, ?)",
                  (user_id, username, datetime.now().strftime("%Y-%m-%d"), 0))
        
        c.execute("SELECT message_text, photo_path FROM welcome_message ORDER BY id DESC LIMIT 1")
        welcome_text, photo_path = c.fetchone()
        conn.commit()
    except Exception as e:
        logging.error(f"Ошибка при работе с базой данных в /start: {e}")
        bot.send_message(chat_id, "Произошла ошибка. Попробуйте позже.")
        return
    finally:
        conn.close()

    inline_markup = types.InlineKeyboardMarkup()
    inline_markup.add(types.InlineKeyboardButton("Открыть веб-магазин", url="YOUR_SHOP_URL"))

    if os.path.exists(photo_path):
        try:
            with open(photo_path, 'rb') as photo:
                bot.send_message(chat_id, welcome_text, reply_markup=inline_markup)
                bot.send_photo(chat_id, photo)
        except Exception as e:
            logging.error(f"Ошибка при отправке фото: {e}")
            bot.send_message(chat_id, welcome_text, reply_markup=inline_markup)
    else:
        bot.send_message(chat_id, welcome_text + "\n(Фото недоступно)", reply_markup=inline_markup)

    main_menu(chat_id)

# Обработчик команды /admin
@bot.message_handler(commands=['admin'])
def handle_admin(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "У вас нет доступа к админ-панели.")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📊 Выгрузка пользователей", "🏪 Управление магазином",
               "📨 Рассылка", "💬 Ответить на вопрос", "📦 Управление заказами")
    bot.send_message(message.chat.id, "Панель администратора:", reply_markup=markup)

# Обработка вопросов (исправлено: без повторных запросов)
@bot.message_handler(func=lambda message: message.text == "Задать вопрос")
def handle_question_start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Общий вопрос", "Вопрос по товару", "Отмена")
    msg = bot.send_message(message.chat.id, "Выберите тип вопроса:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_question_type)

def process_question_type(message):
    if message.text == "Отмена":
        main_menu(message.chat.id)
        return

    question_type = message.text
    msg = bot.send_message(message.chat.id, "Опишите ваш вопрос:")
    bot.register_next_step_handler(msg, lambda m: process_question_content(m, question_type))

def process_question_content(message, question_type):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    question_text = message.text
    chat_id = message.chat.id

    try:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("INSERT INTO questions (user_id, username, question_text, question_type, timestamp) VALUES (?, ?, ?, ?, ?)",
                  (user_id, username, question_text, question_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except Exception as e:
        logging.error(f"Ошибка при сохранении вопроса: {e}")
        bot.send_message(chat_id, "Ошибка при сохранении вопроса.")
        return
    finally:
        conn.close()

    ai_response = get_ai_response(question_text)
    bot.send_message(chat_id, ai_response)

    for admin_id in ADMIN_IDS:
        bot.send_message(admin_id, f"Новый вопрос от @{username} (ID: {user_id}) [{question_type}]:\n{question_text}\n\nОтвет ИИ: {ai_response}")

    main_menu(chat_id)

# Выбор товара
@bot.message_handler(func=lambda message: message.text == "Выбрать товар")
def handle_show_categories(message):
    try:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("SELECT id, name FROM categories")
        categories = c.fetchall()
    except Exception as e:
        logging.error(f"Ошибка при получении категорий: {e}")
        bot.send_message(message.chat.id, "Ошибка при загрузке категорий.")
        return
    finally:
        conn.close()

    if not categories:
        bot.send_message(message.chat.id, "Категорий пока нет.")
        return

    markup = types.InlineKeyboardMarkup()
    for cat_id, cat_name in categories:
        markup.add(types.InlineKeyboardButton(cat_name, callback_data=f"cat_{cat_id}"))
    bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=markup)

# Обработка callback-запросов
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        if call.data.startswith("cat_"):
            category_id = int(call.data.split("_")[1])
            conn = sqlite3.connect('shop.db')
            c = conn.cursor()
            c.execute("SELECT id, name, description, photo FROM products WHERE category_id = ?", (category_id,))
            products = c.fetchall()
            conn.close()

            if not products:
                bot.send_message(call.message.chat.id, "Товаров в этой категории нет.")
                return

            product_id, name, desc, photo = products[0]
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Заказать", callback_data=f"order_{product_id}"))
            with open(photo, 'rb') as p:
                bot.send_photo(call.message.chat.id, p, caption=f"{name}\n{desc}", reply_markup=markup)
        elif call.data.startswith("order_"):
            handle_order_start(call)
    except Exception as e:
        logging.error(f"Ошибка в callback: {e}")
        bot.send_message(call.message.chat.id, "Произошла ошибка.")

# Обработка заказа через ИИ
def handle_order_start(call):
    product_id = int(call.data.split("_")[1])
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    # Сохраняем начальные данные
    order_data[user_id] = {"product_id": product_id, "step": "ask_product_details"}

    # Получаем название товара
    try:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("SELECT name FROM products WHERE id = ?", (product_id,))
        product_name = c.fetchone()[0]
        order_data[user_id]["product_name"] = product_name
    except Exception as e:
        logging.error(f"Ошибка при получении товара: {e}")
        bot.send_message(chat_id, "Ошибка при обработке заказа.")
        return
    finally:
        conn.close()

    # ИИ спрашивает количество
    ai_prompt = f"Пользователь хочет заказать '{product_name}'. Спроси, сколько единиц товара ему нужно."
    ai_response = get_ai_response(ai_prompt)
    msg = bot.send_message(chat_id, ai_response)
    bot.register_next_step_handler(msg, process_product_quantity)

def process_product_quantity(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_id not in order_data or order_data[user_id]["step"] != "ask_product_details":
        bot.send_message(chat_id, "Ошибка в процессе заказа. Начните заново.")
        return

    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            raise ValueError("Количество должно быть положительным.")
        order_data[user_id]["quantity"] = quantity
        order_data[user_id]["step"] = "ask_delivery_details"
    except ValueError:
        bot.send_message(chat_id, "Укажите корректное число.")
        bot.register_next_step_handler(message, process_product_quantity)
        return

    # ИИ уточняет адрес
    ai_prompt = f"Пользователь заказал {order_data[user_id]['quantity']} шт. '{order_data[user_id]['product_name']}'. Уточни адрес доставки."
    ai_response = get_ai_response(ai_prompt)
    msg = bot.send_message(chat_id, ai_response)
    bot.register_next_step_handler(msg, process_delivery_address)

def process_delivery_address(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_id not in order_data or order_data[user_id]["step"] != "ask_delivery_details":
        bot.send_message(chat_id, "Ошибка в процессе заказа. Начните заново.")
        return

    order_data[user_id]["address"] = message.text.strip()
    order_data[user_id]["step"] = "confirm_order"

    # ИИ формирует подтверждение
    order_summary = (
        f"Ваш заказ:\n"
        f"Товар: {order_data[user_id]['product_name']}\n"
        f"Количество: {order_data[user_id]['quantity']} шт.\n"
        f"Адрес: {order_data[user_id]['address']}\n"
        f"Сумма: {order_data[user_id]['quantity'] * 100} руб."
    )
    ai_prompt = f"Данные заказа:\n{order_summary}\nСпроси, всё ли верно."
    ai_response = get_ai_response(ai_prompt)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Да", "Нет")
    msg = bot.send_message(chat_id, ai_response, reply_markup=markup)
    bot.register_next_step_handler(msg, process_order_confirmation)

def process_order_confirmation(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_id not in order_data or order_data[user_id]["step"] != "confirm_order":
        bot.send_message(chat_id, "Ошибка в процессе заказа. Начните заново.")
        return

    if message.text.lower() == "да":
        try:
            conn = sqlite3.connect('shop.db')
            c = conn.cursor()
            c.execute(
                "INSERT INTO orders (user_id, username, product_id, product_name, quantity, address, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, message.from_user.username or "Unknown", order_data[user_id]["product_id"],
                 order_data[user_id]["product_name"], order_data[user_id]["quantity"], order_data[user_id]["address"],
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            order_id = c.lastrowid
            c.execute("UPDATE users SET orders_count = orders_count + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
        except Exception as e:
            logging.error(f"Ошибка при сохранении заказа: {e}")
            bot.send_message(chat_id, "Ошибка при сохранении заказа.")
            return
        finally:
            conn.close()

        order_summary = (
            f"Новый заказ #{order_id}\n"
            f"От: @{message.from_user.username or 'Unknown'} (ID: {user_id})\n"
            f"Товар: {order_data[user_id]['product_name']}\n"
            f"Количество: {order_data[user_id]['quantity']} шт.\n"
            f"Адрес: {order_data[user_id]['address']}"
        )
        for admin_id in ADMIN_IDS:
            bot.send_message(admin_id, order_summary)

        ai_prompt = "Заказ подтверждён. Предоставь реквизиты для оплаты."
        ai_response = get_ai_response(ai_prompt)
        bot.send_message(chat_id, ai_response)
        order_data[user_id]["step"] = "awaiting_payment"
        order_data[user_id]["order_id"] = order_id

    elif message.text.lower() == "нет":
        bot.send_message(chat_id, "Заказ отменён. Начните заново.")
        del order_data[user_id]
    else:
        bot.send_message(chat_id, "Выберите 'Да' или 'Нет'.")
        bot.register_next_step_handler(message, process_order_confirmation)

    main_menu(chat_id)

# Обработка оплаты
@bot.message_handler(func=lambda message: "оплатил" in message.text.lower())
def process_payment_confirmation(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_id not in order_data or order_data[user_id]["step"] != "awaiting_payment":
        bot.send_message(chat_id, "Нет активного заказа для оплаты.")
        return

    ai_prompt = "Пользователь сообщил, что оплатил. Подтверди и уведомь админа."
    ai_response = get_ai_response(ai_prompt)
    bot.send_message(chat_id, ai_response)

    order_id = order_data[user_id]["order_id"]
    for admin_id in ADMIN_IDS:
        bot.send_message(admin_id, f"@{message.from_user.username or 'Unknown'} (ID: {user_id}) оплатил заказ #{order_id}.")

    try:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("UPDATE orders SET status = 'awaiting_confirmation' WHERE id = ?", (order_id,))
        conn.commit()
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса: {e}")
    finally:
        conn.close()

    del order_data[user_id]
    main_menu(chat_id)

# Запуск бота
if __name__ == "__main__":
    logging.info("Запуск бота...")
    init_db()
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logging.error(f"Ошибка в polling: {e}")
