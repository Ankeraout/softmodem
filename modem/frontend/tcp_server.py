import modem
import socket

class TCPServer(modem.IByteReceiver):
    def __init__(self, address: str, port: int, byte_sender: modem.IByteSender | None = None) -> None:
        self._byte_sender = byte_sender
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self._server_socket.bind((address, port))
        self._server_socket.listen()
        self._client_socket: socket.socket | None = None

    def run(self) -> None:
        print("Server ready.")
        end = False

        try:
            while not end:
                self._client_socket, address = self._server_socket.accept()

                print("Client connected.")

                try:
                    while True:
                        data = self._client_socket.recv(1500)

                        if len(data) == 0:
                            end = True
                            break

                        self._byte_sender.send_bytes(data)

                except KeyboardInterrupt:
                    print("Program termination request received.")
                    end = True

                except Exception as e:
                    print("Client disconnected.")
                    raise e

        except KeyboardInterrupt:
            pass

    @property
    def byte_sender(self) -> modem.IByteSender | None:
        return self._byte_sender
    
    @byte_sender.setter
    def byte_sender(self, byte_sender: modem.IByteSender | None) -> None:
        self._byte_sender = byte_sender

    def receive_bytes(self, data: bytes) -> None:
        try:
            self._client_socket.send(data)
        
        except:
            pass
