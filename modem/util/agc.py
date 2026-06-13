import math
import typing

class AGC:
    def __init__(
        self,
        alpha: float,
        slicer: typing.Callable[[complex], complex]
    ) -> None:
        self._alpha = alpha
        self._slicer = slicer
        self._power = 1

    def receive_samples(self, samples: list[complex]) -> list[complex]:
        output: list[complex] = []

        for sample in samples:
            scaled_sample = sample * (1 / math.sqrt(self._power))
            decided_symbol = self._slicer(scaled_sample)
            symbol_power = decided_symbol.real ** 2 + decided_symbol.imag ** 2

            self._power = (
                (1 - self._alpha) * self._power
                + self._alpha * symbol_power
            )

            gain = 1 if self._power == 0 else 1 / math.sqrt(self._power)

            output.append(sample * gain)

        return output
            