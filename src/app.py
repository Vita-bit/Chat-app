import socket
import json
import threading
import os
import sys
import base64
from PySide6 import QtCore, QtWidgets, QtGui


def send_json(sock: socket.socket, message: dict) -> bool:
    try:
        data = json.dumps(message).encode()
        sock.sendall(len(data).to_bytes(4, "big"))
        sock.sendall(data)
    except Exception as e:
        print(f"error sending json: {e}")
        return False
    return True


def recv_json(sock: socket.socket) -> dict | None:
    try:
        length_bytes = sock.recv(4)
        length = int.from_bytes(length_bytes, "big")
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        return json.loads(data.decode())
    except Exception as e:
        print(f"error receiving message: {e}")
        return None



class AppSignals(QtCore.QObject):
    chats_received    = QtCore.Signal(list)
    chat_created      = QtCore.Signal(str, str, int)
    chat_opened       = QtCore.Signal(int, list)
    new_message       = QtCore.Signal(str, str, bool)
    file_received     = QtCore.Signal(str, str, int, str, bool)
    file_download_ready = QtCore.Signal(str, str)
    logged_out        = QtCore.Signal()
    server_message    = QtCore.Signal(str, str)


class AppState:
    def __init__(self):
        self.sock: socket.socket | None = None
        self.username: str | None = None
        self.current_chat_id: int | None = None
        self.signals = AppSignals()


class ChatItem(QtWidgets.QFrame):
    def __init__(self, chat_name: str, last_message: str, chat_id: int):
        super().__init__()
        self.chat_id = chat_id
        self.setFixedHeight(70)
        self.setCursor(QtCore.Qt.PointingHandCursor)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        name_label = QtWidgets.QLabel(chat_name)
        name_font = QtGui.QFont()
        name_font.setPointSize(12)
        name_font.setBold(True)
        name_label.setFont(name_font)

        message_label = QtWidgets.QLabel(last_message)
        message_font = QtGui.QFont()
        message_font.setPointSize(9)
        message_label.setFont(message_font)
        message_label.setStyleSheet("color: hsl(0,0,100); font-weight: 500;")
        message_label.setWordWrap(True)
        self.message_label = message_label

        text_layout = QtWidgets.QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 10, 0)
        text_layout.setSpacing(0)
        text_layout.addWidget(name_label)
        text_layout.addWidget(message_label)

        layout.addLayout(text_layout)
        layout.addStretch()

        self.setStyleSheet("""
            QFrame { background-color: hsl(0,0,60); }
            QFrame:hover { background-color: hsl(0,0,50); }
            QLabel { background-color: transparent; }
        """)


class FileMessageWidget(QtWidgets.QFrame):
    def __init__(self, sender: str, file_name: str, message_id: int, sent_at: str, me: bool, state: "AppState"):
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

        time_label = QtWidgets.QLabel(sent_at)
        time_label.setStyleSheet("color: rgba(255,255,255,0.6); font-weight: 300; font-size: 10px;")
        layout.addWidget(time_label)

        download_btn = QtWidgets.QPushButton("Download")
        download_btn.setStyleSheet("""
            QPushButton { background-color: rgba(255,255,255,0.2); color: white; border-radius: 4px; padding: 4px 8px; }
            QPushButton:hover { background-color: rgba(255,255,255,0.35); }
        """)
        download_btn.clicked.connect(lambda: send_json(state.sock, {
            "type": "request_download",
            "file_id": message_id,
            "chat_id": state.current_chat_id
        }))
        layout.addWidget(download_btn)

        bg = "hsl(58,73,53)" if me else "hsl(0,0,30)"
        self.setStyleSheet(f"QFrame {{ background-color: {bg}; border-radius: 8px; margin: 2px; }}")


