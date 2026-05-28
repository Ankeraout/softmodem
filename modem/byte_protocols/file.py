import modem
import io

class FileByteReceiver(modem.IByteReceiver):
    def __init__(self, file: io.RawIOBase) -> None:
        self._file = file

    def receive_bytes(self, data: bytes) -> None:
        self._file.write(data)
        self._file.flush()
