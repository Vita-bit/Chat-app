## Chat app

Basic python chatting app where messages are sent to a server you can host anywhere. Each server has its own SQLite database. The user interacts with the server using sockets as JSON files. After connecting to a server users have to register / log in. Then they can create private chats / group chats with other users.

# Functions:
    - Basic chat with messages
    - Voice messages
    - Voice chat and calls
    - Sending files

# Used libraries:
    - PyQT
    - opencv
    - aiortc
    - asyncio
    - sounddevice
    - sqlite3
    - FastAPI

# How to setup the server:
1. Download the server module using pip
2. Run 
    ```bash
    python -m server start
    ```
3. Enter the port you want to run the server on (if you want to connect through the internet make sure you have port forwarding on)
4. Share the private IP address if the users are on the same network and the public IP if you're connecting through the internet

# How to start the app:
1. Download the app module using pip
2. Run:
    ```bash
    python -m app start
    ```
3. Enter the private / public IP of the server you want to connect to
4. Enter the port the server is running on
