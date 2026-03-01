import socket
import json

HOST = input("Enter server's public IP adress: ")
PORT = input("Enter the port the server's running on: ")

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))
print("Type 'help' for commands")

def send_json(sock, message):
    data = json.dumps(message).encode()
    sock.sendall(len(data).to_bytes(4, "big"))
    sock.sendall(data)
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

username = input("Enter your username: ")
password = input("Enter your password: ")
send_json(s, {"type": "login", "username": username, "password": password})
response = recv_json(s)
print(response["content"])

while True:
    comm = input("")
    if comm == "help":
        print("get_chats - prints all your chats\ncreate_chat [username] - creates a chat with another user\ncreate_group [name] [usernames (list)]- creates a group chat with other users\nopen_chat [chat_id] - opens chat and prints the last 50 messages")
