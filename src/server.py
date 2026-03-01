import socket
import sqlite3
import requests
import json

conn = sqlite3.connect("chatapp.db")
cur = conn.cursor()
PORT = input("Enter the port for the server to run on: ")
HOST = "0.0.0.0"

try:
    response = requests.get("https://api.ipify.org")
    print(f"Your public IP is: {response.text}")
    print(f"Your server is running on port: {PORT}")
except requests.RequestException:
    print("Could not determine public IP")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, int(PORT)))
    s.listen()
    print(f"Server listening on {HOST}:{PORT}")

    while True:
        conn, addr = s.accept()
        with conn:
            buffer = ""
            while True:
                data = conn.recv().decode()
                if not data:
                    break
                buffer += data

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    try:
                        message = json.loads(line)
                        print("Received JSON:", message)
                    except json.JSONDecodeError:
                        print("Invalid JSON:", line)