import random

class Scrambler:
    def __init__(self, polynomial: int, state: int | None = None) -> None:
        self._polynomial = polynomial >> 1
        self._state_mask = 2 ** self._polynomial.bit_length() - 1
        self._state = (
            random.randint(0, 2 ** self._polynomial.bit_length()) 
            if state is None
            else state
        )
    
    def scramble(self, bits: list[int]) -> list[int]:
        result: list[int] = []

        for bit in bits:
            sbit = ((self._state & self._polynomial).bit_count() & 1) ^ bit
            self._state = ((self._state << 1) & self._state_mask) | sbit
            result.append(sbit)

        return result
    
class Unscrambler:
    def __init__(self, polynomial: int, state: int | None = None) -> None:
        self._polynomial = polynomial >> 1
        self._state_mask = 2 ** self._polynomial.bit_length() - 1
        self._state = (
            random.randint(0, 2 ** self._polynomial.bit_length()) 
            if state is None
            else state
        )

    def unscramble(self, bits: list[int]) -> None:
        result: list[int] = []

        for bit in bits:
            sbit = ((self._state & self._polynomial).bit_count() & 1) ^ bit
            self._state = ((self._state << 1) & self._state_mask) | bit
            result.append(sbit)

        return result
