import asyncio
import logging
import sqlite3
import random
import os
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# Config
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Admin ID ni .env dan oling
DB_NAME = "users.db"

logging.basicConfig(level=logging.INFO)

# ==================== DATABASE ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Foydalanuvchilar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            name TEXT,
            phone TEXT,
            language TEXT DEFAULT 'uz',
            registered INTEGER DEFAULT 0,
            cashback_balance INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL,
            referrals_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Keshbek tarixi jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cashback_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            percent INTEGER,
            cashback INTEGER,
            type TEXT DEFAULT 'purchase',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    # Migration: Agar ustunlar yo'q bo'lsa
    try:
        cursor.execute('SELECT referred_by FROM users LIMIT 1')
    except sqlite3.OperationalError:
        cursor.execute('ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT NULL')
        logging.info("MIGRATION: referred_by ustuni qo'shildi")
    
    try:
        cursor.execute('SELECT referrals_count FROM users LIMIT 1')
    except sqlite3.OperationalError:
        cursor.execute('ALTER TABLE users ADD COLUMN referrals_count INTEGER DEFAULT 0')
        logging.info("MIGRATION: referrals_count ustuni qo'shildi")
    
    try:
        cursor.execute('SELECT type FROM cashback_history LIMIT 1')
    except sqlite3.OperationalError:
        cursor.execute('ALTER TABLE cashback_history ADD COLUMN type TEXT DEFAULT \'purchase\'')
        logging.info("MIGRATION: type ustuni qo'shildi")
    
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_all_users():
    """Barcha foydalanuvchilarni olish (admin uchun)"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id, name, phone, cashback_balance, first_name, last_name 
        FROM users 
        WHERE registered = 1 
        ORDER BY created_at DESC
    ''')
    users = cursor.fetchall()
    conn.close()
    return users

def reset_user_data(user_id):
    """Foydalanuvchi balansini va tarixini tozalash"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # Balansni 0 ga tushirish
        cursor.execute('UPDATE users SET cashback_balance = 0 WHERE user_id = ?', (user_id,))
        
        # Tarixni tozalash
        cursor.execute('DELETE FROM cashback_history WHERE user_id = ?', (user_id,))
        
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Foydalanuvchi ma'lumotlarini tozalashda xato: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def add_bonus_to_user(user_id, percent):
    """Foydalanuvchiga foiz ko'rinishida bonus qo'shish"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # Joriy balansni olish
        cursor.execute('SELECT cashback_balance FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if not result:
            return None, 0
        
        current_balance = result[0]
        
        # Bonus miqdorini hisoblash
        bonus_amount = int(current_balance * percent / 100)
        
        if bonus_amount <= 0:
            return current_balance, 0
        
        # Yangi balans
        new_balance = current_balance + bonus_amount
        
        # Balansni yangilash
        cursor.execute('UPDATE users SET cashback_balance = ? WHERE user_id = ?', (new_balance, user_id))
        
        # Tarixga yozish (bonus sifatida)
        cursor.execute('''
            INSERT INTO cashback_history (user_id, amount, percent, cashback, type) 
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, current_balance, percent, bonus_amount, 'admin_bonus'))
        
        conn.commit()
        return new_balance, bonus_amount
        
    except Exception as e:
        logging.error(f"Bonus qo'shishda xato: {e}")
        conn.rollback()
        return None, 0
    finally:
        conn.close()

def create_user(user_id, username, first_name, last_name, referred_by=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, referred_by)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, referred_by))
    conn.commit()
    conn.close()

def update_language(user_id, language):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (language, user_id))
    conn.commit()
    conn.close()

def update_name(user_id, name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET name = ? WHERE user_id = ?', (name, user_id))
    conn.commit()
    conn.close()

def update_phone(user_id, phone):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET phone = ?, registered = 1 WHERE user_id = ?', (phone, user_id))
    conn.commit()
    conn.close()

def add_referral_bonus(user_id, amount):
    """Referral bonus qo'shish (1%)"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # Balansni yangilash
        cursor.execute('''
            UPDATE users 
            SET cashback_balance = cashback_balance + ?,
                referrals_count = referrals_count + 1
            WHERE user_id = ?
        ''', (amount, user_id))
        
        # Tarixga yozish
        cursor.execute('''
            INSERT INTO cashback_history (user_id, amount, percent, cashback, type) 
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, amount, 1, amount, 'referral'))
        
        conn.commit()
        
        # Yangi balansni qaytarish
        cursor.execute('SELECT cashback_balance FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0
        
    except Exception as e:
        logging.error(f"Referral bonus qo'shishda xato: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def add_cashback(user_id, amount, percent, cashback):
    """Keshbek qo'shish va tarixga yozish"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # Balansni yangilash
        cursor.execute('''
            UPDATE users 
            SET cashback_balance = cashback_balance + ? 
            WHERE user_id = ?
        ''', (cashback, user_id))
        
        # Tarixga qo'shish
        cursor.execute('''
            INSERT INTO cashback_history (user_id, amount, percent, cashback, type) 
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, amount, percent, cashback, 'purchase'))
        
        conn.commit()
    except Exception as e:
        logging.error(f"Keshbek qo'shishda xato: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def get_cashback_balance(user_id):
    """Joriy keshbek balansini olish"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT cashback_balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def get_cashback_history(user_id):
    """Barcha keshbeklar tarixini olish"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT amount, percent, cashback, created_at, type 
        FROM cashback_history 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (user_id,))
    history = cursor.fetchall()
    conn.close()
    return history

def get_referrals_count(user_id):
    """Taklif qilgan odamlar soni"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT referrals_count FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def get_statistics():
    """Umumiy statistika olish"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Umumiy foydalanuvchilar
    cursor.execute('SELECT COUNT(*) FROM users WHERE registered = 1')
    total_users = cursor.fetchone()[0]
    
    # Bugun qo'shilganlar
    cursor.execute('SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE("now")')
    today_users = cursor.fetchone()[0]
    
    # Umumiy cashback balansi
    cursor.execute('SELECT SUM(cashback_balance) FROM users')
    total_balance = cursor.fetchone()[0] or 0
    
    # Umumiy transaksiyalar soni va summasi
    cursor.execute('SELECT COUNT(*), SUM(cashback) FROM cashback_history')
    transactions = cursor.fetchone()
    
    # Oxirgi 7 kun statistikasi
    cursor.execute('''
        SELECT DATE(created_at) as date, COUNT(*) as count 
        FROM users 
        WHERE created_at >= DATE("now", "-7 days")
        GROUP BY DATE(created_at)
        ORDER BY date DESC
    ''')
    weekly_stats = cursor.fetchall()
    
    conn.close()
    return {
        'total_users': total_users,
        'today_users': today_users,
        'total_balance': total_balance,
        'total_transactions': transactions[0] or 0,
        'total_cashback_given': transactions[1] or 0,
        'weekly_stats': weekly_stats
    }

def delete_user(user_id):
    """Foydalanuvchini butunlay o'chirish"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # Avval tarixni o'chirish (foreign key constraint uchun)
        cursor.execute('DELETE FROM cashback_history WHERE user_id = ?', (user_id,))
        # Keyin foydalanuvchini o'chirish
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Foydalanuvchini o'chirishda xato: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


# ==================== TEXTS ====================
TEXTS = {
    'uz': {
        'welcome': """👋 <b>Assalomu alaykum!</b>

