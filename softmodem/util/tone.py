import math
import softmodem

class ToneGenerator(softmodem.IAnalogProvider):
    def __init__(self, sample_rate: int, frequency: float) -> None:
        self._phase_advance = 2 * math.pi * frequency / sample_rate
        self._phase = 0

    def get_samples(self, n: int) -> list[float]:
        output = []

        for _ in range(n):
            output.append(math.cos(self._phase))
            self._phase += self._phase_advance
            self._phase %= 2 * math.pi

        return output
    
    def phase_shift(self, angle: float) -> list[float]:
        self._phase += angle
        self._phase %= 2 * math.pi

def tone(sample_rate: int, frequency: float, n: int) -> list[float]:
    phase_advance = 2 * math.pi * frequency / sample_rate
    phase = 0
    output = []

    for _ in range(n):
        output.append(math.cos(phase))
        phase += phase_advance
    
    return output
