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
def create_chat(users, creator, conn, chat_name=None, is_group=False):
    is_group = len(users) + 1 > 2
    if not is_group and chat_name is None:
        chat_name = None
    elif is_group and chat_name is None:
        chat_name = "Group Chat"
    with sqlite3.connect("db/chatapp.db") as dbconn:
        dbconn.execute("pragma foreign_keys = ON")
        cur = dbconn.cursor()
        user_ids = []
        for username in users:
            cur.execute("select id from users where username = ?", (username,))
            row = cur.fetchone()
            if row is None:
                if conn:
                    send_json(conn, {"type": "error", "content": f"User '{username}' does not exist"})
                    continue
            user_ids.append(row[0])
        cur.execute("insert into chats (name, is_group) values (?, ?)", (chat_name, int(is_group)))
        chat_id = cur.lastrowid
        for user_id in user_ids:
            cur.execute("insert into chat_users (chat_id, user_id) values (?, ?)", (chat_id, user_id))
        cur.execute("select id from users where username = ?", (creator,))
        creator_row = cur.fetchone()
        creator_id = creator_row[0]
        cur.execute("insert into chat_users (chat_id, user_id) values (?,?)",(chat_id, creator_id))
        dbconn.commit()
def get_chats(user):
    with sqlite3.connect("db/chatapp.db") as dbconn:
        dbconn.execute("pragma foreign_keys = ON")
        cur = dbconn.cursor()
        cur.execute("select id from users where username = ?", (user,))
        user_id_row = cur.fetchone()
        if user_id_row:
            user_id = user_id_row[0]
        cur.execute("select c.id as chat_id, coalesce(c.name, u.username) as chat_name from chats c join chat_users cu on c.id = cu.chat_id join users u on u.id = cu.user_id where cu.chat_id in (select chat_id from chat_users where user_id = ?) and u.username != ? group by c.id",(user_id, user_id))
        rows = cur.fetchall()
        ret = []
        for r in rows:
            ret.append({"id" : r[0], "name" : r[1]})
        send_json(clients[user], {"type" : "success", "chats" : ret})

with sqlite3.connect("db/chatapp.db") as dbconn:
    dbconn.execute("PRAGMA foreign_keys = ON")
    cur = dbconn.cursor()
    cur.execute("create table if not exists users (id integer primary key autoincrement, username text not null unique, password text not null)")
    cur.execute("create table if not exists chats (id integer primary key autoincrement, name text, is_group boolean not null default 0)")
    cur.execute("create table if not exists chat_users (chat_id integer not null, user_id integer not null, primary key (chat_id, user_id), foreign key (chat_id) references chats(id) on delete cascade, foreign key (user_id) references users(id) on delete cascade)")
    cur.execute("create table if not exists messages (id integer primary key autoincrement, chat_id integer not null, sender_id integer not null, content text not null, sent_at datetime default current_timestamp, foreign key (chat_id) references chats(id) on delete cascade, foreign key (sender_id) references users(id) on delete cascade)")
    cur.execute("create table if not exists files (id integer primary key autoincrement, chat_id integer not null, sender_id integer not null, file_name text not null, file_path text not null, sent_at datetime default current_timestamp, foreign key (chat_id) references chats(id) on delete cascade, foreign key (sender_id) references users(id) on delete cascade)")
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
            with sqlite3.connect("db/chatapp.db") as dbconn:
                dbconn.execute("PRAGMA foreign_keys = ON")
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
            if json_type == "create_chat":
                users = message.get("users")
                creator = message.get("creator")
                chat_name = message.get("name")
                create_chat(users, creator, clients[username], chat_name)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, int(PORT)))
    s.listen()
    print(f"Server listening on {HOST}:{PORT}")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()