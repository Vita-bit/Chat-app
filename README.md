## Chat app

Basic python chatting app where messages are sent to a server you can host anywhere. Each server has its own database ( messages are stored on a SQLite database ). The user interacts with the server using sockets as JSON files. After connecting to a server users have to register / log in. Then they can create private chats / group chats with other users. The server uses ngrok to assign a domain to itself that users connect to.

# Functions:
    - Basic chat with messages
    - Voice messages
    - Voice chat and calls
    - Sending files
    - Modern GUI
    - Video calls

# Used libraries:
    - PyQT
    - opencv
    - aiortc
    - asyncio
    - sounddevice
    - sqlite3
    - pyngrok
    - FastAPI
