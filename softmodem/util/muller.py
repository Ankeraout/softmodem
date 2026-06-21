import math
import typing

# Muller & Mueller loop implementation
class Muller:
    def __init__(
        self,
        samples_per_symbol: float,
        slicer: typing.Callable[[complex], complex],
        gain_mu: float,
        gain_omega: float
    ) -> None:
        self._samples_per_symbol = samples_per_symbol
        self.slicer = slicer
        self._omega = samples_per_symbol
        self._mu = 0

        self._gain_mu = gain_mu
        self._gain_omega = gain_omega

        self._buffer = []

        self._previous_sample = 0
        self._previous_decision = 0

    @staticmethod
    def interpolate(x0: complex, x1: complex, mu: float) -> complex:
        return x0 + mu * (x1 - x0)
    
    def receive_samples(self, samples: list[complex]) -> list[complex]:
        self._buffer += samples

        out = []
        i = 0

        while i + int(math.ceil(self._omega)) + 1 < len(self._buffer):
            base = int(i + self._mu)
            frac = (i + self._mu) - base

            sample = self.interpolate(
                self._buffer[base],
                self._buffer[base + 1],
                frac
            )

            decision = self.slicer(sample)

            error = (
                self._previous_decision.conjugate() * sample
                - decision.conjugate() * self._previous_sample
            ).real

            self._omega += self._gain_omega * error
            self._mu += self._omega + self._gain_mu * error

            step = int(self._mu)
            self._mu -= step

            i += step

            self._previous_sample = sample
            self._previous_decision = decision

            out.append(sample)

        self._buffer = self._buffer[i:]

        return out