SPK Systems botiga xush kelibsiz 🤝

🛒 Xarid qiling
💰 Cashback oling  
📊 Balansingizni kuzating

Biz orqali qilgan har bir xaridingiz sizga foyda keltiradi.

👇 Quyidagi menyudan kerakli bo'limni tanlang""",
        
        'choose_language': "🌐 Tilni tanlang:",
        'enter_name': "✏️ Ismingizni kiriting:",
        'share_phone': "📱 Telefon raqamingizni yuboring:",
        'phone_button': "📞 Kontaktni yuborish",
        'registered': "✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!",
        'invalid_phone': "❌ Iltimos, kontaktni yuboring:",
        'cashback': "💰 Cashback",
        'balance': "📊 Balans",
        'history': "🧾 Xaridlar tarixi",
        'location': "📍 Manzil",
        'contact': "📞 Malumot uchun",
        'group': "👥 Guruhga qo'shilish",
        'referral': "👤 Odam qo'shish",
        'back': "⬅️ Orqaga",
        'change_language': "🌐 Tilni o'zgartirish",
        
        # Admin specific
        'admin_panel': "🔐 <b>Admin Panel</b>\n\nQuyidagi bo'limlardan birini tanlang:",
        'admin_user_info': """👤 <b>Foydalanuvchi ma'lumotlari</b>

📝 Ism: <b>{name}</b>
📱 Telefon: <code>{phone}</code>
💰 Balans: <b>{balance} so'm</b>
🆔 ID: <code>{user_id}</code>""",
        'admin_reset_success': "✅ Foydalanuvchi balansi va tarixi tozalandi!",
        'admin_reset_error': "❌ Xatolik yuz berdi!",
        'admin_back_to_users': "◀️ Orqaga (Foydalanuvchilar)",
        'admin_reset_button': "🗑 Balansni 0 ga tushirish",
        'admin_bonus_button': "🎁 Bonus berish",
        'admin_enter_percent': "📊 <b>Bonus foizini kiriting</b>\n\nFoydalanuvchining joriy balansiga qancha foiz (%) bonus qo'shmoqchisiz?\n\nMisol: <code>5</code> (5% bonus)\n<code>10</code> (10% bonus)\n<code>15</code> (15% bonus)",
        'admin_invalid_percent': "❌ Iltimos, faqat raqam kiriting (1-100 orasida):",
        'admin_bonus_success': """✅ <b>Bonus muvaffaqiyatli qo'shildi!</b>

💰 Joriy balans: <b>{old_balance} so'm</b>
🎁 Bonus ({percent}%): <b>+{bonus} so'm</b>
💵 Yangi balans: <b>{new_balance} so'm</b>""",
        'admin_bonus_error': "❌ Bonus qo'shishda xatolik yuz berdi!",
        'admin_delete_button': "🗑 O'chirish",
        'admin_delete_confirm': "❓ <b>Foydalanuvchini o'chirish</b>\n\nRostdan ham ushbu foydalanuvchini o'chirmoqchimisiz?\n\nBu amalni qaytarib bo'lmaydi!",
        'admin_delete_success': "✅ Foydalanuvchi muvaffaqiyatli o'chirildi!",
        'admin_delete_error': "❌ O'chirishda xatolik yuz berdi!",
        'admin_delete_cancel': "❌ O'chirish bekor qilindi.",
        # Admin Stats
        'admin_stats_title': "📊 <b>Umumiy Statistika</b>",
        'admin_stats_weekly': "📈 Oxirgi 7 kun:",
        
        # Admin Broadcast
        'admin_broadcast_title': "📢 <b>Barcha foydalanuvchilarga xabar yuborish</b>\n\nXabaringizni kiriting (matn, rasm yoki video):\n\n❌ Bekor qilish uchun /cancel",
        'admin_broadcast_confirm': "❓Ushbu xabarni barcha foydalanuvchilarga yuborishni xohlaysizmi?",
        'admin_broadcast_sent': "✅ <b>Yuborildi!</b>\n\n✔️ Muvaffaqiyatli: <b>{sent}</b> ta\n❌ Muvaffaqiyatsiz: <b>{failed}</b> ta",
        'admin_broadcast_cancel': "❌ Xabar yuborish bekor qilindi.",
        
        # Admin Deduct
        'admin_deduct_title': "➖ <b>Balansdan ayirish</b>\n\nJoriy balans: <b>{balance}</b> so'm\n\nAyirish miqdorini kiriting (so'mda):\nMisol: <code>50000</code>",
        'admin_deduct_success': """✅ <b>Balans muvaffaqiyatli ayirildi!</b>

💰 Eski balans: <b>{old_balance}</b> so'm
➖ Ayirildi: <b>{amount}</b> so'm
💵 Yangi balans: <b>{new_balance}</b> so'm""",
        'admin_deduct_invalid': "❌ Iltimos, faqat musbat raqam kiriting:",
        'admin_deduct_error': "❌ Xatolik! Balansda yetarli mablag' yo'q.",
        'admin_deduct_button': "➖ Ayirish",
        'admin_history_button': "📜 Tarix",
        
        # Referral specific
        'referral_title': """👤 <b>Do'stlaringizni taklif qiling!</b>

💎 Havolangiz bilan ro'yxatdan o'tgan har bir do'stingiz uchun <b>1% bonus</b> olasiz!

📊 Joriy balans: <b>{balance} so'm</b>
👥 Taklif qilganlar: <b>{count} ta</b>

👇 Havolani ulashing:""",
        'referral_share_text': "🎁 SPK Systems botiga qo'shil va cashback yig'!",
        'referral_success_user': "🎉 Siz do'stingiz taklifi bilan qo'shildingiz!",
        'referral_success_inviter': """🎉 Tabriklaymiz! Yangi do'stingiz qo'shildi!

💰 Balansingizga <b>{bonus} so'm</b> bonus qo'shildi!
💵 Joriy balans: <b>{balance} so'm</b>""",
        
        # Cashback specific
        'cashback_title': "💰 <b>Cashback hisoblash</b>\n\nXarid qilgan summangizni yozing.\nBot avtomatik tarzda <b>1% dan 5% gacha</b> cashback hisoblab beradi.\n\n📌 Misol: <code>1000000</code>",
        'cashback_success': """✅ <b>Xarid muvaffaqiyatli qabul qilindi!</b>

🧾 Xarid summasi: <b>{amount} so'm</b>
🎯 Cashback foizi: <b>{percent}%</b>
💸 Cashback: <b>{cashback} so'm</b>
💰 Joriy balans: <b>{balance} so'm</b>

🎉 Cashback balansingizga qo'shildi!""",
        'invalid_amount': "❌ Iltimos, faqat raqam kiriting:\nMisol: <code>150000</code>",
        
        # Balance specific
        'balance_title': """📊 <b>Sizning balansingiz:</b>

💰 Cashback: <b>{balance} so'm</b>

ℹ️ Xarid qilganingiz sari balansingiz oshib boradi.
Cashback'ni keyinroq foydalanishingiz mumkin.""",

        # History specific
        'history_empty': """🧾 <b>Xaridlar tarixi</b>

Siz hali xarid amalga oshirmagansiz.""",
        'history_item': "🗓 <b>{date}</b>\n💵 Summa: {amount} so'm\n🎯 Foiz: {percent}%\n💰 Cashback: <code>+{cashback}</code> so'm\n<b>{type}</b>\n━━━━━━━━━━━━━━\n",
        'type_purchase': "🛒 Xarid",
        'type_referral': "👤 Referral bonus",
        'type_admin_bonus': "🎁 Admin bonus",
        'type_admin_deduct': "➖ Admin ayirish",
    },
    
    'ru': {
        'welcome': """👋 <b>Здравствуйте!</b>

Добро пожаловать в бот SPK Systems 🤝

🛒 Совершайте покупки
💰 Получайте кешбэк
📊 Отслеживайте баланс

Каждая покупка через нас приносит вам выгоду.

👇 Выберите нужный раздел из меню ниже""",
        
        'choose_language': "🌐 Выберите язык:",
        'enter_name': "✏️ Введите ваше имя:",
        'share_phone': "📱 Отправьте ваш номер телефона:",
        'phone_button': "📞 Отправить контакт",
        'registered': "✅ Вы успешно зарегистрированы!",
        'invalid_phone': "❌ Пожалуйста, отправьте контакт:",
        'cashback': "💰 Кешбэк",
        'balance': "📊 Баланс",
        'history': "🧾 История покупок",
        'location': "📍 Адрес",
        'contact': "📞 Для справки",
        'group': "👥 Присоединиться к группе",
        'referral': "👤 Добавить человека",
        'back': "⬅️ Назад",
        'change_language': "🌐 Изменить язык",
        
        # Admin specific
        'admin_panel': "🔐 <b>Admin Panel</b>\n\nВыберите раздел:",
        'admin_user_info': """👤 <b>Информация о пользователе</b>

📝 Имя: <b>{name}</b>
📱 Телефон: <code>{phone}</code>
💰 Баланс: <b>{balance} сум</b>
🆔 ID: <code>{user_id}</code>""",
        'admin_reset_success': "✅ Баланс и история пользователя очищены!",
        'admin_reset_error': "❌ Произошла ошибка!",
        'admin_back_to_users': "◀️ Назад (Пользователи)",
        'admin_reset_button': "🗑 Обнулить баланс",
        'admin_bonus_button': "🎁 Дать бонус",
        'admin_enter_percent': "📊 <b>Введите процент бонуса</b>\n\nСколько процентов (%) добавить к текущему балансу пользователя?\n\nПример: <code>5</code> (5% бонус)\n<code>10</code> (10% бонус)\n<code>15</code> (15% бонус)",
        'admin_invalid_percent': "❌ Пожалуйста, введите только число (от 1 до 100):",
        'admin_bonus_success': """✅ <b>Бонус успешно добавлен!</b>

💰 Текущий баланс: <b>{old_balance} сум</b>
🎁 Бонус ({percent}%): <b>+{bonus} сум</b>
💵 Новый баланс: <b>{new_balance} сум</b>""",
        'admin_bonus_error': "❌ Ошибка при добавлении бонуса!",
        'admin_delete_button': "🗑 Удалить",
        'admin_delete_confirm': "❓ <b>Удаление пользователя</b>\n\nВы действительно хотите удалить этого пользователя?\n\nЭто действие нельзя отменить!",
        'admin_delete_success': "✅ Пользователь успешно удален!",
        'admin_delete_error': "❌ Ошибка при удалении!",
        'admin_delete_cancel': "❌ Удаление отменено.",
        
        # Admin Stats
        'admin_stats_title': "📊 <b>Общая статистика</b>",
        'admin_stats_weekly': "📈 Последние 7 дней:",
        
        # Admin Broadcast
        'admin_broadcast_title': "📢 <b>Отправить сообщение всем пользователям</b>\n\nВведите сообщение (текст, фото или видео):\n\n❌ Отменить /cancel",
        'admin_broadcast_confirm': "❓Отправить это сообщение всем пользователям?",
        'admin_broadcast_sent': "✅ <b>Отправлено!</b>\n\n✔️ Успешно: <b>{sent}</b>\n❌ Неудачно: <b>{failed}</b>",
        'admin_broadcast_cancel': "❌ Отправка отменена.",
        
        # Admin Deduct
        'admin_deduct_title': "➖ <b>Вычесть с баланса</b>\n\nТекущий баланс: <b>{balance}</b> сум\n\nВведите сумму для вычитания:\nПример: <code>50000</code>",
        'admin_deduct_success': """✅ <b>С баланса успешно вычтено!</b>

💰 Старый баланс: <b>{old_balance}</b> сум
➖ Вычтено: <b>{amount}</b> сум
💵 Новый баланс: <b>{new_balance}</b> сум""",
        'admin_deduct_invalid': "❌ Пожалуйста, введите только положительное число:",
        'admin_deduct_error': "❌ Ошибка! Недостаточно средств на балансе.",
        'admin_deduct_button': "➖ Вычесть",
        'admin_history_button': "📜 История",
        
        # Referral specific
        'referral_title': """👤 <b>Приглашайте друзей!</b>

💎 За каждого друга, зарегистрировавшегося по вашей ссылке, вы получите <b>1% бонуса</b>!

📊 Текущий баланс: <b>{balance} сум</b>
👥 Приглашено: <b>{count} чел.</b>

👇 Поделитесь ссылкой:""",
        'referral_share_text': "🎁 Присоединяйся к SPK Systems и копи кешбэк!",
        'referral_success_user': "🎉 Вы присоединились по приглашению друга!",
        'referral_success_inviter': """🎉 Поздравляем! Новый друг присоединился!

💰 На ваш баланс добавлено <b>{bonus} сум</b>!
💵 Текущий баланс: <b>{balance} сум</b>""",
        
        # Cashback specific
        'cashback_title': "💰 <b>Расчет кешбэка</b>\n\nВведите сумму покупки.\nБот автоматически рассчитает <b>кешбэк от 1% до 5%</b>.\n\n📌 Пример: <code>1000000</code>",
        'cashback_success': """✅ <b>Покупка успешно принята!</b>

🧾 Сумма покупки: <b>{amount} сум</b>
🎯 Процент кешбэка: <b>{percent}%</b>
💸 Кешбэк: <b>{cashback} сум</b>
💰 Текущий баланс: <b>{balance} сум</b>

🎉 Кешбэк добавлен на ваш баланс!""",
        'invalid_amount': "❌ Пожалуйста, введите только число:\nПример: <code>150000</code>",
        
        # Balance specific
        'balance_title': """📊 <b>Ваш баланс:</b>

💰 Кешбэк: <b>{balance} сум</b>

ℹ️ С каждой покупкой ваш баланс растет.
Кешбэком можно воспользоваться позже.""",

        # History specific
        'history_empty': """🧾 <b>История покупок</b>

Вы еще не совершали покупок.""",
        'history_item': "🗓 <b>{date}</b>\n💵 Сумма: {amount} сум\n🎯 Процент: {percent}%\n💰 Кешбэк: <code>+{cashback}</code> сум\n<b>{type}</b>\n━━━━━━━━━━━━━━\n",
        'type_purchase': "🛒 Покупка",
        'type_referral': "👤 Реферальный бонус",
        'type_admin_bonus': "🎁 Бонус от админа",
        'type_admin_deduct': "➖ Вычет админа",
    }
}

