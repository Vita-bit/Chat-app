import socket
import sqlite3
import requests
import json
import threading

PORT = input("Enter the port for the server to run on: ")
HOST = "0.0.0.0"
clients = {}
clients_lock = threading.Lock()

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

with sqlite3.connect("chatapp.db") as dbconn:
    cur = dbconn.cursor()
    cur.execute("create table if not exists users (id integer primary key autoincrement, username text not null unique, password text not null)")
    dbconn.commit()

try:
    response = requests.get("https://api.ipify.org")
    print(f"Your public IP is: {response.text}")
    print(f"Your server is running on port: {PORT}")
except requests.RequestException:
    print("Could not determine public IP")

def handle_client(conn, addr):
    buffer = ""
    username = None
    while True:
        message = recv_json(conn)
        if username is None:
            username = message.get("username")
            password = message.get("password")
            if not username or not password:
                    send_json(conn, {"type": "error", "content": "Username and password required"})
            with sqlite3.connect("chatapp.db") as dbconn:
                cur = dbconn.cursor()
                cur.execute("select id, password from users where username = ?",(username,))
                exists_row = cur.fetchone()
                if exists_row:
                    stored_password = exists_row[1]
                    if stored_password == password:
                        with clients_lock:
                            clients[username] = conn
                        send_json(conn, {"type": "success", "content": "Successfully logged in"})
                    else:
                        send_json(conn, {"type": "error", "content": "Wrong password"})
                else:
                        cur.execute("insert into users(username, password) values(?, ?)",(username,password))
                        dbconn.commit()
                        with clients_lock:
                            clients[username] = conn
                        send_json(conn, {"type" : "success", "content" : "Created user"})
        else:
            json_type = message.get("type")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, int(PORT)))
    s.listen()
    print(f"Server listening on {HOST}:{PORT}")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()