import socket
import sqlite3
import requests
import json
import threading
import os
import uuid
import base64

if __name__ == "__main__":
    PORT = input("Enter the port for the server to run on: ")
    HOST = "0.0.0.0"
    os.makedirs("files", exist_ok=True)
    clients = {}
    clients_lock = threading.Lock()
    current_chats = {}
    current_chats_lock = threading.Lock()

    def send_json(socket, message):
        try:
            data = json.dumps(message).encode()
            socket.sendall(len(data).to_bytes(4, "big"))
            socket.sendall(data)
            return True
        except Exception:
            return False
    
    def recv_json(sock):
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
        
    def create_chat(users, creator, conn, chat_name=None, avatar=None):
        with sqlite3.connect("chatapp.db") as dbconn:
            dbconn.execute("pragma foreign_keys = ON")
            cur = dbconn.cursor()

            user_ids = []
            for user in users:
                cur.execute("select id from users where username = ?", (user,))
                row = cur.fetchone()
                if row is None:
                    if conn:
                        send_json(conn, {"type": "error", "content": f"User '{user}' does not exist"})
                        return
                user_ids.append(row[0])

            cur.execute("insert into chats (name) values (?)", (chat_name,))
            chat_id = cur.lastrowid

            for user_id in user_ids:
                cur.execute("insert into chat_users (chat_id, user_id) values (?, ?)", (chat_id, user_id))

            cur.execute("select id from users where username = ?", (creator,))
            creator_row = cur.fetchone()
            creator_id = creator_row[0]
            if creator_id not in user_ids:
                cur.execute("insert into chat_users (chat_id, user_id) values (?,?)",(chat_id, creator_id))

            dbconn.commit()
            cur.execute("""
                select u.username from chat_users cu
                join users u on cu.user_id = u.id
                where cu.chat_id = ?
            """, (chat_id,))
            members = [row[0] for row in cur.fetchall()]

            notify = {
                "type": "chat_created",
                "chat_id": chat_id,
                "chat_name": chat_name,
                "last_message": ""
            }
            with clients_lock:
                for member in members:
                    if member in clients:
                        send_json(clients[member], notify)
    def get_chats(username):
        with sqlite3.connect("chatapp.db") as dbconn:
            dbconn.execute("PRAGMA foreign_keys = ON")
            cur = dbconn.cursor()
            
            cur.execute("SELECT id FROM users WHERE username = ?", (username,))
            user_row = cur.fetchone()
            if not user_row:
                send_json(clients[username], {"type": "error", "content": "User not set"})
                return
            user_id = user_row[0]
            cur.execute("""
                select 
                    c.id as chat_id,
                    coalesce(c.name, (
                        select u2.username from chat_users cu2 
                        inner join users u2 on cu2.user_id = u2.id 
                        where cu2.chat_id = c.id AND u2.id != ? limit 1
                    )) as chat_name,
                    (
                        select m.content from messages m 
                        where m.chat_id = c.id order by m.sent_at desc limit 1
                    ) as last_message,
                    (
                        select m.sent_at from messages m 
                        where m.chat_id = c.id order by m.sent_at desc limit 1
                    ) as last_message_time
                from chats c 
                inner join chat_users cu on c.id = cu.chat_id 
                where cu.user_id = ? 
                group by c.id 
                order by last_message_time desc
            """, (user_id, user_id))
            rows = cur.fetchall()
            ret = []
            for r in rows:
                chat_id, chat_name, last_message, last_message_time = r
                if last_message is None:
                    last_message = ""
                ret.append({
                    "id": chat_id,
                    "name": chat_name,
                    "last_message": last_message
                })
            send_json(clients[username], {"type": "chats_got", "chats": ret})
    def open_chat(chat_id, username):
        with sqlite3.connect("chatapp.db") as dbconn:
            cur = dbconn.cursor()
            cur.execute("select id from users where username = ?", (username,))
            user_row = cur.fetchone()
            if not user_row:
                send_json(clients[username], {"type": "error", "content": "Invalid user"})
                return
            user_id = user_row[0]
            cur.execute("select id from chats where id = ?", (chat_id,))
            if not cur.fetchone():
                send_json(clients[username], {"type": "error", "content": f"Chat {chat_id} does not exist"})
                return
            cur.execute("select 1 from chat_users where chat_id = ? and user_id = ?", (chat_id, user_id))
            if not cur.fetchone():
                send_json(clients[username], {"type": "error", "content": "You are not in this chat"})
                return
            cur.execute("select m.id, u.username as sender, m.content, m.file_name, m.sent_at from messages m join users u on m.sender_id = u.id where m.chat_id = ? order by m.sent_at desc limit 50", (chat_id,))
            rows = cur.fetchall()
            messages = []
            for r in reversed(rows):
                id, sender, content, file_name, sent_at = r
                messages.append({
                    "sender": sender,
                    "content": content,
                    "file_name": file_name,
                    "message_id": id,
                    "sent_at": sent_at
                })
            with current_chats_lock:
                current_chats[username] = chat_id

            send_json(clients[username], {"type": "chat_open", "chat_id": chat_id, "messages": messages})
    def get_users(requesting_user):
        with sqlite3.connect("chatapp.db") as dbconn:
            cur = dbconn.cursor()
            cur.execute("SELECT username FROM users")
            users = [row[0] for row in cur.fetchall()]
        
        users = [u for u in users if u != requesting_user]

        with clients_lock:
            conn = clients.get(requesting_user)
        
        if conn:
            send_json(conn, {
                "type": "users_got",
                "users": users
            })
        else:
            print(f"Error - Connection for {requesting_user} not found when getting users")
    def msg(user, content):
        with current_chats_lock:
            chat_id = current_chats.get(user)
        if chat_id is None:
            send_json(clients[user], {"type": "error", "content": "No chat active"})
            return
        try:
            with sqlite3.connect("chatapp.db") as dbconn:
                cur = dbconn.cursor()
                cur.execute("select id from users where username = ?", (user,))
                sender_id = cur.fetchone()[0]
                cur.execute("insert into messages (chat_id, sender_id, content) VALUES (?, ?, ?)",(chat_id, sender_id, content))
                dbconn.commit()
                cur.execute("select content, sent_at from messages where id = ?",(cur.lastrowid,))
                sent_at_row = cur.fetchone()
                message_to_send = {"sender": user, "content": sent_at_row[0], "sent_at": sent_at_row[1]}
                cur.execute("select u.username from chat_users cu join users u on cu.user_id = u.id where cu.chat_id = ?",(chat_id,))
                users = cur.fetchall()
                cur.execute("select name from chats where id = ?", (chat_id,))
                chat_name_row = cur.fetchone()
                chat_name = chat_name_row[0] if chat_name_row and chat_name_row[0] else None
                msg_dict = {"type": "new_msg", "chat_id": chat_id, "sender": user, "content": message_to_send.get('content'), "chat_name" : chat_name, "sent_at" : message_to_send.get('sent_at')}
                for u in users:
                    target_user = u[0]
                    if target_user in clients:
                        send_json(clients[target_user], msg_dict)
        except Exception as e:
            print(f"Error sending message for {user}: {e}")
            send_json(clients[user], {"type": "error", "content": "An error occurred while sending the message"})
    def receive_file(user, file_name, file_data_b64, chat_id):
        if chat_id is None:
            send_json(clients[user], {"type": "error", "content": "No chat selected"})
            return
        base, ext = os.path.splitext(file_name)
        unique_name = f"{base}_{uuid.uuid4().hex}{ext}"
        file_path = os.path.join("files", unique_name)
        with open(file_path, "wb") as f:
            f.write(base64.b64decode(file_data_b64))
        with sqlite3.connect("chatapp.db") as dbconn:
            cur = dbconn.cursor()
            cur.execute("select id from users where username = ?", (user,))
            sender_id = cur.fetchone()[0]
            cur.execute("insert into messages (chat_id, sender_id, file_name, file_path) values (?, ?, ?, ?)", (chat_id, sender_id, file_name, file_path))
            dbconn.commit()
            cur.execute("select sent_at, id from messages where id = ?", (cur.lastrowid,))
            row = cur.fetchone()
            if row is None:
                return
            sent_at, message_id = row
            cur.execute("select u.username from chat_users cu join users u on cu.user_id = u.id where cu.chat_id = ?", (chat_id,))
            chat_users = [r[0] for r in cur.fetchall()]
            cur.execute("select name from chats where id = ?", (chat_id,))
            chat_name_row = cur.fetchone()
            chat_name = chat_name_row[0] if chat_name_row and chat_name_row[0] else None
        for member in chat_users:
            file_dict = {"type": "new_file", "chat_id": chat_id, "chat_name": chat_name, "sender": user, "file_name": file_name, "message_id": message_id, "content": None, "sent_at": sent_at}
            if member in clients:
                send_json(clients[member], file_dict)
    def download_file(user, message_id, sock, chat_id):
        try:
            if chat_id is None:
                send_json(clients[user], {"type": "error", "content": "No chat selected"})
                return
            with sqlite3.connect("chatapp.db") as dbconn:
                cur = dbconn.cursor()
                cur.execute("select id from users where username = ?", (user,))
                user_row = cur.fetchone()
                if not user_row:
                    send_json(sock, {"type": "error", "content": "Invalid user"})
                    return
                user_id = user_row[0]
                cur.execute("select 1 from chat_users where chat_id = ? and user_id = ?", (chat_id, user_id))
                if not cur.fetchone():
                    send_json(sock, {"type": "error", "content": "You are not in this chat"})
                    return
                cur.execute("select file_name, file_path from messages where id = ?", (message_id,))
                row = cur.fetchone()
                if not row:
                    send_json(sock, {"type": "error", "content": f"No file found with id {message_id}"})
                    return
                file_name, file_path = row
                if not file_path or not os.path.exists(file_path):
                    send_json(sock, {"type": "error", "content": "File not found on server"})
                    return
                with open(file_path, "rb") as f:
                    file_data = base64.b64encode(f.read()).decode()
                send_json(sock, {"type": "file_download", "file_name": file_name, "file_data": file_data})
        except Exception as e:
            print(f"Error sending file for user {user}: {e}")
            send_json(sock, {"type": "error", "content": "Failed to send file"})
    def change_password(username, old_password, new_password, conn):
        try:
            with sqlite3.connect("chatapp.db") as dbconn:
                dbconn.execute("PRAGMA foreign_keys = ON")
                cur = dbconn.cursor()

                cur.execute("select password from users where username = ?", (username,))
                row = cur.fetchone()
                if not row:
                    send_json(conn, {"type": "error", "content": "User does not exist"})
                    return

                current_password = row[0]
                if current_password != old_password:
                    send_json(conn, {"type": "error", "content": "Old password is incorrect"})
                    return

                cur.execute("update users set password = ? where username = ?", (new_password, username))
                dbconn.commit()
                send_json(conn, {"type": "success", "content": "Password changed successfully"})

        except Exception as e:
            print(f"Error changing password for {username}: {e}")
            send_json(conn, {"type": "error", "content": "Failed to change password"})
    def sql_init():
        try:
            with sqlite3.connect("chatapp.db") as dbconn:
                dbconn.execute("PRAGMA foreign_keys = ON")
                cur = dbconn.cursor()
                cur.execute("create table if not exists users (id integer primary key autoincrement, username text not null unique, password text not null)")
                cur.execute("create table if not exists chats (id integer primary key autoincrement, name text)")
                cur.execute("create table if not exists chat_users (chat_id integer not null, user_id integer not null, primary key (chat_id, user_id), foreign key (chat_id) references chats(id) on delete cascade, foreign key (user_id) references users(id) on delete cascade)")
                cur.execute("create table if not exists messages (id integer primary key autoincrement, chat_id integer not null, sender_id integer not null, content text, file_name text, file_path text, sent_at datetime default current_timestamp, foreign key (chat_id) references chats(id) on delete cascade, foreign key (sender_id) references users(id) on delete cascade)")
                dbconn.commit()
                return True
        except Exception as e:
            print(f"Error while initializing database - {e}")
            return False
        
    sql_init()

    try:
        response = requests.get("https://api.ipify.org")
        def get_private_ip():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            finally:
                s.close()
            return ip
        print("Your private IP is:", get_private_ip())
        print(f"Your public IP is: {response.text}")
        print(f"Your server is running on port: {PORT}")
    except requests.RequestException:
        print("Could not determine public IP")

    def handle_client(conn, addr):
        username = None
        try:
            while True:
                message = recv_json(conn)
                json_type = message.get("type", None)
                if message is None:
                    break
                if username is None:
                    username = message.get("username")
                    password = message.get("password")
                    if not username or not password:
                            send_json(conn, {"type": "loginerror", "content": "Username and password required"})
                    with sqlite3.connect("chatapp.db") as dbconn:
                        dbconn.execute("PRAGMA foreign_keys = ON")
                        cur = dbconn.cursor()
                        cur.execute("select id, password from users where username = ?",(username,))
                        user_row = cur.fetchone()
                        if json_type == "register":
                            if user_row:
                                send_json(conn, {"type": "loginerror", "content": "Username already exists"})
                                username = None
                            else:
                                cur.execute("insert into users(username, password) values (?, ?)", (username, password))
                                dbconn.commit()
                                with clients_lock:
                                    clients[username] = conn
                                print(f"Client {username} registered and connected")
                                send_json(conn, {"type": "loginsuccess", "content": username})
                        
                        elif json_type == "login":
                            if not user_row:
                                send_json(conn, {"type": "loginerror", "content": "User does not exist"})
                                username = None
                            else:
                                stored_password = user_row[1]
                                if stored_password == password:
                                    with clients_lock:
                                        clients[username] = conn
                                    print(f"Client {username} logged in")
                                    send_json(conn, {"type": "loginsuccess", "content": username})
                                else:
                                    send_json(conn, {"type": "loginerror", "content": "Wrong password"})
                                    username = None
                        else:
                            send_json(conn, {"type": "error", "content": "Invalid action, must be login or register"})
                            username = None
                    continue
                else:
                    json_type = message.get("type")

                    if json_type == "create_chat":
                        users = message.get("users")
                        creator = message.get("creator")
                        chat_name = message.get("name")
                        create_chat(users, creator, clients[username], chat_name)

                    elif json_type == "get_chats":
                        get_chats(message.get("user"))

                    elif json_type == "open_chat":
                        open_chat(message.get("chat_id"), username)

                    elif json_type == "msg":
                        msg(username, message.get("content"))

                    elif json_type == "get_users":
                        get_users(username)

                    elif json_type == "close_chat":
                        with current_chats_lock:
                            current_chats[message.get('user')] = None
                        send_json(clients[message.get('user')], {"type" : "closed_chat"})

                    elif json_type == "change_password":
                        old_pw = message.get("old_password")
                        new_pw = message.get("new_password")
                        change_password(username, old_pw, new_pw, clients[username])

                    elif json_type == "send_file":
                        file_name = message.get("file_name")
                        file_data = message.get("file_data")
                        chat_id = message.get("chat_id")
                        if not file_name or not file_data:
                            send_json(clients[username], {"type": "error", "content": "Missing file data"})
                            continue
                        receive_file(username, file_name, file_data, chat_id)

                    elif json_type == "request_download":
                        chat_id = message.get("chat_id")
                        file_id = message.get("file_id")
                        download_file(username, file_id, clients[username], chat_id)

                    elif json_type == "logout":
                        with clients_lock:
                            if username in clients:
                                del clients[username]
                        with current_chats_lock:
                            if username in current_chats:
                                del current_chats[username]
                        break

        except Exception as e:
            pass
        finally:
            if username:
                with clients_lock:
                    if username in clients:
                        try:
                            send_json(clients[username], {"type": "disconnect", "content" : "Disconnected"})
                        except Exception:
                            pass
                        del clients[username]
                    if username in current_chats:
                        del current_chats[username]
            conn.close()
            print(f"Client {username} disconnected")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, int(PORT)))
        s.listen()
        print(f"Server listening on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()