def format_number(num):
    """Raqamni 1 000 000 formatida chiqarish"""
    try:
        return f"{int(num):,}".replace(",", " ")
    except:
        return str(num)

def format_date(date_str):
    """SQLite date formatini chiroyli ko'rinishga o'tkazish"""
    try:
        return date_str[:16].replace("-", ".").replace("T", " ")
    except:
        return date_str

# ==================== STATES ====================
class Registration(StatesGroup):
    language = State()
    name = State()
    phone = State()

class CashbackState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_photo = State()  # Yangi state

class AdminState(StatesGroup):
    waiting_for_bonus_percent = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirmation = State()

class AdminDeductState(StatesGroup):
    waiting_for_amount = State()

# ==================== KEYBOARDS ====================
def language_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data='lang_uz'),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data='lang_ru')
        ]
    ])

def phone_keyboard(lang):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXTS[lang]['phone_button'], request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def main_menu_inline(lang):
    """Asosiy menyu - 6 ta tugma"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TEXTS[lang]['cashback'], callback_data='cashback')],
        [InlineKeyboardButton(text=TEXTS[lang]['balance'], callback_data='balance')],
        [InlineKeyboardButton(text=TEXTS[lang]['history'], callback_data='history')],
        [InlineKeyboardButton(text=TEXTS[lang]['location'], callback_data='location')],
        [InlineKeyboardButton(text=TEXTS[lang]['contact'], callback_data='contact')],
        [InlineKeyboardButton(text=TEXTS[lang]['group'], callback_data='group')],
        [InlineKeyboardButton(text=TEXTS[lang]['referral'], callback_data='referral')],
        [InlineKeyboardButton(text=TEXTS[lang]['change_language'], callback_data='change_language_main')],
    ])

def back_keyboard(lang):
    """Orqaga tugmasi"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TEXTS[lang]['back'], callback_data='main_menu')]
    ])