class PasswordChangeWindow(QtWidgets.QWidget):
    def __init__(self, state: "AppState"):
        super().__init__()
        self.state = state
        self.setWindowTitle("Change Password")
        self.setFixedSize(300, 200)
        self.setStyleSheet("""
            QWidget { background-color: hsl(0,0,60); color: white; font-size: 12pt; }
            QLineEdit { background-color: hsl(0,0,50); border-radius: 5px; padding: 5px; color: white; }
            QPushButton { background-color: hsl(213,100%,50%); border-radius: 5px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: hsl(213,100%,60%); }
            QLabel { color: white; font-size: 24pt; }
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

        confirm_btn = QtWidgets.QPushButton("Confirm")
        confirm_btn.clicked.connect(self._on_confirm)
        layout.addWidget(confirm_btn)

    def _on_confirm(self):
        old_pw = self.old_pass_input.text().strip()
        new_pw = self.new_pass_input.text().strip()
        if not old_pw or not new_pw:
            QtWidgets.QMessageBox.warning(self, "Error", "Please fill in both fields.")
            return
        send_json(self.state.sock, {
            "type": "change_password",
            "username": self.state.username,
            "old_password": old_pw,
            "new_password": new_pw
        })
        self.close()


class ChatPanel(QtWidgets.QWidget):
    def __init__(self, state: "AppState"):
        super().__init__()
        self.state = state

        main_layout = QtWidgets.QVBoxLayout(self)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        messages_container = QtWidgets.QWidget()
        self.messages_layout = QtWidgets.QVBoxLayout(messages_container)
        self.messages_layout.addStretch()
        self.messages_layout.setAlignment(QtCore.Qt.AlignTop)
        self.scroll_area.setWidget(messages_container)
        main_layout.addWidget(self.scroll_area)

        input_layout = QtWidgets.QHBoxLayout()

        self.message_input = QtWidgets.QLineEdit()
        self.message_input.setFixedHeight(36)
        self.message_input.setPlaceholderText("Type a message...")
        self.message_input.returnPressed.connect(self._on_send)

        send_button = QtWidgets.QPushButton("Send")
        send_button.setStyleSheet("""
            QPushButton { background-color: hsl(213,100%,50%); color: white; border-radius: 5px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: hsl(213,100%,60%); }
        """)
        send_button.clicked.connect(self._on_send)

        file_button = QtWidgets.QPushButton("🗎")
        file_button.setFixedSize(36, 36)
        file_button.setStyleSheet("""
            QPushButton { background-color: hsl(0,0,50); color: white; border-radius: 5px; font-size: 14pt; }
            QPushButton:hover { background-color: hsl(0,0,60); }
        """)
        file_button.clicked.connect(self._on_send_file)

        input_layout.addWidget(self.message_input)
        input_layout.addWidget(file_button)
        input_layout.addWidget(send_button)
        main_layout.addLayout(input_layout)

    def open_chat(self, chat_id: int):
        self.state.current_chat_id = chat_id
        for i in reversed(range(self.messages_layout.count() - 1)):
            widget = self.messages_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

    def add_message(self, sender: str, content: str, me: bool = False):
        bubble = QtWidgets.QLabel(f"<b>{sender}</b><br>{content}")
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(min(500, int(self.width() * 0.65)))
        if me:
            bubble.setStyleSheet("padding: 8px; border-radius: 8px; margin: 2px; background-color: #2e86de; color: white;")
        else:
            bubble.setStyleSheet("padding: 8px; border-radius: 8px; margin: 2px; background-color: hsl(0,0,30); color: white;")

        self._insert_row(bubble, me)

    def add_file_message(self, sender: str, file_name: str, message_id: int, sent_at: str, me: bool = False):
        widget = FileMessageWidget(sender, file_name, message_id, sent_at, me, self.state)
        widget.setMaximumWidth(min(500, int(self.width() * 0.65)))
        self._insert_row(widget, me)

    def _insert_row(self, widget: QtWidgets.QWidget, me: bool):
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

    def _on_send(self):
        text = self.message_input.text().strip()
        if text and self.state.current_chat_id is not None:
            send_json(self.state.sock, {
                "type": "msg",
                "chat_id": self.state.current_chat_id,
                "sender": self.state.username,
                "content": text
            })
            self.message_input.clear()

    def _on_send_file(self):
        if self.state.current_chat_id is None:
            QtWidgets.QMessageBox.warning(self, "Error", "Open a chat first")
            return
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select File")
        if not file_path:
            return
        file_name = os.path.basename(file_path)
        try:
            with open(file_path, "rb") as f:
                file_data = base64.b64encode(f.read()).decode()
            send_json(self.state.sock, {
                "type": "send_file",
                "chat_id": self.state.current_chat_id,
                "file_name": file_name,
                "file_data": file_data
            })
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to send file: {e}")


class NewChatWindow(QtWidgets.QWidget):
    def __init__(self, all_users: list, state: "AppState"):
        super().__init__()
        self.state = state
        self.all_users = all_users
        self.setWindowTitle("Create New Chat")
        self.setFixedSize(400, 500)
        self.setStyleSheet("""
            QWidget { background-color: hsl(0,0,60); color: white; font-size: 12pt; }
            QLineEdit { background-color: hsl(0,0,50); border-radius: 5px; padding: 5px; color: white; }
            QPushButton { background-color: hsl(213,100%,50%); border-radius: 5px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: hsl(213,100%,60%); }
            QLabel { color: white; font-size: 24pt; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setPlaceholderText("Chat Name")
        layout.addWidget(self.name_input)

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search users...")
        self.search_input.textChanged.connect(self._update_user_list)
        layout.addWidget(self.search_input)

        self.user_list_widget = QtWidgets.QListWidget()
        layout.addWidget(self.user_list_widget)
        self._update_user_list()

        create_btn = QtWidgets.QPushButton("Create Chat")
        create_btn.clicked.connect(self._on_create)
        layout.addWidget(create_btn)

    def _update_user_list(self):
        search = self.search_input.text().lower()
        self.user_list_widget.clear()
        for user in self.all_users:
            if user.lower() == self.state.username.lower():
                continue
            if search in user.lower():
                item = QtWidgets.QListWidgetItem(user)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Unchecked)
                self.user_list_widget.addItem(item)

    def _on_create(self):
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

        selected_users.append(self.state.username)

        if not self.state.sock:
            QtWidgets.QMessageBox.warning(self, "Error", "No server connection!")
            return

        send_json(self.state.sock, {
            "type": "create_chat",
            "creator": self.state.username,
            "users": selected_users,
            "name": chat_name
        })
        self.close()


class LeftPanel(QtWidgets.QWidget):
    def __init__(self, state: "AppState"):
        super().__init__()
        self.state = state
        self.setStyleSheet("background-color: hsl(0,0,60);")
        self.setFixedWidth(300)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        add_chat_btn = QtWidgets.QPushButton("＋ Add Chat")
        add_chat_btn.setFixedSize(130, 40)
        add_chat_btn.setStyleSheet("""
            QPushButton { background-color: hsl(213,100%,50%); font-weight: bold; font-size: 12pt; text-align: center; }
            QPushButton:hover { background-color: hsl(213,100%,60%); }
        """)
        add_chat_btn.clicked.connect(self._open_new_chat_window)

        top_row = QtWidgets.QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(add_chat_btn)
        main_layout.addLayout(top_row)

        self.chats_container = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QVBoxLayout(self.chats_container)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(5)
        self.scroll_layout.addStretch()

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("border: none;")
        scroll_area.setWidget(self.chats_container)
        main_layout.addWidget(scroll_area)

        bottom_bar = QtWidgets.QFrame()
        bottom_bar.setFixedHeight(60)
        bottom_bar.setStyleSheet("background-color: hsl(0,0,50);")
        bottom_layout = QtWidgets.QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(10, 5, 10, 5)

        self.username_label = QtWidgets.QLabel(state.username or "Username")
        self.username_label.setStyleSheet("font-weight: bold; font-size: 12pt; padding-left: 8px;")
        self.username_label.setMinimumWidth(50)
        self.username_label.setMaximumWidth(130)
        self.username_label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        if state.username:
            self.username_label.setText(
                self.username_label.fontMetrics().elidedText(state.username, QtCore.Qt.ElideRight, 200)
            )
        bottom_layout.addWidget(self.username_label)
        bottom_layout.addStretch()

        menu_btn = QtWidgets.QPushButton("☰")
        menu_btn.setFixedSize(36, 36)
        menu_btn.setStyleSheet("""
            QPushButton { background-color: transparent; color: white; font-size: 18pt; border-radius: 5px; }
            QPushButton:hover { background-color: hsl(0,0,60); }
        """)
        menu_btn.clicked.connect(self._open_menu)
        bottom_layout.addWidget(menu_btn)
        self._menu_btn = menu_btn

        main_layout.addWidget(bottom_bar)

    def _open_menu(self):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: hsl(0,0,50); color: white; border: 1px solid hsl(0,0,40); padding: 4px; }
            QMenu::item { padding: 8px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: hsl(213,100%,50%); }
        """)
        change_pw_action = menu.addAction("Change Password")
        menu.addSeparator()
        logout_action = menu.addAction("Logout")

        action = menu.exec(self._menu_btn.mapToGlobal(QtCore.QPoint(0, -menu.sizeHint().height())))

        if action == change_pw_action:
            self._pw_window = PasswordChangeWindow(self.state)
            self._pw_window.show()
        elif action == logout_action:
            send_json(self.state.sock, {"type": "logout", "username": self.state.username})
            self.state.signals.logged_out.emit()

    def add_chat(self, chat_name: str, last_message: str, chat_id: int, on_click):
        if not last_message:
            last_message = "Start the conversation"
        if len(last_message) > 45:
            last_message = last_message[:42] + "..."
        chat_item = ChatItem(chat_name, last_message, chat_id)
        chat_item.mousePressEvent = lambda e, cid=chat_id: on_click(cid)
        self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, chat_item)

    def update_last_message(self, chat_id: int, content: str):
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i).widget()
            if isinstance(item, ChatItem) and item.chat_id == chat_id:
                text = content if len(content) <= 45 else content[:42] + "..."
                item.message_label.setText(text)
                break

    def update_chats(self, chats: list, on_click):
        for c in chats:
            self.add_chat(c.get("name"), c.get("last_message", ""), c.get("id"), on_click)

    def _open_new_chat_window(self):
        if hasattr(self, "_new_chat_window") and self._new_chat_window.isVisible():
            self._new_chat_window.raise_()
            return
        self._new_chat_window = NewChatWindow([], self.state)
        self._new_chat_window.show()
        send_json(self.state.sock, {"type": "get_users"})

    def update_new_chat_users(self, users: list):
        if hasattr(self, "_new_chat_window") and self._new_chat_window.isVisible():
            self._new_chat_window.all_users = users
            self._new_chat_window._update_user_list()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, state: "AppState"):
        super().__init__()
        self.state = state
        self.setMinimumSize(700, 800)
        self.setWindowTitle("Chat App")

        central = QtWidgets.QWidget()
        central.setStyleSheet("background-color: hsl(0,0,40);")
        self.setCentralWidget(central)

        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.left_panel = LeftPanel(state)
        layout.addWidget(self.left_panel)

        self.chat_panel = ChatPanel(state)
        layout.addWidget(self.chat_panel)

    def open_chat(self, chat_id: int):
        self.chat_panel.open_chat(chat_id)
        send_json(self.state.sock, {"type": "open_chat", "chat_id": chat_id})


class LoginWindow(QtWidgets.QWidget):
    login_success = QtCore.Signal(str)
    login_error   = QtCore.Signal(str)

    def __init__(self, state: "AppState"):
        super().__init__()
        self.state = state
        self.setFixedSize(400, 300)
        self.setWindowTitle("Login")
        self.setStyleSheet("""
            QWidget { background-color: hsl(0,0,60); color: white; font-size: 12pt; }
            QLineEdit { background-color: hsl(0,0,50); border-radius: 5px; padding: 5px; color: white; }
            QPushButton { background-color: hsl(213,100%,50%); border-radius: 5px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: hsl(213,100%,60%); }
            QLabel { color: white; font-size: 24pt; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        title = QtWidgets.QLabel("Chat App")
        title.setAlignment(QtCore.Qt.AlignCenter)
        font = QtGui.QFont()
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        self.username_input = QtWidgets.QLineEdit()
        self.username_input.setPlaceholderText("Username")
        layout.addWidget(self.username_input)

        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addWidget(self.password_input)

        login_btn = QtWidgets.QPushButton("Login")
        login_btn.clicked.connect(self._on_login)
        layout.addWidget(login_btn)

        register_btn = QtWidgets.QPushButton("Register")
        register_btn.setStyleSheet("""
            QPushButton { background-color: hsl(0,0,50%); color: white; border-radius: 5px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: hsl(0,0,60%); }
        """)
        register_btn.clicked.connect(self._on_register)
        layout.addWidget(register_btn)

    def _read_inputs(self) -> tuple[str, str] | None:
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        if not username or not password:
            QtWidgets.QMessageBox.warning(self, "Error", "Please fill in all inputs")
            return None
        return username, password

    def _on_login(self):
        inputs = self._read_inputs()
        if inputs is None:
            return
        username, password = inputs
        self.state.username = username
        send_json(self.state.sock, {"type": "login", "username": username, "password": password})

    def _on_register(self):
        inputs = self._read_inputs()
        if inputs is None:
            return
        username, password = inputs
        self.state.username = username
        send_json(self.state.sock, {"type": "register", "username": username, "password": password})


class ConnectWindow(QtWidgets.QWidget):
    connected = QtCore.Signal(socket.socket)

    def __init__(self):
        super().__init__()
        self.setFixedSize(400, 300)
        self.setWindowTitle("Connect to Server")
        self.setStyleSheet("""
            QWidget { background-color: hsl(0,0,60); color: white; font-size: 12pt; }
            QLineEdit { background-color: hsl(0,0,50); border-radius: 5px; padding: 5px; color: white; }
            QPushButton { background-color: hsl(213,100%,50%); border-radius: 5px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: hsl(213,100%,60%); }
            QLabel { color: white; font-size: 24pt; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        title = QtWidgets.QLabel("Connect to Server")
        title.setAlignment(QtCore.Qt.AlignCenter)
        font = QtGui.QFont()
        font.setBold(True)
        font.setPointSize(20)
        title.setFont(font)
        layout.addWidget(title)

        self.ip_input = QtWidgets.QLineEdit()
        self.ip_input.setPlaceholderText("Server IP")
        layout.addWidget(self.ip_input)

        self.port_input = QtWidgets.QLineEdit()
        self.port_input.setPlaceholderText("Port")
        layout.addWidget(self.port_input)

        connect_btn = QtWidgets.QPushButton("Connect")
        connect_btn.clicked.connect(self._on_connect)
        layout.addWidget(connect_btn)

    def _on_connect(self):
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

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((ip, port))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Error connecting: {e}")
            sock.close()
            return

        self.connected.emit(sock)
        self.close()


class App:
    def __init__(self):
        self.state = AppState()
        self.qt_app = QtWidgets.QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)

        self.connect_window: ConnectWindow | None = None
        self.login_window: LoginWindow | None = None
        self.main_window: MainWindow | None = None

        self.state.signals.logged_out.connect(self._do_logout)

        self.connect_window = ConnectWindow()
        self.connect_window.connected.connect(self._start_login)
        self.connect_window.show()

    def run(self) -> int:
        return self.qt_app.exec()

    def _start_login(self, sock: socket.socket):
        self.state.sock = sock
        threading.Thread(target=self._listener, daemon=True).start()

        self.login_window = LoginWindow(self.state)
        self.login_window.login_success.connect(self._on_login_success)
        self.login_window.login_error.connect(
            lambda err: QtWidgets.QMessageBox.warning(self.login_window, "Login Failed", err)
        )
        self.login_window.show()

    def _on_login_success(self, username: str):
        self.state.username = username
        self.main_window = MainWindow(self.state)
        self.main_window.left_panel.username_label.setText(username)
        self.main_window.show()
        self.login_window.close()

        signals = self.state.signals
        signals.chats_received.connect(
            lambda chats: self.main_window.left_panel.update_chats(chats, self.main_window.open_chat)
        )
        signals.chat_created.connect(
            lambda name, last, cid: self.main_window.left_panel.add_chat(name, last, cid, self.main_window.open_chat)
        )
        signals.chat_opened.connect(self._on_chat_opened)
        signals.new_message.connect(
            lambda sender, content, me: self.main_window.chat_panel.add_message(sender, content, me)
        )
        signals.new_message.connect(
            lambda sender, content, me: self.main_window.left_panel.update_last_message(self.state.current_chat_id, content)
        )
        signals.file_received.connect(
            lambda sender, fname, mid, sat, me: self.main_window.chat_panel.add_file_message(sender, fname, mid, sat, me)
        )
        signals.file_download_ready.connect(self._handle_download)
        signals.server_message.connect(lambda level, content:
            QtWidgets.QMessageBox.warning(
                self.main_window,
                "Success" if level == "info" else "Error",
                content
            )
        )

        send_json(self.state.sock, {"type": "get_chats", "user": username})

    def _on_chat_opened(self, chat_id: int, msgs: list):
        self.main_window.chat_panel.open_chat(chat_id)
        for m in msgs:
            me = m["sender"] == self.state.username
            if m.get("file_name"):
                self.main_window.chat_panel.add_file_message(
                    m["sender"], m["file_name"], m["message_id"], m.get("sent_at", ""), me
                )
            else:
                self.main_window.chat_panel.add_message(m["sender"], m["content"] or "", me)

    def _handle_download(self, file_name: str, file_data: str):
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(None, "Save File", file_name)
        if not save_path:
            return
        try:
            with open(save_path, "wb") as f:
                f.write(base64.b64decode(file_data))
        except Exception as e:
            QtWidgets.QMessageBox.warning(None, "Error", f"Failed to save file: {e}")

    def _do_logout(self):
        signals = self.state.signals
        for attr in ("chats_received", "chat_created", "chat_opened", "new_message",
                     "file_received", "file_download_ready", "server_message"):
            try:
                getattr(signals, attr).disconnect()
            except Exception:
                pass

        if self.main_window:
            self.main_window.close()
            self.main_window = None

        try:
            self.state.sock.close()
        except Exception:
            pass

        self.state.sock = None
        self.state.username = None
        self.state.current_chat_id = None

        self.connect_window = ConnectWindow()
        self.connect_window.connected.connect(self._start_login)
        self.connect_window.show()

    def _listener(self):
        while True:
            try:
                msg = recv_json(self.state.sock)
                if msg is None:
                    print("disconnected from the server")
                    break

                msg_type = msg.get("type")
                signals = self.state.signals

                if msg_type in ("success", "error"):
                    level = "info" if msg_type == "success" else "error"
                    signals.server_message.emit(level, msg.get("content", ""))

                elif msg_type == "loginsuccess":
                    self.login_window.login_success.emit(msg.get("content"))

                elif msg_type == "loginerror":
                    self.login_window.login_error.emit(msg.get("content"))

                elif msg_type == "users_got":
                    users = msg.get("users", [])
                    if self.main_window:
                        self.main_window.left_panel.update_new_chat_users(users)

                elif msg_type == "chats_got":
                    signals.chats_received.emit(msg.get("chats", []))

                elif msg_type == "chat_open":
                    self.state.current_chat_id = msg.get("chat_id")
                    signals.chat_opened.emit(self.state.current_chat_id, msg.get("messages", []))

                elif msg_type == "chat_created":
                    signals.chat_created.emit(
                        msg.get("chat_name", ""),
                        msg.get("last_message", ""),
                        msg.get("chat_id")
                    )

                elif msg_type == "new_msg":
                    if msg.get("chat_id") == self.state.current_chat_id:
                        me = msg.get("sender") == self.state.username
                        signals.new_message.emit(msg.get("sender"), msg.get("content"), me)

                elif msg_type == "new_file":
                    if msg.get("chat_id") == self.state.current_chat_id:
                        me = msg.get("sender") == self.state.username
                        signals.file_received.emit(
                            msg.get("sender"), msg.get("file_name"),
                            msg.get("message_id"), msg.get("sent_at", ""), me
                        )

                elif msg_type == "file_download":
                    signals.file_download_ready.emit(msg.get("file_name"), msg.get("file_data"))

                elif msg_type == "disconnect":
                    print(f"disconnected from server: {msg.get('content')}")

            except Exception as e:
                print("error receiving message:", e)


if __name__ == "__main__":
    app = App()
    sys.exit(app.run())