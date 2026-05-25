import socket
import json
import threading
import os
import sys
import base64
from PySide6 import QtCore, QtWidgets, QtGui

class AppSignals(QtCore.QObject):
    chats_received = QtCore.Signal(list)
    chat_created = QtCore.Signal(str, str, int)
    chat_opened = QtCore.Signal(int, list)
    new_message = QtCore.Signal(str, str, bool)
    file_received = QtCore.Signal(str, str, int, str, bool)
    file_download_ready = QtCore.Signal(str, str)
    logged_out = QtCore.Signal()
    server_message = QtCore.Signal(str, str)

class ChatItem(QtWidgets.QFrame):
    def __init__(self, chat_name, last_message, chat_id):
        super().__init__()
        self.chat_id = chat_id
        self.setFixedHeight(70)
        self.setCursor(QtCore.Qt.PointingHandCursor)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        text_layout = QtWidgets.QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 10, 0)
        text_layout.setSpacing(0)

        self.name_label = QtWidgets.QLabel(chat_name)
        name_font = QtGui.QFont()
        name_font.setPointSize(12)
        name_font.setBold(True)
        self.name_label.setFont(name_font)

        self.message_label = QtWidgets.QLabel(last_message)
        message_font = QtGui.QFont()
        message_font.setPointSize(9)
        self.message_label.setFont(message_font)
        self.message_label.setStyleSheet("color: hsl(0,0,100);")
        self.message_label.setWordWrap(True)

        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.message_label)
        layout.addLayout(text_layout)
        layout.addStretch()

        self.setStyleSheet("""
            QFrame {
                background-color: hsl(0,0,60);
            }
            QFrame:hover {
                background-color: hsl(0,0,50);
            }
            QLabel {
                background-color: transparent;               
            }
        """)

class FileMessageWidget(QtWidgets.QFrame):
    def __init__(self, sender, file_name, message_id, sent_at, me=False):
        super().__init__()
        self.message_id = message_id
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        name_label = QtWidgets.QLabel(sender)
        name_label.setStyleSheet("color: white; font-weight: bold; font-size: 15px;")
        layout.addWidget(name_label)

        file_label = QtWidgets.QLabel(file_name)
        file_label.setStyleSheet("color: white;")
        file_label.setWordWrap(True)
        layout.addWidget(file_label)

        time_label = QtWidgets.QLabel(f"<small>{sent_at}</small>")
        time_label.setStyleSheet("color: rgba(255,255,255,0.6);")
        layout.addWidget(time_label)

        download_btn = QtWidgets.QPushButton("Download")
        download_btn.setStyleSheet("""
            QPushButton { background-color: rgba(255,255,255,0.2); color:white; border-radius:4px; padding: 4px 8px; }
            QPushButton:hover { background-color: rgba(255,255,255,0.35); }
        """)
        download_btn.clicked.connect(lambda: send_json(s, {
            "type": "request_download",
            "file_id": message_id,
            "chat_id": main_window.chat_panel.current_chat_id
        }))
        layout.addWidget(download_btn)

        if me:
            bg = "#2e86de"
        else:
            bg = "hsl(0,0,30)"

        self.setStyleSheet(f"QFrame {{ background-color:{bg}; border-radius:8px; margin:2px; }}")

