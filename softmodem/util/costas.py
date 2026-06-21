import cmath
import typing

SQRT_2 = 2 ** 0.5

def sign(n: float) -> float:
    return -1 if n < 0 else 0 if n == 0 else 1

class Costas:
    def __init__(
        self,
        slicer: typing.Callable[[complex], complex],
        alpha: float,
        beta: float,
        samples_per_symbol
    ) -> None:
        self._alpha = alpha
        self._beta = beta
        self._samples_per_symbol = samples_per_symbol
        self.slicer = slicer
        self._increment = 0
        self._phase = 0
        self._frequency = 0
        self._integrated_error = 0

    def receive_samples(self, samples: list[complex]) -> list[complex]:
        result = []

        for sample in samples:
            sample_fixed = sample * cmath.exp(complex(imag=-self._phase))
            result.append(sample_fixed)

            self._integrated_error += self._error(sample_fixed)
            self._increment += 1

            if self._increment >= self._samples_per_symbol:
                error = self._integrated_error / self._samples_per_symbol

                self._frequency += self._beta * error
                self._phase += self._frequency + self._alpha * error
                self._phase %= 2 * cmath.pi

                self._increment -= self._samples_per_symbol
                self._integrated_error = 0

        return result
    
    def _error(self, sample: complex) -> float:
        return (self.slicer(sample).conjugate() * sample).imag
