"""Работа с базой данных (SQLite)"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path("bot_data.db")

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Таблица пользователей и их фильтров
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            filters TEXT DEFAULT '{}'  -- JSON с фильтрами
        )
    """)

    # Таблица отслеживаемых объявлений
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT UNIQUE,
            title TEXT,
            price INTEGER,
            rooms INTEGER,
            area REAL,
            floor TEXT,
            address TEXT,
            district TEXT,
            url TEXT,
            photo_url TEXT,
            description TEXT,
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Таблица отправленных уведомлений
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            listing_id TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
        )
    """)

    conn.commit()
    conn.close()

def get_user_filters(user_id: int) -> dict:
    """Получить фильтры пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT filters FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[0]:
        return json.loads(result[0])
    return {}

def set_user_filters(user_id: int, filters: dict):
    """Установить фильтры пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users (user_id, filters) 
        VALUES (?, ?) 
        ON CONFLICT(user_id) DO UPDATE SET filters = excluded.filters
    """, (user_id, json.dumps(filters, ensure_ascii=False)))

    conn.commit()
    conn.close()

def save_listing(listing_data: dict) -> bool:
    """Сохранить объявление. Возвращает True если новое"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO listings 
            (listing_id, title, price, rooms, area, floor, address, district, url, photo_url, description, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            listing_data["id"],
            listing_data.get("title", ""),
            listing_data.get("price", 0),
            listing_data.get("rooms", 0),
            listing_data.get("area", 0.0),
            listing_data.get("floor", ""),
            listing_data.get("address", ""),
            listing_data.get("district", ""),
            listing_data.get("url", ""),
            listing_data.get("photo_url", ""),
            listing_data.get("description", ""),
            listing_data.get("published_at", datetime.now().isoformat())
        ))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def was_notified(user_id: int, listing_id: str) -> bool:
    """Проверить, отправлялось ли уже уведомление"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM notifications WHERE user_id = ? AND listing_id = ?",
        (user_id, listing_id)
    )
    result = cursor.fetchone() is not None
    conn.close()
    return result

def mark_notified(user_id: int, listing_id: str):
    """Отметить уведомление как отправленное"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO notifications (user_id, listing_id) VALUES (?, ?)",
        (user_id, listing_id)
    )
    conn.commit()
    conn.close()

def get_all_users() -> list:
    """Получить всех пользователей"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, filters FROM users")
    users = cursor.fetchall()
    conn.close()
    return users