def location_keyboard(lang):
    """Manzil uchun keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📍 {'Yangi Jomi 1 (Yunusobod)' if lang == 'uz' else 'Янги Джоми 1 (Юнусобод)'}", 
                             url="https://maps.google.com/maps?q=41.357268   ,69.244138&ll=41.357268,69.244138&z=16")],
        [InlineKeyboardButton(text=f"📍 {'Dimax (Nazarbek bozor)' if lang == 'uz' else 'Димах (Назарбек базар)'}", 
                             url="https://maps.google.com/maps?q=41.311049   ,69.152031&ll=41.311049,69.152031&z=16")],
        [InlineKeyboardButton(text=TEXTS[lang]['back'], callback_data='main_menu')]
    ])

def referral_keyboard(lang, bot_username, user_id):
    """Referral tugmalari"""
    referral_link = f"https://t.me/  {bot_username}?start=ref_{user_id}"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Ulashish / Поделиться", url=f"https://t.me/share/url?url=  {referral_link}&text={TEXTS[lang]['referral_share_text']}")],
        [InlineKeyboardButton(text=TEXTS[lang]['back'], callback_data='main_menu')]
    ])

def admin_main_keyboard():
    """Admin paneli uchun menyu"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_panel_users")],
        [InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="admin_broadcast")],
    ])

