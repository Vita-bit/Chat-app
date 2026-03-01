import socket
import json

HOST = input("Enter server's public IP adress: ")
PORT = input("Enter the port the server's running on: ")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, int(PORT)))

    message = {"username": "Alice", "message": "Hello!"}
    s.sendall((json.dumps(message) + "\n").encode())

    data = s.recv(1024).decode()
    response = json.loads(data.strip())
    print("Server response:", response)