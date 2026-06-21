import socket
import softmodem

class SocketByteReceiver(softmodem.IByteReceiver):
    def __init__(self, socket: socket.socket) -> None:
        self._socket = socket
    
    def receive_bytes(self, data: bytes) -> None:
        self._socket.send(data)