class PasswordChangeWindow(QtWidgets.QWidget):
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.setWindowTitle("Change Password")
        self.setFixedSize(300, 200)

        self.setStyleSheet("""
            QWidget { background-color: hsl(0,0,60); color: white; }
            QLineEdit { background-color: hsl(0,0,50); border-radius:5px; padding:5px; color:white; }
            QPushButton { background-color: hsl(213,100%,50%); border-radius:5px; padding:8px; font-weight:bold; }
            QPushButton:hover { background-color: hsl(213,100%,60%); }
            QLabel { color:white; font-size:12pt; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.old_pass_input = QtWidgets.QLineEdit()
        self.old_pass_input.setPlaceholderText("Old Password")
        self.old_pass_input.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addWidget(self.old_pass_input)

        self.new_pass_input = QtWidgets.QLineEdit()
        self.new_pass_input.setPlaceholderText("New Password")
        self.new_pass_input.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addWidget(self.new_pass_input)

        self.confirm_btn = QtWidgets.QPushButton("Confirm")
        self.confirm_btn.clicked.connect(self.change_password)
        layout.addWidget(self.confirm_btn)

    def change_password(self):
        old_pw = self.old_pass_input.text().strip()
        new_pw = self.new_pass_input.text().strip()
        if not old_pw or not new_pw:
            QtWidgets.QMessageBox.warning(self, "Error", "Please fill in both fields")
            return
        
        send_json(s, {
            "type": "change_password",
            "username": self.username,
            "old_password": old_pw,
            "new_password": new_pw
        })
        self.close()

class LeftPanel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: hsl(0,0,60);")
        self.setFixedWidth(300)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.new_chat_btn = QtWidgets.QPushButton("＋ Add Chat")
        self.new_chat_btn.setFixedSize(130, 40)
        self.new_chat_btn.setStyleSheet("""
            QPushButton {
                background-color: hsl(213, 100%, 50%);
                font-weight: bold;
                font-size: 12pt;
                text-align: center;
            }
            QPushButton:hover {
                background-color: hsl(213, 100%, 60%);
            }
        """)
        top_row = QtWidgets.QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.new_chat_btn)
        main_layout.addLayout(top_row)

        self.new_chat_btn.clicked.connect(self.open_new_chat_window)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("border: none;")

        self.chats_container = QtWidgets.QWidget()

        self.scroll_layout = QtWidgets.QVBoxLayout(self.chats_container)
        self.scroll_layout.setContentsMargins(0,0,0,0)
        self.scroll_layout.setSpacing(5)
        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.chats_container)
        main_layout.addWidget(self.scroll_area)

        self.bottom_bar = QtWidgets.QFrame()
        self.bottom_bar.setFixedHeight(60)
        self.bottom_bar.setStyleSheet("background-color: hsl(0,0,50);")
        bottom_layout = QtWidgets.QHBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(10, 5, 10, 5)

        self.username_label = QtWidgets.QLabel(username if username else "Username")
        self.username_label.setStyleSheet("font-weight: bold; font-size: 12pt; padding-left: 8px;")
        self.username_label.setMinimumWidth(50)
        self.username_label.setMaximumWidth(130)
        self.username_label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        self.username_label.setText(self.username_label.fontMetrics().elidedText(username, QtCore.Qt.ElideRight, 200))
        bottom_layout.addWidget(self.username_label)

        bottom_layout.addStretch()

        self.menu_btn = QtWidgets.QPushButton("☰")
        self.menu_btn.setFixedSize(36, 36)
        self.menu_btn.setStyleSheet("""
            QPushButton { background-color: transparent; color: white; font-size: 18pt; border-radius: 5px; }
            QPushButton:hover { background-color: hsl(0,0,60); }
        """)
        self.menu_btn.clicked.connect(self.open_menu)
        bottom_layout.addWidget(self.menu_btn)

        main_layout.addWidget(self.bottom_bar)

    def open_menu(self):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: hsl(0,0,50); color: white; border: 1px solid hsl(0,0,40); padding: 4px; }
            QMenu::item { padding: 8px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: hsl(213,100%,50%); }
        """)
        change_pw_action = menu.addAction("Change Password")
        menu.addSeparator()
        logout_action = menu.addAction("Logout")

        action = menu.exec(self.menu_btn.mapToGlobal(
            QtCore.QPoint(0, -menu.sizeHint().height())
        ))

        if action == change_pw_action:
            self.pw_window = PasswordChangeWindow(username)
            self.pw_window.show()
        elif action == logout_action:
            send_json(s, {"type": "logout", "username": username})
            app_signals.logged_out.emit()

    def update_last_message(self, chat_id, content):
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i).widget()
            if isinstance(item, ChatItem) and item.chat_id == chat_id:
                text = content if len(content) <= 45 else content[:42] + "..."
                item.message_label.setText(text)
                break

    def add_chat(self, chat_name, last_message, chat_id):
        if not last_message:
            last_message = "Start the conversation"
        if len(last_message) > 45:
            last_message = last_message[:42] + "..."
        chat_item = ChatItem(chat_name, last_message, chat_id)
        chat_item.mousePressEvent = lambda e, cid=chat_id: main_window.open_chat(cid)
        self.scroll_layout.insertWidget(self.scroll_layout.count()-1, chat_item)

    def open_chat(self, chat_id):
        self.chat_panel.open_chat(chat_id)
        send_json(s, {"type": "open_chat", "chat_id": chat_id})

    def update_chats(self, chats):
        for c in chats:
            name = c.get("name")
            last_message = c.get("last_message", "")
            chat_id = c.get("id")
            self.add_chat(name, last_message, chat_id)
        
    def open_new_chat_window(self):
        if hasattr(self, "new_chat_window") and self.new_chat_window.isVisible():
            self.new_chat_window.raise_()
            return

        self.new_chat_window = NewChatWindow(all_users if 'all_users' in globals() else [], username)
        self.new_chat_window.show()

        send_json(s, {"type": "get_users"})

