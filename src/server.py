import socket
import sqlite3
import requests
import json
import threading
import os
import uuid
import base64


clients: dict[str, socket.socket] = {}
clients_lock = threading.Lock()
current_chats: dict[str, int | None] = {}
current_chats_lock = threading.Lock()


def send_json(sock: socket.socket, message: dict) -> bool:
    try:
        data = json.dumps(message).encode()
        sock.sendall(len(data).to_bytes(4, "big"))
        sock.sendall(data)
        return True
    except Exception:
        return False


def recv_json(sock: socket.socket) -> dict | None:
    try:
        length_bytes = sock.recv(4)
        if not length_bytes:
            return None
        length = int.from_bytes(length_bytes, "big")
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        return json.loads(data.decode())
    except Exception:
        return None


def sql_init() -> bool:
    try:
        with sqlite3.connect("chatapp.db") as db:
            db.execute("pragma foreign_keys = on")
            cur = db.cursor()
            cur.execute("""
                create table if not exists users (
                    id integer primary key autoincrement,
                    username text not null unique,
                    password text not null
                )
            """)
            cur.execute("""
                create table if not exists chats (
                    id integer primary key autoincrement,
                    name text
                )
            """)
            cur.execute("""
                create table if not exists chat_users (
                    chat_id integer not null,
                    user_id integer not null,
                    primary key (chat_id, user_id),
                    foreign key (chat_id) references chats(id) on delete cascade,
                    foreign key (user_id) references users(id) on delete cascade
                )
            """)
            cur.execute("""
                create table if not exists messages (
                    id integer primary key autoincrement,
                    chat_id integer not null,
                    sender_id integer not null,
                    content text,
                    file_name text,
                    file_path text,
                    sent_at datetime default current_timestamp,
                    foreign key (chat_id) references chats(id) on delete cascade,
                    foreign key (sender_id) references users(id) on delete cascade
                )
            """)
            db.commit()
            return True
    except Exception as e:
        print(f"error while initializing database: {e}")
        return False


def get_private_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    finally:
        sock.close()


def _notify_chat_members(chat_id: int, message: dict):
    with sqlite3.connect("chatapp.db") as db:
        cur = db.cursor()
        cur.execute("""
            select u.username from chat_users cu
            join users u on cu.user_id = u.id
            where cu.chat_id = ?
        """, (chat_id,))
        members = [row[0] for row in cur.fetchall()]

    with clients_lock:
        for member in members:
            if member in clients:
                send_json(clients[member], message)


def create_chat(users: list, creator: str, conn: socket.socket, chat_name: str):
    with sqlite3.connect("chatapp.db") as db:
        db.execute("pragma foreign_keys = on")
        cur = db.cursor()

        user_ids = []
        for user in users:
            cur.execute("select id from users where username = ?", (user,))
            row = cur.fetchone()
            if row is None:
                send_json(conn, {"type": "error", "content": f"user '{user}' does not exist"})
                return
            user_ids.append(row[0])

        cur.execute("insert into chats (name) values (?)", (chat_name,))
        chat_id = cur.lastrowid

        for user_id in user_ids:
            cur.execute("insert into chat_users (chat_id, user_id) values (?, ?)", (chat_id, user_id))

        cur.execute("select id from users where username = ?", (creator,))
        creator_id = cur.fetchone()[0]
        if creator_id not in user_ids:
            cur.execute("insert into chat_users (chat_id, user_id) values (?, ?)", (chat_id, creator_id))

        db.commit()

    _notify_chat_members(chat_id, {
        "type": "chat_created",
        "chat_id": chat_id,
        "chat_name": chat_name,
        "last_message": ""
    })


