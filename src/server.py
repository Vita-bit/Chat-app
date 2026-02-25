import socket
import threading

HOST = "127.0.0.1"
PORT = 1000

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((HOST, PORT))
server.listen()

clients = []
nicknames = []

print("Server running")

def broadcast_to_all(message):
    for client in clients:
        client.send(message)

def handle(client):
    while True:
        try:
            message = client.recv(1024)
            broadcast_to_all(message)
        except:
            index = clients.index(client)
            clients.remove(client)
            client.close()
            nickname = nicknames[index]
            broadcast_to_all(f"{nickname} left the chat!".encode('utf-8'))
            nicknames.remove(nickname)
            break

def receive():
    while True:
        client, address = server.accept()
        print(f"Connected with {str(address)}")
        client.send("NICK".encode('utf-8'))
        nickname = client.recv(1024).decode('utf-8')
        nicknames.append(nickname)
        clients.append(client)
        print(f"Nickname is {nickname}")
        broadcast_to_all(f"{nickname} joined the chat!".encode('utf-8'))
        client.send("Connected succesfully".encode('utf-8'))
        thread = threading.Thread(target=handle, args=(client,))
        thread.start()

receive()