# plugin_loader.py
import sys
import os,traceback
import json
import importlib
import inspect
import re
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QComboBox, QLineEdit, QListWidget, QListWidgetItem, 
                               QCheckBox, QLabel, QSizePolicy,QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from modules.types import PluginBase,PlaylistItem
from modules.other import LocalSaveDir
from modules import extractors 

class PluginLoader:
    def __init__(self,config, plugins_dir_name="plugins"):
        if "__compiled__" in globals():
            self.base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        else:
            self.base_dir = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))

        if (config.get("plugins")==None):
            config["plugins"]={}

        self.config=config

        self.plugins_dir_name = plugins_dir_name
        self.plugins_dir = os.path.join(self.base_dir, plugins_dir_name)
        self.loaded_plugins = []
        self.extractor_plugins = []

        if self.base_dir not in sys.path:
            sys.path.insert(0, self.base_dir)

    def init_all(self, context):
        for plugin_instance in self.loaded_plugins:
                if(hasattr(plugin_instance, 'init_plugin')):
                    try:
                        plugin_instance.init_plugin()
                    except Exception as e:
                        details = traceback.format_exc()
                        print(f"Ошибка иницизилации: {details}")
                        box = QMessageBox()
                        box.setIcon(QMessageBox.Critical)
                        box.setWindowTitle("Plugin Manager")
                        box.setText(details)#"Plugin "+str(plugin_id))
                        #box.setDetailedText(details)
                        box.exec()


    def load_allowed(self, context):
        if not os.path.exists(self.plugins_dir):
            try:
                os.makedirs(self.plugins_dir)
                return
            except PermissionError:
                self.plugins_dir=os.path.join(LocalSaveDir(),"plugins")

            try:
                if not os.path.exists(self.plugins_dir):
                    os.makedirs(self.plugins_dir)
                    return
            except PermissionError:
                return
        
        for item in os.listdir(self.plugins_dir):
            item_path = os.path.join(self.plugins_dir, item)

            
            if os.path.isdir(item_path) and not item.startswith(('.', '_')):
                try:
                    with open(os.path.join(item_path, "meta.json"), "r", encoding="utf-8") as f:
                        plugin_id = json.load(f).get("Id")
                except:
                    continue

                if(self.config["plugins"].get(plugin_id)):
                    if os.path.exists(os.path.join(item_path, "index.py")):
                        self._load_plugin_from_folder(item, context)

    def _load_plugin_from_folder(self, folder_name, context):
        try:

            # "plugins.hello_world_plugin.main_plugin"
            module_path = f"{self.plugins_dir_name}.{folder_name}.index"
            
            module = importlib.import_module(module_path)

            for attribute_name in dir(module):
                print(module)
                attribute = getattr(module, attribute_name)
                
                if (inspect.isclass(attribute) and 
                    issubclass(attribute, PluginBase) and 
                    attribute is not PluginBase):
                    
                    plugin_instance = attribute(context)
                    if(hasattr(plugin_instance, 'awake_plugin')):
                        plugin_instance.awake_plugin()

                    if(hasattr(plugin_instance, 'extractor_plugin')):
                        self.extractor_plugins.append(plugin_instance.extractor_plugin())
                    
                    self.loaded_plugins.append(plugin_instance)
                    print(f"✅ Загружен плагин: {folder_name}")
                    return

        except Exception as e:
            details = traceback.format_exc()
            print(f"Ошибка загрузки из папки {folder_name}: {details}")


    def Source_resolver(self,url):
        for extractor in self.extractor_plugins:
            detection=extractor.TypeDetector(url)
            print(detection)
            if(detection):
                return detection,extractor.source
                
        return None,None

    def find_resolver(self,
                    index: int,
                    item: PlaylistItem,
                    signals:  extractors.ResolveSignals,
                    cookie_browser: str = "",
                    proxy:dict = {},
                    type=None
                ):
        for extractor in self.extractor_plugins:
            if(extractor.source==item.source_id):
                return extractor.ResolveTask(index,item.page_url,signals,extractor.session,proxy)
                
        return extractors.ResolveTask(index,item.page_url,signals,cookie_browser,proxy=proxy,type=type)