def get_chats(username: str):
    with sqlite3.connect("chatapp.db") as db:
        db.execute("pragma foreign_keys = on")
        cur = db.cursor()

        cur.execute("select id from users where username = ?", (username,))
        user_row = cur.fetchone()
        if not user_row:
            send_json(clients[username], {"type": "error", "content": "user not found"})
            return

        user_id = user_row[0]
        cur.execute("""
            select
                c.id,
                coalesce(c.name, (
                    select u2.username from chat_users cu2
                    join users u2 on cu2.user_id = u2.id
                    where cu2.chat_id = c.id and u2.id != ? limit 1
                )),
                (select m.content from messages m where m.chat_id = c.id order by m.sent_at desc limit 1),
                (select m.sent_at from messages m where m.chat_id = c.id order by m.sent_at desc limit 1)
            from chats c
            join chat_users cu on c.id = cu.chat_id
            where cu.user_id = ?
            group by c.id
            order by 4 desc
        """, (user_id, user_id))

        chats = []
        for chat_id, chat_name, last_message, _ in cur.fetchall():
            chats.append({
                "id": chat_id,
                "name": chat_name,
                "last_message": last_message or ""
            })

    send_json(clients[username], {"type": "chats_got", "chats": chats})


def open_chat(chat_id: int, username: str):
    with sqlite3.connect("chatapp.db") as db:
        cur = db.cursor()

        cur.execute("select id from users where username = ?", (username,))
        user_row = cur.fetchone()
        if not user_row:
            send_json(clients[username], {"type": "error", "content": "invalid user"})
            return

        user_id = user_row[0]

        cur.execute("select id from chats where id = ?", (chat_id,))
        if not cur.fetchone():
            send_json(clients[username], {"type": "error", "content": f"chat {chat_id} does not exist"})
            return

        cur.execute("select 1 from chat_users where chat_id = ? and user_id = ?", (chat_id, user_id))
        if not cur.fetchone():
            send_json(clients[username], {"type": "error", "content": "you are not in this chat"})
            return

        cur.execute("""
            select m.id, u.username, m.content, m.file_name, m.sent_at
            from messages m
            join users u on m.sender_id = u.id
            where m.chat_id = ?
            order by m.sent_at desc
            limit 50
        """, (chat_id,))

        messages = [
            {
                "sender": sender,
                "content": content,
                "file_name": file_name,
                "message_id": msg_id,
                "sent_at": sent_at
            }
            for msg_id, sender, content, file_name, sent_at in reversed(cur.fetchall())
        ]

    with current_chats_lock:
        current_chats[username] = chat_id

    send_json(clients[username], {"type": "chat_open", "chat_id": chat_id, "messages": messages})


def get_users(requesting_user: str):
    with sqlite3.connect("chatapp.db") as db:
        cur = db.cursor()
        cur.execute("select username from users")
        users = [row[0] for row in cur.fetchall() if row[0] != requesting_user]

    with clients_lock:
        conn = clients.get(requesting_user)

    if conn:
        send_json(conn, {"type": "users_got", "users": users})
    else:
        print(f"connection for {requesting_user} not found when getting users")


def send_message(username: str, content: str):
    with current_chats_lock:
        chat_id = current_chats.get(username)

    if chat_id is None:
        send_json(clients[username], {"type": "error", "content": "no active chat"})
        return

    try:
        with sqlite3.connect("chatapp.db") as db:
            cur = db.cursor()
            cur.execute("select id from users where username = ?", (username,))
            sender_id = cur.fetchone()[0]

            cur.execute(
                "insert into messages (chat_id, sender_id, content) values (?, ?, ?)",
                (chat_id, sender_id, content)
            )
            db.commit()

            cur.execute("select content, sent_at from messages where id = ?", (cur.lastrowid,))
            saved_content, sent_at = cur.fetchone()

            cur.execute("select name from chats where id = ?", (chat_id,))
            chat_name_row = cur.fetchone()
            chat_name = chat_name_row[0] if chat_name_row else None

            cur.execute(
                "select u.username from chat_users cu join users u on cu.user_id = u.id where cu.chat_id = ?",
                (chat_id,)
            )
            members = [row[0] for row in cur.fetchall()]

        msg_dict = {
            "type": "new_msg",
            "chat_id": chat_id,
            "chat_name": chat_name,
            "sender": username,
            "content": saved_content,
            "sent_at": sent_at
        }

        with clients_lock:
            for member in members:
                if member in clients:
                    send_json(clients[member], msg_dict)

    except Exception as e:
        print(f"error sending message for {username}: {e}")
        send_json(clients[username], {"type": "error", "content": "failed to send message"})


