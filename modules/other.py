import random,hashlib
import psutil,os,sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout,
    QHBoxLayout, QGraphicsOpacityEffect, QLabel, QGraphicsBlurEffect
)
from PySide6.QtGui import QColor,QPixmap, QPainter, QLinearGradient, QImage
from PySide6.QtCore import QPropertyAnimation, QRect, QEasingCurve, Qt,QObject, QProcess,QParallelAnimationGroup
import requests
import __main__ 
import re
from urllib.parse import parse_qs, urlparse

class GradientImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_pixmap = QPixmap()
        # ОТКЛЮЧАЕМ стандартное искажающее растягивание Qt
        self.setScaledContents(False) 

        self.blur_effect = QGraphicsBlurEffect()
        self.blur_effect.setBlurRadius(16)
        self.setGraphicsEffect(self.blur_effect)
        
    def set_new_image(self, image_source):
        """Динамически принимает путь к файлу (str) или готовый QPixmap"""
        if isinstance(image_source, QPixmap):
            self.original_pixmap = image_source
        else:
            self.original_pixmap = QPixmap(str(image_source))
            
        self.update_gradient_mask()

    def update_gradient_mask(self):
        if self.original_pixmap.isNull():
            return

        # Получаем текущие размеры самого виджета QLabel
        target_width = self.width()
        target_height = self.height()
        
        if target_width <= 0 or target_height <= 0:
            return

        # 1. Конвертируем оригинал в QImage с поддержкой Альфа-канала
        src_image = self.original_pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        
        # 2. РАСЧЕТ КАДРИРОВАНИЯ И ЦЕНТРИРОВАНИЯ (Аналог object-fit: cover)
        src_width = src_image.width()
        src_height = src_image.height()
        
        # Вычисляем коэффициенты масштабирования
        scale_w = target_width / src_width
        scale_h = target_height / src_height
        scale = max(scale_w, scale_h) # Берем максимальный, чтобы залить всю площадь
        
        # Размеры картинки после пропорционального масштабирования
        new_w = int(src_width * scale)
        new_h = int(src_height * scale)
        
        # Масштабируем исходное изображение сглаженным алгоритмом
        scaled_image = src_image.scaled(new_w, new_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        
        # Находим координаты для вырезания центральной части (центрирование)
        crop_x = (new_w - target_width) // 2
        crop_y = (new_h - target_height) // 2
        
        # Вырезаем кадр точно под размер QLabel
        cropped_image = scaled_image.copy(QRect(crop_x, crop_y, target_width, target_height))

        # 3. НАЛОЖЕНИЕ ГРАДИЕНТА ПРОЗРАЧНОСТИ
        # Создаем пустой холст строго под размер QLabel и заливаем прозрачностью
        result_image = QImage(target_width, target_height, QImage.Format.Format_ARGB32_Premultiplied)
        result_image.fill(QColor(0, 0, 0, 0)) 
        
        painter = QPainter(result_image)
        # Рисуем уже отцентрированный и обрезанный кадр
        painter.drawImage(0, 0, cropped_image)
        
        # Применяем маску прозрачности
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        
        # Линейный градиент сверху вниз по размеру виджета
        gradient = QLinearGradient(0, 0, 0, target_height)
        gradient.setColorAt(0.95, QColor(0, 0, 0, 0))    # Прозрачный верх
        gradient.setColorAt(0.6, QColor(0, 0, 0, 128))  # Непрозрачный низ
        
        painter.fillRect(result_image.rect(), gradient)
        painter.end()
        
        # Выводим в QLabel
        self.setPixmap(QPixmap.fromImage(result_image))

    def resizeEvent(self, event):
        """При ресайзе картинка автоматически перекадрируется и центрируется заново"""
        super().resizeEvent(event)
        self.update_gradient_mask()



def parse_youtube_link(url):
    # Паттерн для чистого плейлиста (начинается с playlist?list=)
    playlist_pattern = r'(?:https?:\/\/)?(?:www\.|m\.)?youtube\.com\/playlist\?(?:.*&)?list=([a-zA-Z0-9_-]+)'
    
    # Паттерн для видео (обычное, мобильное, короткое youtu.be или shorts)
    video_pattern = r'(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    
    # Паттерн для параметра list= в любой ссылке
    list_param_pattern = r'[?&]list=([a-zA-Z0-9_-]+)'

    # Проверяем, есть ли ID видео
    video_match = re.search(video_pattern, url)
    # Проверяем, есть ли ID плейлиста (как отдельный плейлист или параметр в видео)
    playlist_match = re.search(playlist_pattern, url)
    list_param_match = re.search(list_param_pattern, url)

    if video_match and list_param_match:
        return {
            "type": "video&playlist",
            "video_id": video_match.group(1),
            "playlist_id": list_param_match.group(1)
        }
    elif playlist_match:
        return {
            "type": "playlist",
            "playlist_id": playlist_match.group(1)
        }
    elif video_match:
        return {
            "type": "video",
            "video_id": video_match.group(1)
        }
    else:
        return {
            "type": "Неизвестная ссылка или не YouTube"
        }

def extract_youtube_video_id(page_url: str) -> str:
    parsed = urlparse(page_url)
    query_id = parse_qs(parsed.query).get("v", [None])[0]
    if query_id:
        return str(query_id).strip()

    path = parsed.path.strip("/")
    if parsed.netloc in {"youtu.be", "www.youtu.be"} and path:
        return path.split("/", 1)[0].strip()

    match = re.search(
        r"(?:v=|/shorts/|/live/|/embed/|youtu\.be/)([A-Za-z0-9_-]{6,})",
        page_url,
    )
    if match:
        return match.group(1).strip()

    if path:
        tail = path.split("/")[-1]
        if len(tail) >= 6:
            return tail.strip()
    return ""