def admin_users_keyboard():
    """Admin panel - foydalanuvchilar ro'yxati"""
    users = get_all_users()
    buttons = []
    
    for user in users:
        user_id, name, phone, balance, first_name, last_name = user
        display_name = name if name else f"{first_name} {last_name if last_name else ''}".strip()
        if not display_name:
            display_name = f"User {user_id}"
        
        # Har bir qatorda 1 ta tugma (yaxshi ko'rinish uchun)
        buttons.append([InlineKeyboardButton(
            text=f"{display_name} | {format_number(balance)} so'm",
            callback_data=f"admin_user_{user_id}"
        )])
    
    if not buttons:
        buttons.append([InlineKeyboardButton(text="❌ Foydalanuvchilar yo'q", callback_data="admin_empty")])
    
    buttons.append([InlineKeyboardButton(text="◀️ Asosiy menyu", callback_data="admin_main_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_user_actions_keyboard(user_id, lang='uz'):
    """Admin - foydalanuvchi ma'lumotlari va amallar"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=TEXTS[lang]['admin_bonus_button'], callback_data=f"admin_bonus_{user_id}"),
            InlineKeyboardButton(text=TEXTS[lang]['admin_deduct_button'], callback_data=f"admin_deduct_{user_id}")
        ],
        [
            InlineKeyboardButton(text=TEXTS[lang]['admin_reset_button'], callback_data=f"admin_reset_{user_id}"),
            InlineKeyboardButton(text=TEXTS[lang]['admin_history_button'], callback_data=f"admin_history_{user_id}")
        ],
        [
            InlineKeyboardButton(text=TEXTS[lang]['admin_delete_button'], callback_data=f"admin_delete_{user_id}")
        ],
        [InlineKeyboardButton(text=TEXTS[lang]['admin_back_to_users'], callback_data="admin_panel_users")]
    ])

def stats_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main_menu")]
    ])

# ==================== ROUTER ====================
router = Router()

def is_admin(user_id):
    """Foydalanuvchi admin ekanligini tekshirish"""
    return user_id == ADMIN_ID

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    user = message.from_user
    
    # Admin tekshiruvi
    if is_admin(user.id):
        await state.clear()
        await message.answer(
            TEXTS['uz']['admin_panel'],
            reply_markup=admin_main_keyboard(),
            parse_mode='HTML'
        )
        return
    
    args = message.text.split()
    
    # Referral tekshirish (start ref_{user_id})
    referred_by = None
    if len(args) > 1 and args[1].startswith('ref_'):
        try:
            referred_by = int(args[1].replace('ref_', ''))
            # O'zini o'zi taklif qilishni tekshirish
            if referred_by == user.id:
                referred_by = None
        except:
            referred_by = None
    
    user_data = get_user(user.id)
    
    if not user_data:
        # Yangi foydalanuvchi yaratish
        create_user(user.id, user.username, user.first_name, user.last_name, referred_by)
        
        # Agar referral bo'lsa, bonus berish
        if referred_by and get_user(referred_by):
            # Referrer ning joriy balansini olish
            referrer_balance = get_cashback_balance(referred_by)
            bonus = int(referrer_balance * 0.01)  # 1%
            
            if bonus > 0:
                # Bonus qo'shish
                new_balance = add_referral_bonus(referred_by, bonus)
                
                if new_balance is not None:
                    # Referrer ga xabar yuborish
                    referrer_lang = get_user(referred_by)[6] if get_user(referred_by) else 'uz'
                    try:
                        await bot.send_message(
                            referred_by,
                            TEXTS[referrer_lang]['referral_success_inviter'].format(
                                bonus=format_number(bonus),
                                balance=format_number(new_balance)
                            ),
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logging.error(f"Referral xabar yuborishda xato: {e}")
            
            # Yangi foydalanuvchiga xabar
            user_lang = get_user(user.id)[6] if get_user(user.id) else 'uz'
            await message.answer(TEXTS[user_lang]['referral_success_user'])
    
    # Agar ro'yxatdan o'tgan bo'lsa
    if user_data and user_data[7] == 1:
        lang = user_data[6]
        await message.answer(
            TEXTS[lang]['welcome'], 
            reply_markup=main_menu_inline(lang),
            parse_mode='HTML'
        )
        return
    
    # Ro'yxatdan o'tish
    if not user_data or user_data[7] == 0:
        await state.set_state(Registration.language)
        await message.answer(TEXTS['uz']['choose_language'], reply_markup=language_keyboard())

# ==================== ADMIN HANDLERS ====================
@router.callback_query(F.data == "admin_main_menu")
async def admin_main_handler(callback: CallbackQuery, state: FSMContext):
    """Asosiy admin menyu"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    await state.clear()
    await callback.answer()
    
    await callback.message.edit_text(
        TEXTS['uz']['admin_panel'],
        reply_markup=admin_main_keyboard(),
        parse_mode='HTML'
    )

@router.callback_query(F.data == "admin_panel_users")
async def admin_panel_handler(callback: CallbackQuery, state: FSMContext):
    """Foydalanuvchilar ro'yxati"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    await state.clear()
    await callback.answer()
    
    await callback.message.edit_text(
        "👥 <b>Foydalanuvchilar ro'yxati:</b>",
        reply_markup=admin_users_keyboard(),
        parse_mode='HTML'
    )

@router.callback_query(F.data.startswith("admin_user_"))
async def admin_user_details(callback: CallbackQuery):
    """Foydalanuvchi ma'lumotlarini ko'rish"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    user_id = int(callback.data.replace("admin_user_", ""))
    user = get_user(user_id)
    
    if not user:
        await callback.answer("Foydalanuvchi topilmadi!", show_alert=True)
        return
    
    await callback.answer()
    
    # User ma'lumotlarini olish
    _, username, first_name, last_name, name, phone, lang, registered, balance, referred_by, referrals_count, created_at = user
    
    display_name = name if name else f"{first_name} {last_name if last_name else ''}".strip()
    display_phone = phone if phone else "Telefon kiritilmagan"
    
    text = TEXTS['uz']['admin_user_info'].format(
        name=display_name,
        phone=display_phone,
        balance=format_number(balance),
        user_id=user_id
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=admin_user_actions_keyboard(user_id, 'uz'),
        parse_mode='HTML'
    )

@router.callback_query(F.data.startswith("admin_reset_"))
async def admin_reset_user(callback: CallbackQuery):
    """Foydalanuvchi balansini va tarixini tozalash"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    user_id = int(callback.data.replace("admin_reset_", ""))
    
    # Ma'lumotlarni tozalash
    success = reset_user_data(user_id)
    
    if success:
        await callback.answer(TEXTS['uz']['admin_reset_success'], show_alert=True)
        # Yangilangan ma'lumotlarni ko'rsatish
        await admin_user_details(callback)
    else:
        await callback.answer(TEXTS['uz']['admin_reset_error'], show_alert=True)

@router.callback_query(F.data.startswith("admin_bonus_"))
async def admin_bonus_start(callback: CallbackQuery, state: FSMContext):
    """Bonus berishni boshlash - foiz kiritishni so'rash"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    user_id = int(callback.data.replace("admin_bonus_", ""))
    
    # State ga saqlaymiz qaysi foydalanuvchiga bonus berayotganimizni
    await state.set_state(AdminState.waiting_for_bonus_percent)
    await state.update_data(target_user_id=user_id)
    
    await callback.answer()
    await callback.message.edit_text(
        TEXTS['uz']['admin_enter_percent'],
        parse_mode='HTML'
    )

@router.callback_query(F.data.startswith("admin_delete_"))
async def admin_delete_start(callback: CallbackQuery, state: FSMContext):
    """Foydalanuvchini o'chirishni boshlash - tasdiqlash so'rash"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    user_id = int(callback.data.replace("admin_delete_", ""))
    
    # Tasdiqlash tugmalari
    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, o'chirish", callback_data=f"confirm_delete_{user_id}"),
            InlineKeyboardButton(text="❌ Yo'q, bekor", callback_data=f"cancel_delete_{user_id}")
        ]
    ])
    
    await callback.answer()
    await callback.message.edit_text(
        TEXTS['uz']['admin_delete_confirm'],
        reply_markup=confirm_keyboard,
        parse_mode='HTML'
    )

@router.callback_query(F.data.startswith("confirm_delete_"))
async def admin_delete_confirm(callback: CallbackQuery):
    """O'chirishni tasdiqlash - bazadan o'chirish"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    user_id = int(callback.data.replace("confirm_delete_", ""))
    
    # O'chirish
    success = delete_user(user_id)
    
    if success:
        await callback.answer(TEXTS['uz']['admin_delete_success'], show_alert=True)
        # Foydalanuvchilar ro'yxatiga qaytish
        await callback.message.edit_text(
            "👥 <b>Foydalanuvchilar ro'yxati:</b>",
            reply_markup=admin_users_keyboard(),
            parse_mode='HTML'
        )
    else:
        await callback.answer(TEXTS['uz']['admin_delete_error'], show_alert=True)

@router.callback_query(F.data.startswith("cancel_delete_"))
async def admin_delete_cancel(callback: CallbackQuery):
    """O'chirishni bekor qilish"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    user_id = int(callback.data.replace("cancel_delete_", ""))
    
    await callback.answer(TEXTS['uz']['admin_delete_cancel'], show_alert=True)
    
    # Foydalanuvchi ma'lumotlariga qaytish
    await admin_user_details(callback)

@router.message(AdminState.waiting_for_bonus_percent)
async def admin_bonus_process(message: Message, state: FSMContext):
    """Bonus foizini qabul qilish va qo'llash"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Ruxsat yo'q!")
        await state.clear()
        return
    
    # Foizni olish
    try:
        percent = int(message.text.strip())
        if percent <= 0 or percent > 100:
            raise ValueError("Noto'g'ri diapazon")
    except ValueError:
        await message.answer(TEXTS['uz']['admin_invalid_percent'])
        return
    
    # State dan foydalanuvchi ID sini olish
    data = await state.get_data()
    target_user_id = data.get('target_user_id')
    
    if not target_user_id:
        await message.answer("❌ Xatolik! Foydalanuvchi topilmadi.")
        await state.clear()
        return
    
    # Eski balansni olish (xabar uchun)
    old_balance = get_cashback_balance(target_user_id)
    
    # Bonus qo'shish
    new_balance, bonus_amount = add_bonus_to_user(target_user_id, percent)
    
    if new_balance is not None:
        # Muvaffaqiyatli xabar
        text = TEXTS['uz']['admin_bonus_success'].format(
            old_balance=format_number(old_balance),
            percent=percent,
            bonus=format_number(bonus_amount),
            new_balance=format_number(new_balance)
        )
        await message.answer(text, parse_mode='HTML')
        
        # Admin panelga qaytish tugmasi
        await message.answer(
            "👇 Admin panelga qaytish:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=TEXTS['uz']['admin_back_to_users'], callback_data=f"admin_user_{target_user_id}")]
            ])
        )
    else:
        await message.answer(TEXTS['uz']['admin_bonus_error'])
    
    await state.clear()

    # Yangilangan ma'lumotlarni ko'rsatish
    await admin_user_details(message)

# ==================== ADMIN BROADCAST ====================
@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    """Broadcast boshlash"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.message.edit_text(
        TEXTS['uz']['admin_broadcast_title'],
        parse_mode='HTML'
    )

@router.message(BroadcastState.waiting_for_message)
async def admin_broadcast_confirm(message: Message, state: FSMContext):
    """Xabarni tasdiqlash"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text == "/cancel":
        await message.answer(TEXTS['uz']['admin_broadcast_cancel'], reply_markup=admin_main_keyboard())
        await state.clear()
        return
    
    # Xabarni saqlash
    message_type = 'text'
    content = message.text
    caption = None
    
    if message.photo:
        message_type = 'photo'
        content = message.photo[-1].file_id
        caption = message.caption
    elif message.video:
        message_type = 'video'
        content = message.video.file_id
        caption = message.caption
    
    await state.update_data(
        message_type=message_type,
        content=content,
        caption=caption
    )
    
    # Tasdiqlash so'rash
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, yuborish", callback_data="confirm_broadcast"),
            InlineKeyboardButton(text="❌ Yo'q, bekor", callback_data="cancel_broadcast")
        ]
    ])
    
    await message.answer(TEXTS['uz']['admin_broadcast_confirm'], reply_markup=keyboard)
    await state.set_state(BroadcastState.waiting_for_confirmation)