def receive_file(username: str, file_name: str, file_data_b64: str, chat_id: int) -> bool:
    if chat_id is None:
        send_json(clients[username], {"type": "error", "content": "no active chat"})
        return False

    base, ext = os.path.splitext(file_name)
    unique_name = f"{base}_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join("files", unique_name)

    with open(file_path, "wb") as f:
        f.write(base64.b64decode(file_data_b64))

    with sqlite3.connect("chatapp.db") as db:
        cur = db.cursor()
        cur.execute("select id from users where username = ?", (username,))
        sender_id = cur.fetchone()[0]

        cur.execute(
            "insert into messages (chat_id, sender_id, file_name, file_path) values (?, ?, ?, ?)",
            (chat_id, sender_id, file_name, file_path)
        )
        db.commit()

        cur.execute("select sent_at, id from messages where id = ?", (cur.lastrowid,))
        row = cur.fetchone()
        if row is None:
            return False
        sent_at, message_id = row

        cur.execute("select name from chats where id = ?", (chat_id,))
        chat_name_row = cur.fetchone()
        chat_name = chat_name_row[0] if chat_name_row else None

    _notify_chat_members(chat_id, {
        "type": "new_file",
        "chat_id": chat_id,
        "chat_name": chat_name,
        "sender": username,
        "file_name": file_name,
        "message_id": message_id,
        "content": None,
        "sent_at": sent_at
    })
    return True


def download_file(username: str, message_id: int, sock: socket.socket, chat_id: int) -> bool:
    try:
        if chat_id is None:
            send_json(clients[username], {"type": "error", "content": "no active chat"})
            return False

        with sqlite3.connect("chatapp.db") as db:
            cur = db.cursor()

            cur.execute("select id from users where username = ?", (username,))
            user_row = cur.fetchone()
            if not user_row:
                send_json(sock, {"type": "error", "content": "invalid user"})
                return False
            user_id = user_row[0]

            cur.execute("select 1 from chat_users where chat_id = ? and user_id = ?", (chat_id, user_id))
            if not cur.fetchone():
                send_json(sock, {"type": "error", "content": "you are not in this chat"})
                return False

            cur.execute("select file_name, file_path from messages where id = ?", (message_id,))
            row = cur.fetchone()
            if not row:
                send_json(sock, {"type": "error", "content": f"no file found with id {message_id}"})
                return False

            file_name, file_path = row
            if not file_path or not os.path.exists(file_path):
                send_json(sock, {"type": "error", "content": "file not found on server"})
                return False

            with open(file_path, "rb") as f:
                file_data = base64.b64encode(f.read()).decode()

        send_json(sock, {"type": "file_download", "file_name": file_name, "file_data": file_data})
        return True

    except Exception as e:
        print(f"error sending file for user {username}: {e}")
        send_json(sock, {"type": "error", "content": "failed to send file"})
        return False


def change_password(username: str, old_password: str, new_password: str, conn: socket.socket) -> bool:
    try:
        with sqlite3.connect("chatapp.db") as db:
            db.execute("pragma foreign_keys = on")
            cur = db.cursor()

            cur.execute("select password from users where username = ?", (username,))
            row = cur.fetchone()
            if not row:
                send_json(conn, {"type": "error", "content": "user does not exist"})
                return False

            if row[0] != old_password:
                send_json(conn, {"type": "error", "content": "old password is incorrect"})
                return False

            cur.execute("update users set password = ? where username = ?", (new_password, username))
            db.commit()
            send_json(conn, {"type": "success", "content": "password changed successfully"})
            return True

    except Exception as e:
        print(f"error changing password for {username}: {e}")
        send_json(conn, {"type": "error", "content": "failed to change password"})
        return False


