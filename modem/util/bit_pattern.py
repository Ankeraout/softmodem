
import modem

class PatternBitProvider(modem.IBitProvider):
    def __init__(self, pattern: list[int]) -> None:
        self._pattern = pattern
        self._index = 0

    def get_bits(self, n: int) -> list[int]:
        bits = []

        for _ in range(n):
            bits.append(self._pattern[self._index])
            self._index += 1
            self._index %= len(self._pattern)
        
        return bits
    
    @property
    def pattern(self) -> list[int]:
        return self._pattern
    
    @pattern.setter
    def pattern(self, pattern: list[int]) -> None:
        self._pattern = pattern
        self._index = 0

class PatternBitReceiver(modem.IBitReceiver):
    def __init__(self, pattern: list[int]) -> None:
        self._pattern = pattern
        self._index = 0
        self._count = 0
        self._best = 0

    def receive_bits(self, bits: list[int]) -> None:
        for bit in bits:
            if bit == self._pattern[self._index]:
                self._count += 1
                self._index += 1
                self._index %= len(self._pattern)

                if self._count > self._best:
                    self._best = self._count
            
            else:
                self._count = 0
                self._index = 0

    @property
    def count(self) -> int:
        return self._count
    
    @property
    def best(self) -> int:
        return self._best
    
    def reset(self) -> None:
        self._count = 0
        self._best = 0
        self._index = 0

class TransitionCounter(modem.IBitReceiver):
    def __init__(self, n: int) -> None:
        self._state = [0] * n
        self._write_index = 0

    def receive_bits(self, bits: list[int]) -> None:
        for bit in bits:
            self._state[self._write_index] = bit
            self._write_index += 1
            self._write_index %= len(self._state)

    def get_transition_count(self) -> int:
        return sum(
            self._state[i] != self._state[i + 1]
            for i in range(len(self._state) - 1)
        )

class BitReceiverSplitter(modem.IBitReceiver):
    def __init__(self, receivers: list[modem.IBitReceiver]) -> None:
        self._receivers = receivers
    
    def receive_bits(self, bits: list[int]) -> None:
        for receiver in self._receivers:
            receiver.receive_bits(bits)