@router.callback_query(F.data == "confirm_broadcast")
async def admin_broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Xabarni yuborish"""
    if not is_admin(callback.from_user.id):
        return
    
    data = await state.get_data()
    users = get_all_users()
    
    await callback.message.edit_text("⏳ Yuborilmoqda...")
    
    sent = 0
    failed = 0
    
    for user in users:
        try:
            if data['message_type'] == 'text':
                await bot.send_message(user[0], data['content'])
            elif data['message_type'] == 'photo':
                await bot.send_photo(user[0], data['content'], caption=data.get('caption'))
            elif data['message_type'] == 'video':
                await bot.send_video(user[0], data['content'], caption=data.get('caption'))
            sent += 1
            await asyncio.sleep(0.05)  # Rate limit
        except Exception as e:
            failed += 1
            logging.error(f"Xabar yuborishda xato {user[0]}: {e}")
    
    await callback.message.edit_text(
        TEXTS['uz']['admin_broadcast_sent'].format(sent=sent, failed=failed),
        reply_markup=admin_main_keyboard(),
        parse_mode='HTML'
    )
    await state.clear()

@router.callback_query(F.data == "cancel_broadcast")
async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    """Bekor qilish"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.message.edit_text(TEXTS['uz']['admin_broadcast_cancel'], reply_markup=admin_main_keyboard())
    await state.clear()

# ==================== ADMIN DEDUCT ====================
@router.callback_query(F.data.startswith("admin_deduct_"))
async def admin_deduct_start(callback: CallbackQuery, state: FSMContext):
    """Balansdan ayirishni boshlash"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    user_id = int(callback.data.replace("admin_deduct_", ""))
    current_balance = get_cashback_balance(user_id)
    
    await state.set_state(AdminDeductState.waiting_for_amount)
    await state.update_data(target_user_id=user_id, current_balance=current_balance)
    
    await callback.message.edit_text(
        TEXTS['uz']['admin_deduct_title'].format(balance=format_number(current_balance)),
        parse_mode='HTML'
    )

@router.message(AdminDeductState.waiting_for_amount)
async def admin_deduct_process(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    if message.text == "/cancel":
        await message.answer("Bekor qilindi.", reply_markup=admin_main_keyboard())
        await state.clear()
        return
    
    try:
        amount = int(message.text.strip().replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except:
        await message.answer(TEXTS['uz']['admin_deduct_invalid'])
        return
    
    data = await state.get_data()
    target_user_id = data['target_user_id']
    current_balance = data['current_balance']
    
    if amount > current_balance:
        await message.answer(f"❌ Xatolik! Balansda yetarli mablag' yo'q.\nJoriy: {format_number(current_balance)} so'm")
        return
    
    # Bazadan ayirish
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    new_balance = current_balance - amount
    
    try:
        cursor.execute('UPDATE users SET cashback_balance = ? WHERE user_id = ?', (new_balance, target_user_id))
        cursor.execute('''
            INSERT INTO cashback_history (user_id, amount, percent, cashback, type) 
            VALUES (?, ?, ?, ?, ?)
        ''', (target_user_id, 0, 0, -amount, 'admin_deduct'))
        
        conn.commit()
        
        await message.answer(
            TEXTS['uz']['admin_deduct_success'].format(
                old_balance=format_number(current_balance),
                amount=format_number(amount),
                new_balance=format_number(new_balance)
            ),
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"admin_user_{target_user_id}")]
            ])
        )
    except Exception as e:
        logging.error(f"Ayirishda xato: {e}")
        await message.answer("❌ Xatolik yuz berdi!")
    finally:
        conn.close()
    
    await state.clear()

# ==================== ADMIN HISTORY ====================
@router.callback_query(F.data.startswith("admin_history_"))
async def admin_user_history(callback: CallbackQuery):
    """Admin uchun foydalanuvchi tarixini ko'rish"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    user_id = int(callback.data.replace("admin_history_", ""))
    history = get_cashback_history(user_id)
    
    if not history:
        text = "📜 <b>Tranzaksiyalar tarixi bo'sh</b>"
    else:
        text = f"📜 <b>Tranzaksiyalar tarixi</b> (User: {user_id})\n\n"
        for amount, percent, cashback, date, type_tx in history[:20]:  # Oxirgi 20 tasi
            emoji = "🟢" if cashback > 0 else "🔴"
            type_key = f"type_{type_tx}"
            type_text = TEXTS['uz'].get(type_key, type_tx)
            text += f"{emoji} {format_date(date)}: <b>{format_number(abs(cashback))}</b> so'm ({type_text})\n"
    
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"admin_user_{user_id}")]
    ]))