class PluginManagerWidget(QWidget):
    def __init__(self,plugins_dir,config={}):
        super().__init__()
        self.setWindowTitle("Менеджер плагинов")
        self.resize(800, 600)
        
        # --- Пути ---
        self.plugins_dir = Path(plugins_dir)
        self.settings_file = Path("settings.json")

        if (config.get("plugins")==None):
            config["plugins"]={}
        
        # --- Данные ---

        self.config=config
        self.plugins_data = {}   
        self.initial_states = {}
        self.ui_items = {}       

        self.setStyleSheet("""
            QWidget {
                font-family: "Segoe UI", Arial, sans-serif; font-size: 13px;
            }
            QComboBox, QLineEdit {
                background-color: #0e0e0e; border: 1px solid #333333; padding: 4px;
            }
            QComboBox::drop-down { border-left: 1px solid #333333; }
            QListWidget {
                background-color: #0e0e0e; border: 1px solid #333333; outline: none;
            }
            QListWidget::item {
                border-bottom: 1px solid #333333;
                background-color: #151515;
            }
            QListWidget::item:hover { 
                background-color: #1e1e1e; 
            }
            QCheckBox::indicator {
                width: 15px; height: 15px; border: 1px solid #555;
                background: #222; border-radius: 2px;
            }
            QCheckBox::indicator:checked { background: #555; }
        """)

        self._load_plugins()     
        
        # Фиксируем начальное состояние для проверки перезагрузки
        self.initial_states = dict(self.config["plugins"])
        
        self._init_ui()
        self._populate_list()
        self._update_all_colors() 
        self._apply_filters()

    def _save_settings(self):
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(self.config["plugins"], f, indent=4)

    def _load_plugins(self):
        if not self.plugins_dir.exists():
            return
        for folder in self.plugins_dir.iterdir():
            if folder.is_dir():
                meta_path = folder / "meta.json"
                icon_path = folder / "icon.png"
                if meta_path.exists():
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            plugin_id = meta.get("Id")
                            if plugin_id:
                                meta["icon_path"] = str(icon_path) if icon_path.exists() else None
                                self.plugins_data[plugin_id] = meta
                    except Exception as e:
                        print(f"Ошибка загрузки плагина: {e}")

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # --- Верхняя панель (Фильтры) ---
        top_layout = QHBoxLayout()
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Все", "Включённые", "Отключённые"])
        self.filter_combo.setFixedWidth(120)
        # Подключаем комбобокс к функции фильтрации
        self.filter_combo.currentIndexChanged.connect(self._apply_filters)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск...")
        # Подключаем строку поиска к функции фильтрации
        self.search_input.textChanged.connect(self._apply_filters)
        
        top_layout.addWidget(self.filter_combo)
        top_layout.addWidget(self.search_input)
        main_layout.addLayout(top_layout)
        
        # --- Сообщение о перезагрузке (Скрыто по умолчанию) ---
        self.restart_label = QLabel("Требуется перезагрузка программы для применения изменений")
        self.restart_label.setStyleSheet("""
            background-color: #2a1b00; 
            color: #ffa500; 
            border: 1px solid #ffa500; 
            padding: 6px; 
            border-radius: 4px;
            font-weight: bold;
        """)
        self.restart_label.setAlignment(Qt.AlignCenter)
        self.restart_label.hide() 
        main_layout.addWidget(self.restart_label)

        # --- Список ---
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(0) 
        main_layout.addWidget(self.list_widget)

    def _populate_list(self):
        for pid, meta in self.plugins_data.items():
            self._add_plugin_widget(pid, meta)

    def _add_plugin_widget(self, pid, meta):
        item_widget = QWidget()
        item_widget.setFixedHeight(130) 
        item_widget.setStyleSheet("background-color: transparent;")
        
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(15, 10, 15, 10)
        item_layout.setSpacing(15)

        # 1. Чекбокс
        checkbox = QCheckBox()
        is_enabled = self.config["plugins"].get(pid, False)
        checkbox.setChecked(is_enabled)
        checkbox.toggled.connect(lambda checked, p=pid: self._on_plugin_toggled(p, checked))
        item_layout.addWidget(checkbox, alignment=Qt.AlignVCenter)

        # 2. Иконка
        icon_label = QLabel()
        icon_label.setFixedSize(64, 64)
        icon_label.setAlignment(Qt.AlignCenter)
        
        if meta.get("icon_path"):
            pixmap = QPixmap(meta["icon_path"])
            if not pixmap.isNull():
                icon_label.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                icon_label.setStyleSheet("background-color: #333333; border-radius: 6px;")
        else:
            icon_label.setStyleSheet("background-color: #333333; border-radius: 6px; font-size: 24px;")
            icon_label.setText("📦")
            
        item_layout.addWidget(icon_label, alignment=Qt.AlignVCenter)

        # 3. Текст
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        text_layout.setAlignment(Qt.AlignTop) 
        
        title_label = QLabel(meta.get("Name", "Unknown Plugin"))
        author_label = QLabel(meta.get("Author", "Unknown Author"))
        desc_label = QLabel(meta.get("Description", ""))
        desc_label.setWordWrap(True) 
        deps_label = QLabel()
        deps_label.setWordWrap(True) 
        
        title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        desc_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        deps_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        text_layout.addWidget(title_label)
        text_layout.addWidget(author_label)
        text_layout.addWidget(desc_label)
        text_layout.addWidget(deps_label)
        
        item_layout.addLayout(text_layout)
        
        self.ui_items[pid] = {
            "title": title_label,
            "desc": desc_label,
            "author": author_label,
            "deps": deps_label
        }

        list_item = QListWidgetItem(self.list_widget)
        list_item.setSizeHint(item_widget.sizeHint()) 
        # ВАЖНО: сохраняем Id плагина в самом элементе списка, чтобы искать по нему
        list_item.setData(Qt.UserRole, pid) 
        
        self.list_widget.addItem(list_item)
        self.list_widget.setItemWidget(list_item, item_widget)

    def _on_plugin_toggled(self, pid, checked):
        self.config["plugins"][pid] = checked
        self._save_settings()
        self._update_all_colors()
        self._check_restart_needed() # Проверяем, изменилось ли состояние
        self._apply_filters()        # Обновляем фильтр (вдруг мы в режиме "Отключённые" и включили плагин)

    def _check_restart_needed(self):
        """Проверяет, отличаются ли текущие настройки от тех, что были при запуске"""
        needs_restart = False
        
        for pid in self.plugins_data.keys():
            # Берем изначальное состояние (по умолчанию False, если плагина не было в настройках)
            initial = self.initial_states.get(pid, False)
            current = self.config["plugins"].get(pid, False)
            
            if initial != current:
                needs_restart = True
                break
                
        self.restart_label.setVisible(needs_restart)

    def _apply_filters(self):
        """Фильтрует список плагинов по статусу и поисковому запросу"""
        search_text = self.search_input.text().lower().strip()
        filter_mode = self.filter_combo.currentText()
        
        # Перебираем все элементы в списке
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            pid = item.data(Qt.UserRole)
            meta = self.plugins_data[pid]
            is_enabled = self.config["plugins"].get(pid, False)
            
            show_item = True
            
            # 1. Проверка комбобокса (Включенные / Отключенные)
            if filter_mode == "Включённые" and not is_enabled:
                show_item = False
            elif filter_mode == "Отключённые" and is_enabled:
                show_item = False
                
            # 2. Проверка поиска (если фильтр чекбоксов уже не скрыл элемент)
            if show_item and search_text:
                name = meta.get("Name", "").lower()
                desc = meta.get("Description", "").lower()
                author = meta.get("Author", "").lower()
                
                # Ищем совпадение в имени, описании или авторе
                if search_text not in name and search_text not in desc and search_text not in author:
                    show_item = False
                    
            # Скрываем или показываем элемент
            item.setHidden(not show_item)

    def _update_all_colors(self):
        for pid, ui in self.ui_items.items():
            meta = self.plugins_data[pid]
            deps = meta.get("dependencies", [])
            is_enabled = self.config["plugins"].get(pid, False)
            
            missing_deps = []
            
            if is_enabled:
                for dep_id in deps:
                    if dep_id not in self.plugins_data or not self.config["plugins"].get(dep_id, False):
                        missing_deps.append(dep_id)

            if missing_deps:
                ui["title"].setStyleSheet("font-weight: bold; font-size: 15px; color: #ff5555;")
                ui["desc"].setStyleSheet("color: #ff5555;")
                ui["author"].setStyleSheet("color: #ff5555;")
                
                err_text = f"ОШИБКА: Отключены или отсутствуют зависимости:\n{', '.join(missing_deps)}"
                ui["deps"].setStyleSheet("color: #ff5555; font-weight: bold; font-size: 12px;")
                ui["deps"].setText(err_text)
            else:
                ui["title"].setStyleSheet("font-weight: bold; font-size: 15px; color: #ffffff;")
                ui["desc"].setStyleSheet("color: #aaaaaa;")
                ui["author"].setStyleSheet("color: #777777;")
                
                if deps:
                    ui["deps"].setStyleSheet("color: #555555; font-size: 11px;")
                    ui["deps"].setText("Зависит от: " + ", ".join(deps))
                else:
                    ui["deps"].setText("")

    def closeEvent(self, event):
        self.hide()