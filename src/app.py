import socket
import json
import threading
import os
import sys
from PySide6 import QtCore, QtWidgets, QtGui

if __name__ == "__main__":

    HOST = input("Enter server's public / private IP address: ")
    PORT = input("Enter the port the server's running on: ")
    current_chat_id = None
    running = True
    app = QtWidgets.QApplication(sys.argv)

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.screen_res = QtGui.QScreen.availableSize(QtGui.QGuiApplication.primaryScreen())
            self.setMinimumSize(700, 800)
            self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
            self.setWindowTitle("Chat App")
            self.setMouseTracking(True)
            self.resize_margin = 15
            self.setStyleSheet("""
                background-color: hsl(0, 0, 40);
            """)

        def __center_on_screen__(self):
            self.move((self.screen_res.width() / 2) - (self.frameSize().width() / 2), (self.screen_res.height() / 2) - (self.frameSize().height() / 2))

        def __show__(self):
            self.setGeometry(0, 0, 700, 800)
            self.__center_on_screen__()
            self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
            self.show()
            self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, False)
            self.show()

        def __close__(self):
            self.setWindowState(QtCore.Qt.WindowNoState)
            self.close()

        def __minimize__(self):
            self.setWindowState(QtCore.Qt.WindowMinimized)

        def __maximize__(self):
            self.setWindowState(QtCore.Qt.WindowMaximized)

        def detect_edges(self, pos):
            rect = self.rect()
            edges = QtCore.Qt.Edges()

            left = pos.x() < self.resize_margin
            right = pos.x() > rect.width() - self.resize_margin
            top = pos.y() < self.resize_margin
            bottom = pos.y() > rect.height() - self.resize_margin

            if left:
                edges |= QtCore.Qt.LeftEdge
            if right:
                edges |= QtCore.Qt.RightEdge
            if top:
                edges |= QtCore.Qt.TopEdge
            if bottom:
                edges |= QtCore.Qt.BottomEdge

            return edges
        
        def mouseMoveEvent(self, event):
            edges = self.detect_edges(event.position().toPoint())

            if edges == (QtCore.Qt.TopEdge | QtCore.Qt.LeftEdge) or edges == (QtCore.Qt.BottomEdge | QtCore.Qt.RightEdge):
                self.setCursor(QtCore.Qt.SizeFDiagCursor)
            elif edges == (QtCore.Qt.TopEdge | QtCore.Qt.RightEdge) or edges == (QtCore.Qt.BottomEdge | QtCore.Qt.LeftEdge):
                self.setCursor(QtCore.Qt.SizeBDiagCursor)
            elif edges & (QtCore.Qt.TopEdge | QtCore.Qt.BottomEdge):
                self.setCursor(QtCore.Qt.SizeVerCursor)
            elif edges & (QtCore.Qt.LeftEdge | QtCore.Qt.RightEdge):
                self.setCursor(QtCore.Qt.SizeHorCursor)
            else:
                self.setCursor(QtCore.Qt.ArrowCursor)
        
        def mousePressEvent(self, event):
            if event.button() == QtCore.Qt.LeftButton:
                edges = self.detect_edges(event.position().toPoint())

                if edges:
                    self.windowHandle().startSystemResize(edges)
                else:
                    self.windowHandle().startSystemMove()

    class CustomTitleBar(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.title = "Chat App"
            #self.icon = 

        def __show__(self):
            self.show()

    main_window = MainWindow()

    while True:
        test = input()
        if test == "open":
            main_window.__show__()
        elif test == "close":
            main_window.__close__()
        elif test == "min":
            main_window.__minimize__()
        elif test == "max":
            main_window.__maximize__()
        else:
            print("Invalid")

    """def send_json(socket, message):
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
        while running:
            try:
                msg = recv_json(s)
                if msg is None:
                    print("Disconnected from the server")
                    running = False
                    break
                msg_type = msg.get("type")
                if msg_type == "success" or msg_type == "error":
                    print(f"{msg.get('content')}")
                elif msg_type == "chats_got":
                    chats = msg.get("chats")
                    clear_console()
                    print("Your chats:\n")
                    for c in chats:
                        print(f"{c['name']} [{c['id']}]")
                elif msg_type == "chat_open":
                    clear_console()
                    print(f"Entered chat with id {msg.get('chat_id')}")
                    current_chat_id = msg.get('chat_id')
                    for m in msg.get("messages"):
                        print(f"{m['sender']} : {m['content']}   {m['sent_at']}")
                elif msg_type == "new_msg":
                    chat_id = msg.get("chat_id")
                    if chat_id == current_chat_id:
                        print(f"{msg.get('sender')} : {msg.get('content')}   {msg.get('sent_at')}")
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
                    running = False
            except Exception as e:
                print("Error receiving message:", e)
                running = False

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, int(PORT)))
    threading.Thread(target=listener, daemon=True).start()

    username = input("Enter your username: ")
    password = input("Enter your password: ")
    send_json(s, {"type": "login", "username": username, "password": password})
    print("\nType 'help' for commands")"""

    while running:
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
                print("Invalid command")