@router.callback_query(F.data == "admin_empty")
async def admin_empty_handler(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data.startswith('lang_'), Registration.language)
async def process_language(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    lang = callback.data.split('_')[1]
    user_id = callback.from_user.id
    
    update_language(user_id, lang)
    await state.update_data(language=lang)
    
    await state.set_state(Registration.name)
    await callback.message.edit_text(TEXTS[lang]['enter_name'])

@router.message(Registration.name)
async def process_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    name = message.text.strip()
    
    if len(name) < 2:
        data = await state.get_data()
        lang = data.get('language', 'uz')
        await message.answer("❌ Ism juda qisqa!" if lang == 'uz' else "❌ Имя слишком короткое!")
        return
    
    update_name(user_id, name)
    data = await state.get_data()
    lang = data.get('language', 'uz')
    
    await state.set_state(Registration.phone)
    await message.answer(TEXTS[lang]['share_phone'], reply_markup=phone_keyboard(lang))

@router.message(Registration.phone, F.contact)
async def process_phone(message: Message, state: FSMContext):
    user_id = message.from_user.id
    phone = message.contact.phone_number
    
    update_phone(user_id, phone)
    data = await state.get_data()
    lang = data.get('language', 'uz')
    
    await state.clear()
    
    # Contact tugmasini olib tashlash
    await message.answer(TEXTS[lang]['registered'], reply_markup=ReplyKeyboardMarkup(keyboard=[[]], resize_keyboard=True))
    
    await message.answer(
        TEXTS[lang]['welcome'], 
        reply_markup=main_menu_inline(lang),
        parse_mode='HTML'
    )

@router.message(Registration.phone)
async def invalid_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('language', 'uz')
    await message.answer(TEXTS[lang]['invalid_phone'])

@router.callback_query(F.data == 'main_menu')
async def main_menu_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    user = get_user(callback.from_user.id)
    lang = user[6] if user else 'uz'
    
    await callback.message.delete()
    await callback.message.answer(
        TEXTS[lang]['welcome'],
        reply_markup=main_menu_inline(lang),
        parse_mode='HTML'
    )

# ==================== REFERRAL HANDLER ====================
@router.callback_query(F.data == 'referral')
async def referral_handler(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    user = get_user(callback.from_user.id)
    lang = user[6] if user else 'uz'
    
    balance = get_cashback_balance(callback.from_user.id)
    count = get_referrals_count(callback.from_user.id)
    
    # Bot username olish
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    
    text = TEXTS[lang]['referral_title'].format(
        balance=format_number(balance),
        count=count
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=referral_keyboard(lang, bot_username, callback.from_user.id),
        parse_mode='HTML'
    )

# ==================== LANGUAGE CHANGE HANDLER ====================
@router.callback_query(F.data == 'change_language_main')
async def change_language_main_handler(callback: CallbackQuery):
    """Asosiy menyudan tilni almashtirish"""
    await callback.answer()
    
    user = get_user(callback.from_user.id)
    current_lang = user[6] if user else 'uz'
    
    # Tilni almashtirish
    new_lang = 'ru' if current_lang == 'uz' else 'uz'
    
    # Bazaga saqlash
    update_language(callback.from_user.id, new_lang)
    
    # Xabar va menyuni yangilash
    await callback.message.edit_text(
        TEXTS[new_lang]['welcome'],
        reply_markup=main_menu_inline(new_lang),
        parse_mode='HTML'
    )

# ==================== CASHBACK HANDLERS ====================
@router.callback_query(F.data == 'cashback')
async def cashback_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = get_user(callback.from_user.id)
    lang = user[6] if user else 'uz'
    
    await state.set_state(CashbackState.waiting_for_amount)
    
    await callback.message.edit_text(
        TEXTS[lang]['cashback_title'],
        reply_markup=back_keyboard(lang),
        parse_mode='HTML'
    )

@router.message(CashbackState.waiting_for_amount)
async def process_cashback_amount(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = get_user(user_id)
    lang = user[6] if user else 'uz'
    
    # Raqamni tozalash
    text = message.text.strip()
    cleaned = text.replace(" ", "").replace("so'm", "").replace("sum", "").replace("сум", "").replace(",", "").replace(".", "")
    
    try:
        amount = int(cleaned)
        if amount <= 0:
            raise ValueError("Manfiy son")
        if amount > 100_000_000:
            raise ValueError("Juda katta summa")
    except ValueError:
        await message.answer(TEXTS[lang]['invalid_amount'], parse_mode='HTML')
        return
    
    # Summani state'da saqlash va rasm so'rash
    await state.update_data(amount=amount)
    await message.answer(
        "📸 <b>Mahsulot rasmini yuboring:</b>\n\nIltimos, sotib olgan mahsulotingiz rasmini yuboring." if lang == 'uz' 
        else "📸 <b>Отправьте фото товара:</b>\n\nПожалуйста, отправьте фото купленного товара.",
        parse_mode='HTML'
    )
    await state.set_state(CashbackState.waiting_for_photo)

@router.message(CashbackState.waiting_for_photo, F.photo)
async def process_cashback_photo(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    user = get_user(user_id)
    lang = user[6] if user else 'uz'
    data = await state.get_data()
    amount = data.get('amount')
    
    # Rasm file_id sini olish (eng yuqori sifatli)
    photo_file_id = message.photo[-1].file_id
    
    # Foydalanuvchi ma'lumotlari
    user_info = f"{user[4] if user[4] else message.from_user.full_name}" if user else message.from_user.full_name
    phone = user[5] if user and user[5] else "Telefon kiritilmagan"
    
    # Admin ga yuboriladigan matn
    admin_text = f"""🆕 <b>Yangi Cashback So'rovi</b>

👤 Foydalanuvchi: <b>{user_info}</b>
🆔 ID: <code>{user_id}</code>
📱 Telefon: <code>{phone}</code>
💵 Xarid summasi: <b>{format_number(amount)} so'm</b>

❓ Tasdiqlaysizmi?"""
    
    if lang == 'ru':
        admin_text = f"""🆕 <b>Новый запрос на кешбэк</b>

👤 Пользователь: <b>{user_info}</b>
🆔 ID: <code>{user_id}</code>
📱 Телефон: <code>{phone}</code>
💵 Сумма покупки: <b>{format_number(amount)} сум</b>

❓ Подтверждаете?"""
    
    # Admin uchun tugmalar
    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Tasdiqlash" if lang == 'uz' else "✅ Подтвердить", 
                callback_data=f"ccf_{user_id}_{amount}"  # cashback confirm
            ),
            InlineKeyboardButton(
                text="❌ Bekor qilish" if lang == 'uz' else "❌ Отменить", 
                callback_data=f"ccx_{user_id}_{amount}"  # cashback cancel
            )
        ]
    ])
    
    # Admin ga yuborish
    try:
        await bot.send_photo(
            ADMIN_ID, 
            photo_file_id, 
            caption=admin_text, 
            reply_markup=admin_keyboard,
            parse_mode='HTML'
        )
        
        # Foydalanuvchiga xabar
        await message.answer(
            "✅ <b>So'rovingiz adminga yuborildi!</b>\n\nIltimos, tasdiqlashini kuting..." 
            if lang == 'uz' 
            else "✅ <b>Ваш запрос отправлен администратору!</b>\n\nПожалуйста, ожидайте подтверждения...",
            parse_mode='HTML'
        )
    except Exception as e:
        logging.error(f"Admin ga yuborishda xato: {e}")
        await message.answer(
            "❌ Xatolik yuz berdi. Iltimos keyinroq qayta urinib ko'ring." 
            if lang == 'uz' 
            else "❌ Произошла ошибка. Попробуйте позже.",
            parse_mode='HTML'
        )
    
    await state.clear()

@router.message(CashbackState.waiting_for_photo)
async def invalid_cashback_photo(message: Message):
    """Agar rasm yuborilmasa"""
    user = get_user(message.from_user.id)
    lang = user[6] if user else 'uz'
    await message.answer(
        "❌ Iltimos, faqat rasm yuboring:" if lang == 'uz' else "❌ Пожалуйста, отправьте только фото:"
    )