class ChatPanel(QtWidgets.QWidget):
    def __init__(self, send_callback=None):
        super().__init__()
        self.send_callback = send_callback
        self.current_chat_id = None

        main_layout = QtWidgets.QVBoxLayout(self)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.messages_container = QtWidgets.QWidget()
        self.messages_layout = QtWidgets.QVBoxLayout(self.messages_container)
        self.messages_layout.addStretch()
        self.messages_layout.setAlignment(QtCore.Qt.AlignTop)
        self.scroll_area.setWidget(self.messages_container)
        main_layout.addWidget(self.scroll_area)

        input_layout = QtWidgets.QHBoxLayout()
        self.message_input = QtWidgets.QLineEdit()
        self.message_input.setFixedHeight(36)
        self.message_input.returnPressed.connect(self._send_clicked)
        self.message_input.setPlaceholderText("Type a message...")

        self.send_button = QtWidgets.QPushButton("Send")
        self.send_button.setStyleSheet("""
            QPushButton { background-color: hsl(213,100%,50%); color:white; border-radius:5px; padding:6px 12px; font-weight:bold; }
            QPushButton:hover { background-color: hsl(213,100%,60%); }
        """)
        self.send_button.clicked.connect(self._send_clicked)

        self.file_button = QtWidgets.QPushButton("🗎")
        self.file_button.setFixedSize(36, 36)
        self.file_button.setStyleSheet("""
            QPushButton { background-color: hsl(0,0,50); color:white; border-radius:5px; font-size:14pt; }
            QPushButton:hover { background-color: hsl(0,0,60); }
        """)
        self.file_button.clicked.connect(self._send_file_clicked)

        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.file_button)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)

    def open_chat(self, chat_id):
        self.current_chat_id = chat_id
        for i in reversed(range(self.messages_layout.count() - 1)):
            widget = self.messages_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

    def add_message(self, sender, content, me=False):
        bubble = QtWidgets.QLabel(f"<b>{sender}</b><br>{content}")
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(min(500, int(self.width() * 0.65)))
        bubble.setStyleSheet(
            "padding:8px; border-radius:8px; margin:2px; background-color: #2e86de; color: white;"
            if me else
            "padding:8px; border-radius:8px; margin:2px; background-color: hsl(0,0,30); color: white;"
        )

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(4, 2, 4, 2)
        if me:
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()

        container = QtWidgets.QWidget()
        container.setLayout(row)
        container.setStyleSheet("background: transparent;")
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, container)
        self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum())

    def add_file_message(self, sender, file_name, message_id, sent_at, me=False):
        widget = FileMessageWidget(sender, file_name, message_id, sent_at, me=me)
        widget.setMaximumWidth(min(500, int(self.width() * 0.65)))

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(4, 2, 4, 2)
        if me:
            row.addStretch()
            row.addWidget(widget)
        else:
            row.addWidget(widget)
            row.addStretch()

        container = QtWidgets.QWidget()
        container.setLayout(row)
        container.setStyleSheet("background: transparent;")
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, container)
        self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum())

    def _send_clicked(self):
        text = self.message_input.text().strip()
        if text and self.send_callback and self.current_chat_id is not None:
            self.send_callback(self.current_chat_id, text)
            self.message_input.clear()

    def _send_file_clicked(self):
        if self.current_chat_id is None:
            QtWidgets.QMessageBox.warning(self, "Error", "Open a chat first")
            return
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select File")
        if not file_path:
            return
        file_name = os.path.basename(file_path)
        try:
            with open(file_path, "rb") as f:
                file_data = base64.b64encode(f.read()).decode()
            send_json(s, {
                "type": "send_file",
                "chat_id": self.current_chat_id,
                "file_name": file_name,
                "file_data": file_data
            })
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to send file: {e}")

