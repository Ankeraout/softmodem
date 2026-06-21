import math

class AGC:
    def __init__(self, alpha: float) -> None:
        self._alpha = alpha
        self._power = 1

    def receive_samples(self, samples: list[complex]) -> list[complex]:
        output: list[complex] = []

        for sample in samples:
            self._power = (
                (1 - self._alpha) * self._power
                + self._alpha * (sample.real ** 2 + sample.imag ** 2)
            )

            if self._power == 0:
                gain = 1

            else:
                gain = 1 / math.sqrt(self._power)

            output.append(sample * gain)

        return output
            