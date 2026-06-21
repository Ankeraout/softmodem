import array
import softmodem

class PCM16(softmodem.ICodec):
    def __init__(self) -> None:
        self._buffer: int | None = None

    def decode(self, data: bytes) -> list[float]:
        if self._buffer is not None:
            data = self._buffer.to_bytes(1) + data
            self._buffer = None

        if (len(data) % 2) != 0:
            self._buffer = data[-1]
            data = data[:-1]
        
        return list(map(lambda x: x / 32767, array.array("h", data)))
    
    def encode(self, samples: list[float]) -> bytes:
        return array.array("h", map(lambda x: round(x * 32767), samples)).tobytes()