import socket
import json
import threading
import os
import sys
from PySide6 import QtCore, QtWidgets, QtGui

class ChatItem(QtWidgets.QFrame):
    def __init__(self, chat_name, last_message, chat_id, avatar_bytes = None):
        super().__init__()
        self.chat_id = chat_id
        self.setFixedHeight(70)
        self.setCursor(QtCore.Qt.PointingHandCursor)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        self.avatar_label = QtWidgets.QLabel()
        self.avatar_label.setFixedSize(50, 50)
        if avatar_bytes:
            pixmap = QtGui.QPixmap()
            pixmap.loadFromData(avatar_bytes)
            pixmap = pixmap.scaled(50, 50, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
        else:
            pixmap = QtGui.QPixmap(50, 50)
            pixmap.fill(QtGui.QColor("gray"))
        self.avatar_label.setPixmap(pixmap)
        self.avatar_label.setScaledContents(True)
        layout.addWidget(self.avatar_label)

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

        self.old_pw_input = QtWidgets.QLineEdit()
        self.old_pw_input.setPlaceholderText("Old Password")
        self.old_pw_input.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addWidget(self.old_pw_input)

        self.new_pw_input = QtWidgets.QLineEdit()
        self.new_pw_input.setPlaceholderText("New Password")
        self.new_pw_input.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addWidget(self.new_pw_input)

        self.confirm_btn = QtWidgets.QPushButton("Confirm")
        self.confirm_btn.clicked.connect(self.change_password)
        layout.addWidget(self.confirm_btn)

    def change_password(self):
        old_pw = self.old_pw_input.text().strip()
        new_pw = self.new_pw_input.text().strip()
        if not old_pw or not new_pw:
            QtWidgets.QMessageBox.warning(self, "Error", "Please fill in both fields")
            return
        send_json(s, {
            "type": "change_password",
            "username": self.username,
            "old_password": old_pw,
            "new_password": new_pw
        })
        QtWidgets.QMessageBox.information(self, "Success", "Password change requested")
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
        self.username_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        self.username_label.setMinimumWidth(50)
        self.username_label.setMaximumWidth(130)
        self.username_label.setText(self.username_label.fontMetrics().elidedText(username, QtCore.Qt.ElideRight, 200))
        bottom_layout.addWidget(self.username_label)

        bottom_layout.addStretch()

        self.edit_password_btn = QtWidgets.QPushButton("Change Password")
        self.edit_password_btn.setFixedSize(120, 30)
        self.edit_password_btn.setStyleSheet("""
            QPushButton {
                background-color: hsl(213, 100%, 50%);
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: hsl(213, 100%, 60%);
            }
        """)
        self.edit_password_btn.clicked.connect(self.open_password_window)
        bottom_layout.addWidget(self.edit_password_btn)

        main_layout.addWidget(self.bottom_bar)

    def add_chat(self, chat_name, last_message, chat_id):
        chat_item = ChatItem(chat_name, last_message, chat_id)
        self.scroll_layout.insertWidget(self.scroll_layout.count()-1, chat_item)

    def update_chats(self, chats):
        for c in chats:
            name = c.get("name")
            last_message = c.get("last_message", "")
            chat_id = c.get("id")
            self.add_chat(name, last_message, chat_id)
        
    def open_new_chat_window(self):
        self.new_chat_window = NewChatWindow([], username)
        self.new_chat_window.show()
        send_json(s, {"type": "get_users"})

    def open_password_window(self):
        self.pw_window = PasswordChangeWindow(username)
        self.pw_window.show()

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
        self.send_button = QtWidgets.QPushButton("Send")
        self.send_button.clicked.connect(self._send_clicked)
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)

        main_layout.addLayout(input_layout)

    def open_chat(self, chat_id):
        self.current_chat_id = chat_id
        for i in reversed(range(self.messages_layout.count() - 1)):
            widget = self.messages_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

    def add_message(self, sender, content, me=False):
        label = QtWidgets.QLabel(f"<b>{sender}:</b> {content}")
        label.setWordWrap(True)
        label.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Raised)
        if me:
            label.setStyleSheet("padding:5px; margin:2px; background-color:#a8e6cf; border-radius:5px;")
        else:
            label.setStyleSheet("padding:5px; margin:2px; background-color:#e0e0e0; border-radius:5px;")
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, label)
        self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum())

    def _send_clicked(self):
        text = self.message_input.text().strip()
        if text and self.send_callback and self.current_chat_id is not None:
            self.send_callback(self.current_chat_id, text)
            self.add_message("Me", text, me=True)
            self.message_input.clear()

