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


class LocalAudioDb:
    def __init__(self, db_name="savedMusic.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                author TEXT NOT NULL,
                album TEXT,
                title TEXT NOT NULL,
                image_path TEXT,
                local_position TEXT
            )
        ''')
        self.conn.commit()

    def add_track(self, item: PlaylistItem):
        """Добавляет трек в базу данных, извлекая данные из PlaylistItem."""
        self.cursor.execute('''
            INSERT OR REPLACE INTO tracks (url, author, album, title, image_path, local_position)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            item.page_url, 
            item.uploader, 
            item.album, 
            item.title, 
            item.artwork_url, 
            item.stream_url
        ))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_track_by_url(self, url: str) -> PlaylistItem | None:
        """Ищет трек по url и возвращает его в виде готового объекта PlaylistItem."""
        self.cursor.execute('SELECT * FROM tracks WHERE url = ?', (url,))
        row = self.cursor.fetchone()
        
        if row:
            # Воссоздаем объект PlaylistItem из данных базы
            return PlaylistItem(
                page_url=row['url'],
                uploader=row['author'],
                album=row['album'] if row['album'] else "",
                title=row['title'],
                artwork_url=row['image_path'] if row['image_path'] else "",
                stream_url=row['local_position'] if row['local_position'] else ""
                # Остальные поля (duration, waveform и т.д.) примут дефолтные значения, 
                # так как они не хранятся в вашей текущей схеме БД.
            )
        return None

    def delete_track(self, url: str, delete_physical_files: bool = False):
        """Удаляет трек из базы, и (опционально) сами файлы с диска."""
        if delete_physical_files:
            self.cursor.execute('SELECT local_position, image_path FROM tracks WHERE url = ?', (url,))
            row = self.cursor.fetchone()
            if row:
                if row['local_position'] and os.path.exists(row['local_position']):
                    os.remove(row['local_position'])
                if row['image_path'] and os.path.exists(row['image_path']):
                    os.remove(row['image_path'])

        self.cursor.execute('DELETE FROM tracks WHERE url = ?', (url,))
        self.conn.commit()

    def close(self):
        self.conn.close()