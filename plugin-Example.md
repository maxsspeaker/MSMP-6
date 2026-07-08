## Simple Example plugin class:

```python
# plugins/hello_world_plugin/index.py
import os
from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QAction
from modules.types import PluginBase
from . import helper

class FolderExamplePlugin(PluginBase):
    def init_plugin(self):
        self.my_folder = os.path.dirname(__file__)
        self.show_dialog()

    def show_dialog(self):
        QMessageBox.information(
            self.main_window, 
            "Test", 
            f"Hello world from:\n{self.my_folder}"
        )
```


```
MSMP-FoxWave/
└── plugins/               <-- Plguin folder
    └── hello_world_plugin/
        ├── index.py       <-- main plugin file
        └── helper.py      <-- yours other local modules
```