class NewChatWindow(QtWidgets.QWidget):
    chat_created = QtCore.Signal(dict)

    def __init__(self, all_users, owner_username):
        super().__init__()
        self.setWindowTitle("Create New Chat")
        self.setFixedSize(400, 500)
        self.owner_username = owner_username
        self.selected_users = set()

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

        self.avatar_btn = QtWidgets.QPushButton("Select Chat Picture")
        self.avatar_btn.clicked.connect(self.select_avatar)
        self.avatar_pixmap = None
        layout.addWidget(self.avatar_btn)

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

    def select_avatar(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Chat Picture", "", "Images (*.png *.jpg *.jpeg)")
        if file_path:
            pixmap = QtGui.QPixmap(file_path)
            self.avatar_pixmap = pixmap.scaled(50, 50, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self.avatar_btn.setText("Picture Selected")

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

        selected_users = [self.user_list_widget.item(i).text() 
                          for i in range(self.user_list_widget.count()) 
                          if self.user_list_widget.item(i).checkState() == QtCore.Qt.Checked]

        if not selected_users:
            QtWidgets.QMessageBox.warning(self, "Error", "Please select at least one user")
            return

        selected_users.append(self.owner_username)

        chat_data = {
            "name": chat_name,
            "users": selected_users,
            "avatar": None
        }

        if self.avatar_pixmap:
            ba = QtCore.QByteArray()
            buffer = QtCore.QBuffer(ba)
            buffer.open(QtCore.QIODevice.WriteOnly)
            self.avatar_pixmap.save(buffer, "PNG")
            chat_data["avatar"] = ba.data()

        self.chat_created.emit(chat_data)
        self.close()

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.screen_res = QtGui.QScreen.availableSize(QtGui.QGuiApplication.primaryScreen())
        self.setMinimumSize(700, 800)
        self.setWindowTitle("Chat App")
        self.setMouseTracking(True)
        self.resize_margin = 15
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

    def __center_on_screen__(self):
        self.move(int((self.screen_res.width() / 2) - (self.frameSize().width() / 2)), int((self.screen_res.height() / 2) - (self.frameSize().height() / 2)))

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
    try:
        msg = recv_json(s)
        if msg is None:
            print("Disconnected from the server")
        msg_type = msg.get("type")
        if msg_type == "success" or msg_type == "error":
            print(f"{msg.get('content')}")
        elif msg_type == "loginsuccess":
            login_window.login_success.emit(msg.get("content"))
        elif msg_type == "loginerror":
            login_window.login_error.emit(msg.get("content"))
        elif msg_type == "users_got":
            global all_users
            all_users = msg.get("users", [])

            if main_window:
                win = main_window.left_panel.new_chat_window
                if win:
                    win.all_users = all_users
                    win.update_user_list()
        elif msg_type == "chats_got":
            chats = msg.get("chats")
            if main_window:
                main_window.left_panel.update_chats(chats)
        elif msg_type == "chat_open":
            clear_console()
            print(f"Entered chat with id {msg.get('chat_id')}")
            current_chat_id = msg.get('chat_id')
            for m in msg.get("messages"):
                print(f"{m['sender']} : {m['content']}   {m['sent_at']}")
        elif msg_type == "new_msg":
            chat_id = msg.get("chat_id")
            if chat_id == current_chat_id:
                main_window.chat_panel.add_message(msg.get("sender"), msg.get("content"))
            else:
                print(f"New message from {msg.get('sender')} in chat {msg.get('chat_name')} [{chat_id}]")
        elif msg_type == "new_file":
            chat_id = msg.get("chat_id")
            if chat_id == current_chat_id:
                print(f"{msg.get('sender')} : File: {msg.get('file_name')} [{msg.get('message_id')}]   {msg.get('sent_at')}")
            else:
                print(f"New file from {msg.get('sender')} in chat {msg.get('chat_name')} [{chat_id}]")
        elif msg_type == "file_download":
            file_name = msg.get('file_name')
            file_size = msg.get('file_size')
            file_path = os.path.join("files", file_name)
            try:
                with open(file_path, "wb") as f:
                    bytes_read = 0
                    while bytes_read < file_size:
                        chunk = s.recv(min(4096, file_size - bytes_read))
                        if not chunk:
                            break
                        f.write(chunk)
                        bytes_read += len(chunk)
                print("File downloaded succesfully")
            except Exception as e:
                print(f"Error occured while downloading file: {e}")
        elif msg_type == "closed_chat":
            clear_console()
            print("Successfully closed chat")
        elif msg_type == "disconnect":
            print(f"Disconnected from the server - {msg.get('content')}")
    except Exception as e:
        print("Error receiving message:", e)

def start_login(connected_socket):
    global s, login_window, main_window
    s = connected_socket
    threading.Thread(target=listener, daemon=True).start()

    login_window = LoginWindow(s)
    login_window.show()

    def handle_login_success(user):
        global username, main_window
        username = user
        main_window = MainWindow()
        main_window.username = username
        main_window.left_panel.username_label.setText(username)
        main_window.show()
        login_window.close()

    login_window.login_success.connect(handle_login_success)
    login_window.login_error.connect(lambda err: QtWidgets.QMessageBox.warning(login_window, "Login Failed", err))

if __name__ == "__main__":

    login_window = None
    main_window = None
    current_chat_id = None
    username = None
    running = True
    app = QtWidgets.QApplication(sys.argv)

    connect_window = ConnectWindow()
    connect_window.connected.connect(start_login)
    connect_window.show()

    """while running:
        if not running:
            break
        comm = input("").strip()
        if comm == "help":
            print("get_chats - prints all your chats\ncreate_chat [username1] [username2] [usernameN] [group/chat name (no spaces allowed)] - creates a chat with another user\nopen_chat [chat_id] - opens chat and prints the last 50 messages\nmsg [content] - sends a message in the currently open chat\nclose_chat - closes the currently active chat\nlogout - logs you out and closes app\nclear - clears the console\nsend_file [file path to the file] - sends a file in the current chat\ndownload_file [file id] downloads the file to the files directory")
        else:
            args = comm.split(" ")
            if args[0] == "create_chat":
                if len(args) < 2:
                    print("You must enter at least one username")
                elif len(args) > 2:
                    users = args[1:-1]
                    chat_name = args[-1]
                elif len(args) == 2:
                    users = [args[1]]
                    chat_name = None
                send_json(s, {"type" : "create_chat", "creator" : username, "users" : users, "name" : chat_name})
            elif args[0] == "get_chats":
                if len(args) > 1:
                    print("Too many arguments")
                else:
                    send_json(s, {"type" : "get_chats", "user" : username})
            elif args[0] == "open_chat":
                if len(args) < 2:
                    print("You must specify chat id")
                elif len(args) > 2:
                    print("Too many arguments")
                else:
                    send_json(s, {"type" : "open_chat", "chat_id" : args[1]})
            elif args[0] == "msg":
                if len(args) < 2:
                    print("You must enter some content")
                else:
                    content = " ".join(args[1:])
                    send_json(s, {"type": "msg", "content": content})
            elif args[0] == "close_chat":
                send_json(s, {"type" : "close_chat", "user" : username})
            elif args[0] == "logout":
                running = False
            elif args[0] == "clear":
                clear_console()
            elif args[0] == "send_file":
                if not current_chat_id:
                    print("No chat currently open. Use open_chat first.")
                    continue
                if len(args) != 2:
                    print("send_file accepts exactly one argument: the file path")
                    continue
                file_path = args[1]
                if not os.path.exists(file_path):
                    print("File does not exist")
                    continue
                file_name = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                send_json(s, {"type": "send_file", "sender": username, "chat_id": current_chat_id, "file_name": file_name, "file_size": file_size})
                try:
                    with open(file_path, "rb") as f:
                        while chunk := f.read(4096):
                            s.sendall(chunk)
                    print(f"Sent file {file_name} ({file_size} bytes)")
                except Exception as e:
                    print(f"Error sending file: {e}")
            elif args[0] == "download_file":
                if len(args) != 2:
                    print("download_file accepts exactly one argument: the message id")
                else: 
                    if not current_chat_id:
                        print("No chat currently open. Use open_chat first.")
                        continue
                    try:
                        os.makedirs("files", exist_ok=True)
                        send_json(s, {"type" : "request_download", "file_id" : args[1], "chat_id" : current_chat_id})
                    except Exception as e:
                        print(f"Error while trying to download file: {e}")
            else:
                print("Invalid command")"""

    sys.exit(app.exec())