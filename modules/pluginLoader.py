# plugin_loader.py
import sys
import os,traceback
import importlib
import inspect

from modules.types import PluginBase 

class PluginLoader:
    def __init__(self, plugins_dir_name="plugins"):
        if "__compiled__" in globals():
            self.base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        else:
            self.base_dir = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))
        self.plugins_dir_name = plugins_dir_name
        self.plugins_dir = os.path.join(self.base_dir, plugins_dir_name)
        self.loaded_plugins = []

        if self.base_dir not in sys.path:
            sys.path.insert(0, self.base_dir)

    def load_all(self, context):
        if not os.path.exists(self.plugins_dir):
            os.makedirs(self.plugins_dir)
            return

        for item in os.listdir(self.plugins_dir):
            item_path = os.path.join(self.plugins_dir, item)
            
            if os.path.isdir(item_path) and not item.startswith(('.', '_')):
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
                    plugin_instance.init_plugin()
                    
                    self.loaded_plugins.append(plugin_instance)
                    print(f"✅ Загружен плагин: {folder_name}")
                    return

        except Exception as e:
            details = traceback.format_exc()
            print(f"Ошибка загрузки из папки {folder_name}: {details}")