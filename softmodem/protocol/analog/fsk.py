import cmath
import math
import softmodem
import scipy.signal

class FSKReceiver(softmodem.IAnalogReceiver):
    def __init__(
        self,
        bit_receiver: softmodem.IBitReceiver,
        f0: float,
        f1: float,
        samples_per_second: int,
        symbols_per_second: int
    ) -> None:
        self._bit_receiver = bit_receiver
        center_frequency = (f0 + f1) / 2
        self._phase_advance = 2 * math.pi * center_frequency / samples_per_second
        self._phase: float = 0
        self._shift_filter = scipy.signal.firwin(81, abs(f0 - f1) * 0.6, fs=samples_per_second)
        self._shift_filter_state = [0] * (len(self._shift_filter) - 1)
        self._pulse_filter = [1] * (samples_per_second // symbols_per_second)
        self._pulse_filter_state = [0] * (len(self._pulse_filter) - 1)
        self._previous_shifted_sample = 0
        self._filter_delay = (len(self._shift_filter_state) + len(self._pulse_filter_state)) // 2
        self._t = 0
        self._t_factor = math.lcm(samples_per_second, symbols_per_second) // samples_per_second
        self._t_per_symbol = samples_per_second * self._t_factor // symbols_per_second
        self._previous_sign = -1
        self._invert = f0 < f1
        self._sample_t_min = (self._t_per_symbol - self._t_factor) // 2
        self._sample_t_max = self._sample_t_min + self._t_factor

    def receive_samples(self, samples: list[float]) -> None:
        rx_buffer: list[int] = []

        # Shift the signal to center it around 0 Hz
        samples_shifted = []

        for sample in samples:
            samples_shifted.append(sample * cmath.exp(self._phase * -1j))
            self._phase = (self._phase + self._phase_advance) % (2 * math.pi)
        
        # Filter the high-frequency component
        samples_shifted, self._shift_filter_state = scipy.signal.lfilter(self._shift_filter, 1, samples_shifted, zi=self._shift_filter_state)

        # Compute the phase difference signal
        samples_phase_difference = []

        for sample in samples_shifted:
            phase_difference = cmath.phase(sample * self._previous_shifted_sample.conjugate())
            self._previous_shifted_sample = sample
            samples_phase_difference.append(phase_difference)

        # Filter the phase difference signal
        samples_phase_difference, self._pulse_filter_state = scipy.signal.lfilter(self._pulse_filter, 1, samples_phase_difference, zi=self._pulse_filter_state)

        if self._filter_delay > 0:
            if len(samples_phase_difference) < self._filter_delay:
                self._filter_delay -= len(samples_phase_difference)
                samples_phase_difference = []

            else:
                samples_phase_difference = samples_phase_difference[self._filter_delay:]
                self._filter_delay = 0

        # Demodulation
        for sample in samples_phase_difference:
            sign = -1 if sample < 0 else 1

            # Perform bit sync
            if sign != self._previous_sign:
                self._previous_sign = sign
                self._t = 0

            else:
                if self._t >= self._sample_t_min and self._t < self._sample_t_max:
                    bit = 1 if sample < 0 else 0
                    rx_buffer.append(1 - bit if self._invert else bit)
                
                self._t = (self._t + self._t_factor) % self._t_per_symbol

        self._bit_receiver.receive_bits(rx_buffer)

class FSKSender(softmodem.IAnalogProvider):
    def __init__(
        self,
        bit_provider: softmodem.IBitProvider,
        f0: float,
        f1: float,
        samples_per_second: int,
        symbols_per_second: int
    ) -> None:
        self._bit_provider = bit_provider
        self._phase_advance = [2 * math.pi * f / samples_per_second for f in (f0, f1)]
        self._t: int = 0
        self._phase: float = 0
        self._symbol: int = bit_provider.get_bits(1)[0]
        self._t_factor = math.lcm(samples_per_second, symbols_per_second) // samples_per_second
        self._t_per_symbol = samples_per_second * self._t_factor // symbols_per_second

    def get_samples(self, n: int) -> list[float]:
        samples: list[float] = []

        for _ in range(n):
            samples.append(math.sin(self._phase))
            
            self._t += self._t_factor

            if self._t >= self._t_per_symbol:
                self._t %= self._t_per_symbol

                new_symbol = self._bit_provider.get_bits(1)[0]
                self._phase += (self._t * self._phase_advance[new_symbol] + (self._t_factor - self._t) * self._phase_advance[self._symbol]) / self._t_factor
                self._symbol = new_symbol
            
            else:
                self._phase += self._phase_advance[self._symbol]

            self._phase %= 2 * math.pi

        return samples
