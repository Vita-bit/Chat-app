import socket
import json
import threading
import os

def main():
    HOST = input("Enter server's public / private IP address: ")
    PORT = input("Enter the port the server's running on: ")
    current_chat_id = None
    running = True

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, int(PORT)))

    def send_json(sock, message):
        try:
            data = json.dumps(message).encode()
            sock.sendall(len(data).to_bytes(4, "big"))
            sock.sendall(data)
        except (ConnectionResetError, BrokenPipeError):
            return False
        return True
    def recv_json(sock):
        length_bytes = sock.recv(4)
        length = int.from_bytes(length_bytes, "big")
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        return json.loads(data.decode())
    def clear_console():
        if os.name == 'nt':
            os.system('cls')
        else:
            os.system('clear')
    def listener():
        nonlocal running, current_chat_id
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
                        print(f"{msg.get('sender')} sent a file : {msg.get('file_name')}   {msg.get('sent_at')} [{msg.get('message_id')}]")
                    else:
                        print(f"New file from {msg.get('sender')} in chat {msg.get('chat_name')} [{chat_id}]")
                elif msg_type == "closed_chat":
                    clear_console()
                    print("Successfully closed chat")
                elif msg_type == "disconnect":
                    print(f"Disconnected from the server - {msg.get('content')}")
                    running = False
            except Exception as e:
                print("Error receiving message:", e)
                running = False
    threading.Thread(target=listener, daemon=True).start()

    username = input("Enter your username: ")
    password = input("Enter your password: ")
    send_json(s, {"type": "login", "username": username, "password": password})
    print("\nType 'help' for commands")

    while running:
        if not running:
            break
        comm = input("").strip()
        if comm == "help":
            print("get_chats - prints all your chats\ncreate_chat [username1] [username2] [usernameN] [group/chat name (no spaces allowed)] - creates a chat with another user\nopen_chat [chat_id] - opens chat and prints the last 50 messages\nmsg [content] - sends a message in the currently open chat\nclose_chat - closes the currently active chat\nlogout - logs you out and closes app\nclear - clears the console\nsend_file [relative file path to the app.py file] - sends a file in the current chat")
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
                if len(args) < 2 or len(args) > 2:
                    print("send_file accepts exactly two arguments")
                else:
                    try:
                        file_path = args[1]
                        send_json(s, {"type" : "send_file", "sender" : username, "file_name" : os.path.basename(file_path), "file_size" : os.path.getsize(file_path)})
                        with open(file_path, "rb") as file:
                            while chunk := file.read(4096):
                                s.sendall(chunk)
                        print(f"Sent file {os.path.basename(file_path)} ({os.path.getsize(file_path)} bytes)")
                    except Exception as e:
                        print(f"Error while sending file - {e}")
            else:
                print("Invalid command")

main()