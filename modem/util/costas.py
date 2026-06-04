import cmath
import typing

SQRT_2 = 2 ** 0.5

def sign(n: float) -> float:
    return -1 if n < 0 else 0 if n == 0 else 1

class Costas:
    def __init__(
        self,
        slicer: typing.Callable[[complex], complex],
        alpha: float = 0.01,
        beta: float = 0.00001,
        samples_per_symbol: float = 1.0
    ) -> None:
        self._alpha = alpha
        self._beta = beta
        self._samples_per_symbol = samples_per_symbol
        self._slicer = slicer
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
        return (self._slicer(sample).conjugate() * sample).imag
    
    @staticmethod
    def slicer_qpsk(sample: complex) -> complex:
        return complex(
            -1 if sample.real < 0 else 1,
            -1 if sample.imag < 0 else 1
        ) / SQRT_2
    
    @staticmethod
    def single_axis_slicer(
        value: float,
        min: float,
        max: float,
        steps: int
    ) -> float:
        if value < min:
            return min
        
        elif value > max:
            return max
        
        else:
            amplitude = max - min
            progress = (value - min) / amplitude
            step = progress * (steps - 1)
            quantized = round(step)
            final = quantized * amplitude / (steps - 1) + min

            return final

    @staticmethod
    def slicer_qam16(sample: complex) -> complex:
        return complex(
            Costas.single_axis_slicer(sample.real, -SQRT_2 / 2, SQRT_2 / 2, 4),
            Costas.single_axis_slicer(sample.imag, -SQRT_2 / 2, SQRT_2 / 2, 4)
        )
