import modem

class BufferByteReceiver(modem.IByteReceiver):
    def __init__(self) -> None:
        self.buffer = bytearray()

    def receive_bytes(self, data: bytes):
        self.buffer.extend(data)
