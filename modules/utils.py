import sys,os
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout, QCheckBox



class proxyManager():
    """docstring for proxyManager"""
    def __init__(self, config):

        if (config==None):
            config={}

        self.SOCKS5_host = config.get("SOCKS5_host","127.0.0.1")
        self.SOCKS5_port = str(config.get("SOCKS5_port","1080"))

        self.proxyEnabled=config.get("enabled",False)

        #PROXYCHAINS_SOCKS5_HOST=127.0.0.1 PROXYCHAINS_SOCKS5_PORT=4321 proxychains 


    def restartWithProxy(self,mainwindow):
        if not(self.proxyEnabled):
            return
        LD_PRELOAD=os.environ.get("LD_PRELOAD","")

        if ("/usr/lib/libproxychains4.so" in LD_PRELOAD):
            return

        new_env = os.environ.copy()
        new_env["LD_PRELOAD"] = LD_PRELOAD+":"+"/usr/lib/libproxychains4.so"
        new_env["PROXYCHAINS_SOCKS5_HOST"] = self.SOCKS5_host
        new_env["PROXYCHAINS_SOCKS5_PORT"] = self.SOCKS5_port
        #new_env["PROXYCHAINS_QUIET_MODE"] = "1"

        args = [sys.executable] + sys.argv
        os.execve(sys.executable, args, new_env)
        mainwindow.close()
        sys.exit()

    def get(self):
        if(self.proxyEnabled):
            return {"host":self.SOCKS5_host,"port":self.SOCKS5_port}
        else:
            return {}

class InputDialog(QDialog):
    def __init__(self, hostAdress="", token_line=""):
        super().__init__()
        self.setWindowTitle("SOCKS5  Setup")
        self.setFixedSize(400, 200)
        
        # Поля ввода
        self.hostAdress_line = QLineEdit()
        self.portAdress_line = QLineEdit()
        self.portAdress_line.setMaximumWidth(80)
        self.login_line = QLineEdit()
        self.password_line = QLineEdit()

        self.hostAdress_line.setText(str(hostAdress))
        self.login_line.setText(str(token_line))
        self.password_line.setText(str(token_line))
        
        # Компоновка формы
        layout = QVBoxLayout()
        layout_adress = QHBoxLayout()

        layout_adressHost = QVBoxLayout()
        layout_adressHost.addWidget(QLabel("Адрес сервера:"))
        layout_adressHost.addWidget(self.hostAdress_line)
        layout_adress.addLayout(layout_adressHost)

        layout_adressPort = QVBoxLayout()
        layout_adressPort.addWidget(QLabel("Порт:"))
        layout_adressPort.addWidget(self.portAdress_line)
        layout_adress.addLayout(layout_adressPort)

        layout.addLayout(layout_adress)


        layout_loginData = QHBoxLayout()

        layout_login = QVBoxLayout()
        layout_login.addWidget(QLabel("Логин:"))
        layout_login.addWidget(self.login_line)
        layout_loginData.addLayout(layout_login)

        layout_password = QVBoxLayout()
        layout_password.addWidget(QLabel("Пароль:"))
        layout_password.addWidget(self.password_line)
        layout_loginData.addLayout(layout_password)

        layout.addLayout(layout_loginData)
        
        # Кнопки ОК и Отмена
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("Применить")
        self.cancel_btn = QPushButton("Отмена")
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addStretch(1) 
        self.checkbox = QCheckBox("Включить прокси")
        layout.addWidget(self.checkbox)
        
        layout.addLayout(btn_layout)

        self.setLayout(layout)
        
        # Сигналы кнопок
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        
    def get_data(self):
        return self.hostAdress_line.text(), self.token_line.text()





def main() -> int:

    app = QApplication(sys.argv)

    window = InputDialog()
    window.show() 
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
