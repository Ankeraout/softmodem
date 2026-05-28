import cmath

def sign(n: float) -> float:
    return -1 if n < 0 else 0 if n == 0 else 1

class Costas:
    def __init__(
        self,
        alpha: float = 0.01,
        beta: float = 0.00001,
        samples_per_symbol: float = 1.0
    ) -> None:
        self._alpha = alpha
        self._beta = beta
        self._samples_per_symbol = samples_per_symbol
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
    
    @staticmethod
    def _error(sample: complex) -> float:
        a = sign(sample.real)
        b = sign(sample.imag)

        return a * sample.imag - b * sample.real
