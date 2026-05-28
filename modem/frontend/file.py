import io
import modem

class File(modem.IByteReceiver):
    def __init__(self, file: io.IOBase, byte_sender: modem.IByteSender | None = None) -> None:
        self._byte_sender = byte_sender
        self._file = file

    def run(self) -> None:
        try:
            while True:
                data = self._file.read()
                print(data)
                self._byte_sender.send_bytes(data)

        except KeyboardInterrupt:
            pass

    @property
    def byte_sender(self) -> modem.IByteSender | None:
        return self._byte_sender
    
    @byte_sender.setter
    def byte_sender(self, byte_sender: modem.IByteSender | None) -> None:
        self._byte_sender = byte_sender

    def receive_bytes(self, data: bytes) -> None:
        self._file.write(data)

