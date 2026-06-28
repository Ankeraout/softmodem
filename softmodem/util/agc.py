import math

class AGC:
    def __init__(self, alpha: float) -> None:
        self._alpha = alpha
        self._power = 1
        self.auto_update = True

    def receive_samples(self, samples: list[complex]) -> list[complex]:
        output: list[complex] = []

        for sample in samples:
            if self._power <= 0:
                gain = 1

            else:
                gain = 1 / math.sqrt(self._power)

            corrected = sample * gain

            if self.auto_update:
                self.update(corrected, 1)

            output.append(corrected)

        return output
    
    def update(
        self,
        received_symbol: complex,
        expected_symbol: complex
    ) -> None:
        received_power = received_symbol.real ** 2 + received_symbol.imag ** 2
        expected_power = expected_symbol.real ** 2 + expected_symbol.imag ** 2
        error = received_power - expected_power

        self._power = (
            (1 - self._alpha) * self._power
            + self._alpha * (self._power + error)
        )
