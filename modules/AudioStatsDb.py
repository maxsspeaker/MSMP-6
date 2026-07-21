import sqlite3
from .types import *

class AudioStatsDb:
    def __init__(self, db_name="music.db"):
        """Инициализация подключения и создание таблицы."""
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        """Создает таблицу треков. Поле url теперь UNIQUE (уникальное)."""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                author TEXT NOT NULL,
                album TEXT,
                title TEXT NOT NULL,
                image_url TEXT,
                play_count INTEGER DEFAULT 0
            )
        ''')
        self.conn.commit()

    def increment_plays(self, item: PlaylistItem):
        """
        Увеличивает количество прослушиваний. 
        Если композиции нет в базе, автоматически создает новую запись.
        """
        # Проверяем, существует ли уже трек с таким url
        self.cursor.execute('SELECT id FROM tracks WHERE url = ?', (item.page_url,))
        row = self.cursor.fetchone()

        if row is None:
            # Если трека нет в базе, создаем новую запись сразу с 1 прослушиванием
            # uploader мапится в author, artwork_url в image_url
            self.cursor.execute('''
                INSERT INTO tracks (url, author, album, title, image_url, play_count)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (item.page_url, item.uploader, item.album, item.title, item.artwork_url))
        else:
            # Если трек уже есть, атомарно увеличиваем счетчик прослушиваний
            self.cursor.execute('''
                UPDATE tracks
                SET play_count = play_count + 1
                WHERE id = ?
            ''', (row[0],))
            
        self.conn.commit()

    def get_top_5_tracks(self):
        """Возвращает топ-5 самых часто прослушиваемых композиций (сортировка по убыванию)."""
        self.cursor.execute('''
            SELECT url, author, album, title, image_url, play_count 
            FROM tracks
            ORDER BY play_count DESC
            LIMIT 5
        ''')
        return self.cursor.fetchall()

    def get_track_by_url(self, url: str):
        """Получает информацию о треке по его URL."""
        self.cursor.execute('SELECT * FROM tracks WHERE url = ?', (url,))
        return self.cursor.fetchone()

    def close(self):
        """Закрывает соединение с базой данных."""
        self.conn.close()