def _authenticate(conn: socket.socket, message: dict) -> str | None:
    username = message.get("username")
    password = message.get("password")
    msg_type = message.get("type")

    if not username or not password:
        send_json(conn, {"type": "loginerror", "content": "username and password required"})
        return None

    with sqlite3.connect("chatapp.db") as db:
        db.execute("pragma foreign_keys = on")
        cur = db.cursor()
        cur.execute("select id, password from users where username = ?", (username,))
        user_row = cur.fetchone()

        if msg_type == "register":
            if user_row:
                send_json(conn, {"type": "loginerror", "content": "username already exists"})
                return None
            cur.execute("insert into users (username, password) values (?, ?)", (username, password))
            db.commit()
            with clients_lock:
                clients[username] = conn
            print(f"client {username} registered and connected")
            send_json(conn, {"type": "loginsuccess", "content": username})
            return username

        elif msg_type == "login":
            if not user_row:
                send_json(conn, {"type": "loginerror", "content": "user does not exist"})
                return None
            if user_row[1] != password:
                send_json(conn, {"type": "loginerror", "content": "wrong password"})
                return None
            with clients_lock:
                clients[username] = conn
            print(f"client {username} logged in")
            send_json(conn, {"type": "loginsuccess", "content": username})
            return username

        else:
            send_json(conn, {"type": "error", "content": "invalid action, must be login or register"})
            return None


def handle_client(conn: socket.socket, addr: tuple):
    username = None
    try:
        while True:
            message = recv_json(conn)
            if message is None:
                break

            if username is None:
                username = _authenticate(conn, message)
                continue

            msg_type = message.get("type")

            if msg_type == "create_chat":
                create_chat(
                    message.get("users"),
                    message.get("creator"),
                    clients[username],
                    message.get("name")
                )

            elif msg_type == "get_chats":
                get_chats(message.get("user"))

            elif msg_type == "open_chat":
                open_chat(message.get("chat_id"), username)

            elif msg_type == "msg":
                send_message(username, message.get("content"))

            elif msg_type == "get_users":
                get_users(username)

            elif msg_type == "close_chat":
                with current_chats_lock:
                    current_chats[username] = None
                send_json(clients[username], {"type": "closed_chat"})

            elif msg_type == "change_password":
                change_password(username, message.get("old_password"), message.get("new_password"), clients[username])

            elif msg_type == "send_file":
                file_name = message.get("file_name")
                file_data = message.get("file_data")
                chat_id = message.get("chat_id")
                if not file_name or not file_data:
                    send_json(clients[username], {"type": "error", "content": "missing file data"})
                    continue
                receive_file(username, file_name, file_data, chat_id)

            elif msg_type == "request_download":
                download_file(username, message.get("file_id"), clients[username], message.get("chat_id"))

            elif msg_type == "logout":
                with clients_lock:
                    clients.pop(username, None)
                with current_chats_lock:
                    current_chats.pop(username, None)
                break

    except Exception:
        pass
    finally:
        if username:
            with clients_lock:
                if username in clients:
                    try:
                        send_json(clients[username], {"type": "disconnect", "content": "disconnected"})
                    except Exception:
                        pass
                    del clients[username]
            with current_chats_lock:
                current_chats.pop(username, None)
        conn.close()
        print(f"client {username} disconnected")


if __name__ == "__main__":
    port = input("enter the port for the server to run on: ")
    os.makedirs("files", exist_ok=True)
    sql_init()

    try:
        response = requests.get("https://api.ipify.org")
        print("your private ip is:", get_private_ip())
        print(f"your public ip is: {response.text}")
        print(f"your server is running on port: {port}")
    except requests.RequestException:
        print("could not determine public ip")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind(("0.0.0.0", int(port)))
        server_socket.listen()
        print(f"server listening on 0.0.0.0:{port}")
        while True:
            conn, addr = server_socket.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()