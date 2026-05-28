import enum
import math
import modem

FREQUENCY_TABLE = {
    "1": [697, 1209],
    "2": [697, 1336],
    "3": [697, 1477],
    "A": [697, 1633],
    "4": [770, 1209],
    "5": [770, 1336],
    "6": [770, 1477],
    "B": [770, 1633],
    "7": [852, 1209],
    "8": [852, 1336],
    "9": [852, 1477],
    "C": [852, 1633],
    "*": [941, 1336],
    "0": [941, 1336],
    "#": [941, 1477],
    "D": [941, 1633]
}
SYMBOL_DURATION_MS = 75
SYMBOL_PAUSE_MS = 75
SYMBOL_TIME_MS = SYMBOL_DURATION_MS + SYMBOL_PAUSE_MS

class State(enum.Enum):
    INITIAL = 0
    SYMBOL = 1
    PAUSE = 2

class DTMFSender(modem.IAnalogProvider, modem.IByteSender):
    def __init__(self, sample_rate: int) -> None:
        self._phases = [0, 0]
        self._phase_advances = []
        self._t = 0
        self._buffer = []
        self._t_factor = math.lcm(sample_rate, round(1000 / SYMBOL_DURATION_MS)) // sample_rate
        self._t_end_symbol = round(sample_rate * (SYMBOL_DURATION_MS / 1000) * self._t_factor)
        self._t_end_pause = self._t_end_symbol + round(sample_rate * (SYMBOL_PAUSE_MS / 1000) * self._t_factor)
        self._state = State.INITIAL
        self._sample_rate = sample_rate

    def get_samples(self, n: int) -> list[float]:
        buffer: list[float] = []

        for _ in range(n):
            match self._state:
                case State.INITIAL:
                    buffer.append(0)

                    if len(self._buffer) != 0:
                        digit = self._buffer.pop(0)

                        if digit in FREQUENCY_TABLE:
                            self._phase_advances = [2 * math.pi * f / self._sample_rate for f in FREQUENCY_TABLE[digit]]
                    
                        self._state = State.SYMBOL
                        self._t = 0
                        self._phases = [0, 0]
                
                case State.SYMBOL:
                    buffer.append(sum(math.sin(p) * 0.2 for p in self._phases))
                    self._phases = [(p + pa) % (2 * math.pi) for p, pa in zip(self._phases, self._phase_advances)]
                
                    if self._t >= self._t_end_symbol:
                        self._state = State.PAUSE

                    self._t += self._t_factor

                case State.PAUSE:
                    buffer.append(0)

                    if self._t >= self._t_end_pause:
                        self._state = State.INITIAL
                    
                    self._t += self._t_factor

        for sample in buffer:
            if sample < -1 or sample > 1:
                print(sample)

        return buffer
    
    def send_bytes(self, data: bytes) -> None:
        self._buffer.extend(data.decode())
                    