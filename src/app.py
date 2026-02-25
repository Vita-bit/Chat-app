import socket
import threading

HOST = input("Enter server url: ")
PORT = 1000

username = input("Enter your username: ")

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((HOST, PORT))

def receive():
    while True:
        try:
            message = client.recv(1024).decode('utf-8')
            if message == "NICK":
                client.send(username.encode('utf-8'))
            else:
                print(message)
        except:
            print("Error")
            client.close()
            break

def send():
    while True:
        message = f"{username}: {input('')}"
        client.send(message.encode('utf-8'))

receive_thread = threading.Thread(target=receive)
receive_thread.start()

write_thread = threading.Thread(target=send)
write_thread.start()