class NewChatWindow(QtWidgets.QWidget):
    chat_created = QtCore.Signal(dict)

    def __init__(self, all_users, owner_username):
        super().__init__()
        self.setWindowTitle("Create New Chat")
        self.setFixedSize(400, 500)
        self.owner_username = owner_username

        self.setStyleSheet("""
            QWidget { background-color: hsl(0,0,60); color: white; }
            QLineEdit { background-color: hsl(0,0,50); border-radius:5px; padding:5px; color:white; }
            QPushButton { background-color: hsl(213,100%,50%); border-radius:5px; padding:8px; font-weight:bold; }
            QPushButton:hover { background-color: hsl(213,100%,60%); }
            QLabel { color:white; font-size:12pt; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setPlaceholderText("Chat Name")
        layout.addWidget(self.name_input)

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search users...")
        layout.addWidget(self.search_input)
        self.search_input.textChanged.connect(self.update_user_list)

        self.user_list_widget = QtWidgets.QListWidget()
        layout.addWidget(self.user_list_widget)

        self.all_users = all_users
        self.update_user_list()

        self.create_btn = QtWidgets.QPushButton("Create Chat")
        self.create_btn.clicked.connect(self.create_chat)
        layout.addWidget(self.create_btn)

    def update_user_list(self):
        search_text = self.search_input.text().lower()
        self.user_list_widget.clear()

        for user in self.all_users:
            if user.lower() == self.owner_username.lower():
                continue
            if search_text in user.lower():
                item = QtWidgets.QListWidgetItem(user)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Unchecked)
                self.user_list_widget.addItem(item)

    def create_chat(self):
        chat_name = self.name_input.text().strip()
        if not chat_name:
            QtWidgets.QMessageBox.warning(self, "Error", "Please enter a chat name")
            return

        selected_users = [
            self.user_list_widget.item(i).text()
            for i in range(self.user_list_widget.count())
            if self.user_list_widget.item(i).checkState() == QtCore.Qt.Checked
        ]

        if not selected_users:
            QtWidgets.QMessageBox.warning(self, "Error", "Please select at least one user")
            return

        selected_users.append(self.owner_username)

        message = {
            "type": "create_chat",
            "creator": self.owner_username,
            "users": selected_users,
            "name": chat_name
        }

        if not s:
            QtWidgets.QMessageBox.warning(self, "Error", "No server connection!")
            return
        send_json(s, message)
        self.close()

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.screen_res = QtGui.QScreen.availableSize(QtGui.QGuiApplication.primaryScreen())
        self.setMinimumSize(700, 800)
        self.setWindowTitle("Chat App")
        self.setMouseTracking(True)
        self.central_widget = QtWidgets.QWidget()
        self.central_widget.setStyleSheet("""
                background-color: hsl(0, 0, 40);
            """)
        self.setCentralWidget(self.central_widget)
        self.layout = QtWidgets.QHBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.left_panel = LeftPanel()
        self.layout.addWidget(self.left_panel)

        self.chat_panel = ChatPanel(send_callback=self.send_message_to_server)
        self.layout.addWidget(self.chat_panel)

        for i in range(self.left_panel.scroll_layout.count()-1):
            item = self.left_panel.scroll_layout.itemAt(i).widget()
            if isinstance(item, ChatItem):
                item.mousePressEvent = lambda e, chat_id=item.chat_id: self.open_chat(chat_id)

    def send_message_to_server(self, chat_id, content):
        if not s:
            print("No server connection!")
            return
        send_json(s, {
            "type": "msg",
            "chat_id": chat_id,
            "sender": self.username,
            "content": content
        })

    def open_chat(self, chat_id):
        self.chat_panel.open_chat(chat_id)
        send_json(s, {"type": "open_chat", "chat_id": chat_id})

class LoginWindow(QtWidgets.QWidget):
    login_success = QtCore.Signal(str)
    login_error = QtCore.Signal(str) 

    def __init__(self, s):
        super().__init__()
        self.s = s
        self.setFixedSize(400, 300)
        self.setWindowTitle("Login")
        self.setStyleSheet("""
            QWidget {
                background-color: hsl(0,0,60);
                color: white;
                font-size: 12pt;
            }
            QLineEdit {
                background-color: hsl(0,0,50);
                border-radius: 5px;
                padding: 5px;
                color: white;
            }
            QPushButton {
                background-color: hsl(213, 100%, 50%);
                border-radius: 5px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: hsl(213, 100%, 60%);
            }
            QLabel {
                color: white;
                font-size: 24pt;
            }
        """)

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(30, 30, 30, 30)
        self.layout.setSpacing(15)

        self.title = QtWidgets.QLabel("Chat App")
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        title_font = QtGui.QFont()
        title_font.setBold(True)
        self.title.setFont(title_font)
        self.layout.addWidget(self.title)

        self.username_input = QtWidgets.QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.layout.addWidget(self.username_input)

        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.layout.addWidget(self.password_input)

        self.login_btn = QtWidgets.QPushButton("Login")
        self.layout.addWidget(self.login_btn)

        self.register_btn = QtWidgets.QPushButton("Register")
        self.register_btn.setStyleSheet("""
            QPushButton {
                background-color: hsl(0,0,50%);
                color: white;
                border-radius: 5px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: hsl(0,0,60%);
            }
        """)
        self.layout.addWidget(self.register_btn)

        self.login_btn.clicked.connect(self.attempt_login)
        self.register_btn.clicked.connect(self.attempt_register)

    def attempt_login(self):
        global username
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        if not username or not password:
            QtWidgets.QMessageBox.warning(self, "Error", "Please fill in all inputs")
            return

        send_json(self.s, {"type": "login", "username": username, "password": password})

    def attempt_register(self):
        global username
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        if not username or not password:
            QtWidgets.QMessageBox.warning(self, "Error", "Please fill in all inputs")
            return
        
        send_json(self.s, {"type": "register", "username": username, "password": password})

class ConnectWindow(QtWidgets.QWidget):
    connected = QtCore.Signal(socket.socket)
    def __init__(self):
        super().__init__()
        self.setFixedSize(400, 300)
        self.setWindowTitle("Connect to Server")
        self.setStyleSheet("""
            QWidget {
                background-color: hsl(0,0,60);
                color: white;
                font-size: 12pt;
            }
            QLineEdit {
                background-color: hsl(0,0,50);
                border-radius: 5px;
                padding: 5px;
                color: white;
            }
            QPushButton {
                background-color: hsl(213, 100%, 50%);
                border-radius: 5px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: hsl(213, 100%, 60%);
            }
            QLabel {
                color: white;
                font-size: 24pt;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        self.title = QtWidgets.QLabel("Connect to Server")
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        title_font = QtGui.QFont()
        title_font.setBold(True)
        title_font.setPointSize(20)
        self.title.setFont(title_font)
        layout.addWidget(self.title)

        self.ip_input = QtWidgets.QLineEdit()
        self.ip_input.setPlaceholderText("Server IP")
        layout.addWidget(self.ip_input)

        self.port_input = QtWidgets.QLineEdit()
        self.port_input.setPlaceholderText("Port")
        layout.addWidget(self.port_input)

        self.connect_btn = QtWidgets.QPushButton("Connect")
        layout.addWidget(self.connect_btn)

        self.connect_btn.clicked.connect(self.__attempt_connect__)

    def __attempt_connect__(self):
        ip = self.ip_input.text().strip()
        port_text = self.port_input.text().strip()
        if not ip or not port_text:
            QtWidgets.QMessageBox.warning(self, "Error", "Please fill in all inputs")
            return
        try:
            port = int(port_text)
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Error", "Port must be a number")
            return
        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((ip, port))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Error connecting: {e}")
            s.close()
            return
        
        self.connected.emit(s)
        self.close()

def send_json(socket, message):
        try:
            data = json.dumps(message).encode()
            socket.sendall(len(data).to_bytes(4, "big"))
            socket.sendall(data)
        except Exception as e:
            print(f"Error sending json to server - {e}")
            return False
        return True

def recv_json(socket):
    try:
        length_bytes = socket.recv(4)
        length = int.from_bytes(length_bytes, "big")
        data = b""
        while len(data) < length:
            chunk = socket.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        return json.loads(data.decode())
    except Exception as e:
        print(f"Error recieving message from server - {e}")

def clear_console():
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')

def listener():
    while True:
        try:
            msg = recv_json(s)

            if msg is None:
                print("Disconnected from the server")
                break
            msg_type = msg.get("type")

            if msg_type == "success" or msg_type == "error":
                level = "info" if msg_type == "success" else "error"
                app_signals.server_message.emit(level, msg.get("content", ""))

            elif msg_type == "loginsuccess":
                login_window.login_success.emit(msg.get("content"))

            elif msg_type == "loginerror":
                login_window.login_error.emit(msg.get("content"))

            elif msg_type == "users_got":
                global all_users
                all_users = msg.get("users", [])
                if main_window and hasattr(main_window.left_panel, "new_chat_window"):
                    win = main_window.left_panel.new_chat_window
                    if win.isVisible():
                        win.all_users = all_users
                        win.update_user_list()

            elif msg_type == "chats_got":
                app_signals.chats_received.emit(msg.get("chats", []))

            elif msg_type == "chat_open":
                global current_chat_id
                current_chat_id = msg.get("chat_id")
                app_signals.chat_opened.emit(current_chat_id, msg.get("messages", []))

            elif msg_type == "chat_created":
                app_signals.chat_created.emit(
                    msg.get("chat_name", ""),
                    msg.get("last_message", ""),
                    msg.get("chat_id")
                )

            elif msg_type == "new_msg":
                chat_id = msg.get("chat_id")
                if chat_id == current_chat_id:
                    me = msg.get("sender") == username
                    app_signals.new_message.emit(msg.get("sender"), msg.get("content"), me)

            elif msg_type == "new_file":
                chat_id = msg.get("chat_id")
                if chat_id == current_chat_id:
                    me = msg.get("sender") == username
                    app_signals.file_received.emit(
                        msg.get("sender"), msg.get("file_name"),
                        msg.get("message_id"), msg.get("sent_at", ""), me
                    )

            elif msg_type == "file_download":
                file_name = msg.get("file_name")
                file_data = msg.get("file_data")
                app_signals.file_download_ready.emit(file_name, file_data)

            elif msg_type == "disconnect":
                print(f"Disconnected from the server - {msg.get('content')}")

        except Exception as e:
            print("Error receiving message:", e)

def _handle_download(file_name, file_data):
    save_path, _ = QtWidgets.QFileDialog.getSaveFileName(None, "Save File", file_name)
    if not save_path:
        return
    try:
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(file_data))
    except Exception as e:
        QtWidgets.QMessageBox.warning(None, "Error", f"Failed to save file: {e}")

def _on_chat_opened(chat_id, msgs):
    main_window.chat_panel.open_chat(chat_id)
    for m in msgs:
        me = m["sender"] == username
        if m.get("file_name"):
            main_window.chat_panel.add_file_message(m["sender"], m["file_name"], m["message_id"], m.get("sent_at", ""), me)
        else:
            main_window.chat_panel.add_message(m["sender"], m["content"] or "", me)

def handle_login_success(user):
    global username, main_window
    username = user
    main_window = MainWindow()
    main_window.username = username
    main_window.left_panel.username_label.setText(username)
    main_window.show()
    login_window.close()
    app_signals.chats_received.connect(main_window.left_panel.update_chats)
    app_signals.chat_created.connect(lambda name, last, cid: main_window.left_panel.add_chat(name, last, cid))

    app_signals.chat_opened.connect(_on_chat_opened)

    app_signals.new_message.connect(
        lambda sender, content, me: main_window.chat_panel.add_message(sender, content, me)
    )
    app_signals.file_received.connect(
        lambda sender, fname, mid, sat, me: main_window.chat_panel.add_file_message(sender, fname, mid, sat, me)
    )
    app_signals.file_download_ready.connect(_handle_download)

    app_signals.server_message.connect(lambda level, content:
        QtWidgets.QMessageBox.warning(main_window, "Success" if level == "info" else "Error", content)
    ) 

    app_signals.new_message.connect(lambda sender, content, me:
        main_window.left_panel.update_last_message(current_chat_id, content)
    )
   
    send_json(s, {"type": "get_chats", "user": username})

def do_logout():
    global main_window, username, current_chat_id, s, connect_window

    username = None
    current_chat_id = None

    try:
        app_signals.chats_received.disconnect()
    except:
        pass
    try:
        app_signals.chat_created.disconnect()
    except:
        pass
    try:
        app_signals.chat_opened.disconnect()
    except:
        pass
    try:
        app_signals.new_message.disconnect()
    except:
        pass
    try:
        app_signals.file_received.disconnect()
    except:
        pass
    try:
        app_signals.file_download_ready.disconnect()
    except:
        pass
    try:
        app_signals.server_message.disconnect()
    except:
        pass

    connect_window = ConnectWindow()
    connect_window.connected.connect(start_login)
    connect_window.show()

    if main_window:
        main_window.close()
        main_window = None

    try:
        s.close()
    except Exception:
        pass

    s = None

def start_login(connected_socket):
    global s, login_window, main_window
    s = connected_socket
    threading.Thread(target=listener, daemon=True).start()

    login_window = LoginWindow(s)
    login_window.show()

    login_window.login_success.connect(handle_login_success)
    login_window.login_error.connect(lambda err: QtWidgets.QMessageBox.warning(login_window, "Login Failed", err))

if __name__ == "__main__":

    login_window = None
    main_window = None
    current_chat_id = None
    username = None
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    app_signals = AppSignals()
    app_signals.logged_out.connect(do_logout) 
    connect_window = ConnectWindow()
    connect_window.connected.connect(start_login)
    connect_window.show()

    sys.exit(app.exec())
