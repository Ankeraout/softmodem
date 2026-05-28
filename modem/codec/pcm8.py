import array
import modem

class PCM8(modem.ICodec[bytes]):
    def decode(self, data: bytes) -> list[float]:
        return list(map(lambda x: x / 255, data))
    
    def encode_sample(self, sample: float) -> int:
        if sample < -1:
            return 0
        
        if sample > 1:
            return 255
        
        else:
            return round(sample * 255)
    
    def encode(self, samples: list[float]) -> bytes:
        return bytes(map(lambda x: round((x + 1) * 255 / 2), samples))
