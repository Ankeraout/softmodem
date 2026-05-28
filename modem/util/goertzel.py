import cmath
import math
import modem

class SlidingGoertzel(modem.IAnalogReceiver):
    def __init__(self, sample_rate: int, frequency: float, window_size: int) -> None:
        self._sample_rate = sample_rate
        self._frequency = frequency
        self._phase_advance = 2 * math.pi * frequency / sample_rate
        self._phase = 0
        self._fifo = [0] * window_size
        self._fifo_write_index = 0
        self._fifo_sum = 0

    def receive_samples(self, samples: list[float]) -> None:
        for sample in samples:
            self._fifo_sum -= self._fifo[self._fifo_write_index]
            self._fifo[self._fifo_write_index] = sample * cmath.exp(complex(imag=-self._phase))
            self._fifo_sum += self._fifo[self._fifo_write_index]
            self._fifo_write_index = (self._fifo_write_index + 1) % len(self._fifo)
            self._phase += self._phase_advance
    
    def get_value(self) -> float:
        return abs(self._fifo_sum) / len(self._fifo)
    
    def clear(self) -> None:
        self._fifo = [0] * len(self._fifo)