@router.callback_query(F.data.startswith("ccf_"))
async def admin_confirm_cashback(callback: CallbackQuery, bot: Bot):
    """Admin cashback ni tasdiqlasa"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    # Parse callback data: ccf_userid_amount
    parts = callback.data.split("_")
    user_id = int(parts[1])
    amount = int(parts[2])
    
    # Cashback hisoblash (1% dan 5% gacha)
    percent = random.randint(1, 5)
    cashback = int(amount * percent / 100)
    
    try:
        # Bazaga saqlash
        add_cashback(user_id, amount, percent, cashback)
        new_balance = get_cashback_balance(user_id)
        
        # Foydalanuvchi tilini aniqlash
        user = get_user(user_id)
        user_lang = user[6] if user else 'uz'
        
        # Foydalanuvchiga xabar
        success_text = TEXTS[user_lang]['cashback_success'].format(
            amount=format_number(amount),
            percent=percent,
            cashback=format_number(cashback),
            balance=format_number(new_balance)
        )
        
        await bot.send_message(user_id, success_text, parse_mode='HTML')
        
        # Admin xabarini yangilash
        await callback.message.edit_caption(
            callback.message.caption + f"\n\n✅ <b>TASDIQLANDI</b>\n💰 Cashback: {format_number(cashback)} so'm ({percent}%)",
            parse_mode='HTML'
        )
        
        await callback.answer("✅ Tasdiqlandi va foydalanuvchiga yuborildi!", show_alert=True)
        
    except Exception as e:
        logging.error(f"Cashback tasdiqlashda xato: {e}")
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)

@router.callback_query(F.data.startswith("ccx_"))
async def admin_cancel_cashback(callback: CallbackQuery, bot: Bot):
    """Admin cashback ni bekor qilsa"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[1])
    
    # Foydalanuvchi tilini aniqlash
    user = get_user(user_id)
    user_lang = user[6] if user else 'uz'
    
    # Foydalanuvchiga xabar
    cancel_text = (
        "❌ <b>So'rovingiz bekor qilindi</b>\n\nAdmin sizning so'rovingizni bekor qildi." 
        if user_lang == 'uz' 
        else "❌ <b>Ваш запрос отменен</b>\n\nАдминистратор отменил ваш запрос."
    )
    
    try:
        await bot.send_message(user_id, cancel_text, parse_mode='HTML')
        
        # Admin xabarini yangilash
        await callback.message.edit_caption(
            callback.message.caption + "\n\n❌ <b>BEKOR QILINDI</b>",
            parse_mode='HTML'
        )
        
        await callback.answer("❌ Bekor qilindi", show_alert=True)
    except Exception as e:
        logging.error(f"Bekor qilishda xatolik: {e}")
        await callback.answer("❌ Xatolik!", show_alert=True)


# ==================== BALANCE HANDLER ====================
@router.callback_query(F.data == 'balance')
async def balance_handler(callback: CallbackQuery):
    await callback.answer()
    user = get_user(callback.from_user.id)
    lang = user[6] if user else 'uz'
    
    balance = get_cashback_balance(callback.from_user.id)
    
    text = TEXTS[lang]['balance_title'].format(balance=format_number(balance))
    
    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard(lang),
        parse_mode='HTML'
    )

# ==================== HISTORY HANDLER ====================
@router.callback_query(F.data == 'history')
async def history_handler(callback: CallbackQuery):
    await callback.answer()
    user = get_user(callback.from_user.id)
    lang = user[6] if user else 'uz'
    user_id = callback.from_user.id
    
    history = get_cashback_history(user_id)
    
    if not history:
        text = TEXTS[lang]['history_empty']
    else:
        text = "🧾 <b>Xaridlar tarixi</b>\n\n" if lang == 'uz' else "🧾 <b>История покупок</b>\n\n"
        for amount, percent, cashback, date, type_tx in history:
            type_key = f"type_{type_tx}"
            type_text = TEXTS[lang].get(type_key, type_tx)
            text += TEXTS[lang]['history_item'].format(
                date=format_date(date),
                amount=format_number(amount),
                percent=percent,
                cashback=format_number(cashback),
                type=type_text
            )
    
    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard(lang),
        parse_mode='HTML'
    )

@router.callback_query(F.data == 'location')
async def location_handler(callback: CallbackQuery):
    await callback.answer()
    user = get_user(callback.from_user.id)
    lang = user[6] if user else 'uz'
    
    if lang == 'uz':
        text = """📍 <b>SPK Systems manzillari:</b>

🏬 <b>1. SPK Do'kon (Yangi Jomi)</b>
📌 Manzil: Yangi Jomi 1 blok 19-do'kon
🕘 Ish vaqti: Har kuni 08:00 – 18:00

🏬 <b>2. SPK Do'kon (Dimax)</b>  
📌 Manzil: Dimax Nazarbek bozor 226-do'kon
🕘 Ish vaqti: Har kuni 08:00 – 18:00"""
    else:
        text = """📍 <b>Адреса SPK Systems:</b>

🏬 <b>1. Магазин SPK (Янги Джоми)</b>
📌 Адрес: Янги Джоми 1 блок 19-магазин
🕘 Время работы: Ежедневно 08:00 – 18:00

🏬 <b>2. Магазин SPK (Димах)</b>
📌 Адрес: Димах Назарбек базар 226-магазин  
🕘 Время работы: Ежедневно 08:00 – 18:00"""
    
    # Eski xabarni o'chirish
    await callback.message.delete()
    
    # Manzil haqida matn yuborish
    await callback.message.answer(text, parse_mode='HTML')
    
    # 1-lokatsiya: Yangi Jomi (koordinatalar to'g'ri)
    await callback.message.answer_location(
        latitude=41.357268,
        longitude=69.244138,
        title="📍 SPK Systems - Yangi Jomi" if lang == 'uz' else "📍 SPK Systems - Янги Джоми",
        address="Yangi Jomi 1 blok 19-do'kon" if lang == 'uz' else "Янги Джоми 1 блок 19-магазин"
    )
    
    # 2-lokatsiya: Dimax (koordinatalar to'g'ri)
    await callback.message.answer_location(
        latitude=41.311049,
        longitude=69.152031,
        title="📍 SPK Systems - Dimax" if lang == 'uz' else "📍 SPK Systems - Димах",
        address="Dimax Nazarbek bozor 226-do'kon" if lang == 'uz' else "Димах Назарбек базар 226-магазин"
    )
    
    # Orqaga tugmasi
    await callback.message.answer(
        "👇 Asosiy menyuga qaytish:" if lang == 'uz' else "👇 Вернуться в главное меню:",
        reply_markup=back_keyboard(lang)
    )

# ==================== CONTACT HANDLER ====================
@router.callback_query(F.data == 'contact')
async def contact_handler(callback: CallbackQuery):
    await callback.answer()
    user = get_user(callback.from_user.id)
    lang = user[6] if user else 'uz'
    
    if lang == 'uz':
        text = """📞 <b>Biz bilan bog'lanish:</b>

☎️ Telefon: +998338073535
💬 Telegram: https://t.me/laziz3535
"""
    else:
        text = """📞 <b>Связаться с нами:</b>

☎️ Телефон: +998338073535
💬 Telegram: https://t.me/laziz3535
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard(lang),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

@router.callback_query(F.data == 'group')
async def group_handler(callback: CallbackQuery):
    await callback.answer()
    user = get_user(callback.from_user.id)
    lang = user[6] if user else 'uz'
    
    if lang == 'uz':
        text = """🌐 <b>Bizning guruhimiz: https://t.me/+gc0Ps6bjW8llN2Iy</b>"""

    else:
        text = """🌐 <b>Наша группа: https://t.me/+gc0Ps6bjW8llN2Iy</b>"""

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard(lang),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

# ==================== MAIN ====================
async def main():
    init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())