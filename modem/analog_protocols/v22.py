import cmath
import enum
import modem
import modem.util.agc
import modem.util.costas
import modem.util.gardner
import modem.util.goertzel
import modem.util.rrc
import modem.util.tone
import scipy.signal
import threading
import typing

SAMPLE_RATE_EXTERNAL = 8000
SAMPLE_RATE_FACTOR = 3
SAMPLE_RATE_INTERNAL = SAMPLE_RATE_EXTERNAL * SAMPLE_RATE_FACTOR
TONE_THRESHOLD_UP = 0.02
TONE_THRESHOLD_DOWN = 0.01
SYMBOL_RATE = 600
INTERNAL_SAMPLES_PER_SYMBOL = SAMPLE_RATE_INTERNAL // SYMBOL_RATE

class V22Receiver(modem.IAnalogReceiver):
    class _Unscrambler:
        def __init__(self) -> None:
            self._state: list[int] = [
                0, 1, 1, 0, 1, 0, 0, 1,
                0, 0, 1, 1, 1, 1, 0, 0,
                1
            ]
            self._write_index = 0

        def unscramble(self, bits: list[int]) -> None:
            result: list[int] = []

            for bit in bits:
                bit_x14_index = (self._write_index - 14) % len(self._state)
                bit_x17_index = (self._write_index - 17) % len(self._state)

                bit_x14 = self._state[bit_x14_index]
                bit_x17 = self._state[bit_x17_index]

                result.append(bit ^ bit_x14 ^ bit_x17)

                self._state[self._write_index] = bit
                self._write_index = (self._write_index + 1) % len(self._state)

            return result
        
    class _TransitionCounter(modem.IBitReceiver):
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

    def __init__(
        self,
        role: modem.Role,
        bit_receiver: modem.IBitReceiver
    ) -> None:
        self.bit_receiver = bit_receiver
        self._filter = modem.util.rrc.rrc(
            0.75,
            INTERNAL_SAMPLES_PER_SYMBOL,
            6
        )
        self._filter_state = [0] * (len(self._filter) - 1)
        self._upscale_filter = scipy.signal.firwin(
            61,
            SAMPLE_RATE_EXTERNAL // 2,
            fs=SAMPLE_RATE_INTERNAL
        )
        self._upscale_filter_state = [0] * (len(self._upscale_filter) - 1)
        self._phase = 0
        self._phase_advance = 2 * cmath.pi / SAMPLE_RATE_INTERNAL
        self._phase_advance *= 2400 if role == modem.Role.CALLER else 1200
        self._gardner = modem.util.gardner.Gardner(
            INTERNAL_SAMPLES_PER_SYMBOL,
            0.008,
            0.000035
        )
        self._previous_symbol: complex | None = None
        self.enable_unscrambler: bool = True
        self._unscrambler = V22Receiver._Unscrambler()
        self.enable_transition_counter: bool = True
        self._transition_counter = self._TransitionCounter(int(1200 * 0.27))
        self._costas = modem.util.costas.Costas(
            modem.util.costas.Costas.slicer_qpsk,
            0.03,
            0.0005,
            40
        )
        self._agc = modem.util.agc.AGC()

    def get_transition_rate(self) -> float:
        return self._transition_counter.get_transition_count() / (1200 * 0.27)
    
    def filter_samples(self, samples: list[float]) -> list[complex]:
        samples_mixed = []

        for sample in samples:
            samples_mixed.append(sample * cmath.exp(complex(imag=self._phase)))
            self._phase += self._phase_advance * 3
            self._phase %= 2 * cmath.pi

        samples_padded = [0] * (len(samples) * 3)
        samples_padded[::3] = samples_mixed

        samples_filtered, self._filter_state = scipy.signal.lfilter(
            self._filter,
            1,
            samples_padded,
            zi=self._filter_state
        )

        return samples_filtered

    def receive_samples(self, samples: list[float]) -> None:
        samples_filtered = self.filter_samples(samples)
        samples_normalized = self._agc.receive_samples(samples_filtered)
        samples_fixed = self._costas.receive_samples(samples_normalized)

        for symbol in self._gardner.receive_samples(samples_fixed):
            if self._previous_symbol is not None:
                phase_difference = cmath.phase(
                    self._previous_symbol * symbol.conjugate()
                )

                if abs(phase_difference) >= 3 * cmath.pi / 4:
                    bits = [1, 0]
                
                elif abs(phase_difference) < cmath.pi / 4:
                    bits = [0, 1]

                elif phase_difference < 0:
                    bits = [1, 1]

                else:
                    bits = [0, 0]

                if self.enable_transition_counter:
                    self._transition_counter.receive_bits(bits)

                if self.enable_unscrambler:
                    bits = self._unscrambler.unscramble(bits)

                self.bit_receiver.receive_bits(bits)

            self._previous_symbol = symbol

class V22Sender(modem.IAnalogProvider):
    class _Scrambler:
        def __init__(self) -> None:
            self._state: list[int] = [
                0, 1, 1, 0, 1, 0, 0, 1,
                0, 0, 1, 1, 1, 1, 0, 0,
                1
            ]
            self._write_index = 0
        
        def scramble(self, bits: list[int]) -> list[int]:
            result: list[int] = []

            for bit in bits:
                bit_x14_index = (self._write_index - 14) % len(self._state)
                bit_x17_index = (self._write_index - 17) % len(self._state)
                bit_x14 = self._state[bit_x14_index]
                bit_x17 = self._state[bit_x17_index]

                scrambled_bit = bit ^ bit_x14 ^ bit_x17

                result.append(scrambled_bit)

                self._state[self._write_index] = scrambled_bit
                self._write_index = (self._write_index + 1) % len(self._state)

            return result
        
    def __init__(
        self,
        role: modem.Role,
        bit_provider: modem.IBitProvider
    ) -> None:
        self.bit_provider = bit_provider
        self._filter = modem.util.rrc.rrc(
            0.75,
            SAMPLE_RATE_INTERNAL // SYMBOL_RATE,
            6
        )
        self._filter_state = [0] * (len(self._filter) - 1)
        self._phase = 0
        self._phase_advance = 2 * cmath.pi / SAMPLE_RATE_EXTERNAL
        self._phase_advance *= 1200 if role == modem.Role.CALLER else 2400
        self._symbol_phase = 0
        self._scrambler = V22Sender._Scrambler()
        self.enable_scrambler = True
        self._symbol_t = 0

    def get_samples(self, n: int) -> list[float]:
        buffer = []

        for _ in range(n * 3):
            if self._symbol_t == 0:
                bits = self.bit_provider.get_bits(2)

                if self.enable_scrambler:
                    bits = self._scrambler.scramble(bits)

                match bits:
                    case [0, 0]:
                        phase_shift = cmath.pi / 2

                    case [0, 1]:
                        phase_shift = 0

                    case [1, 0]:
                        phase_shift = cmath.pi

                    case [1, 1]:
                        phase_shift = -cmath.pi / 2

                self._symbol_phase += phase_shift
                self._symbol_phase %= 2 * cmath.pi

                buffer.append(cmath.exp(complex(imag=-self._symbol_phase)))
            
            else:
                buffer.append(0)

            self._symbol_t += 1
            self._symbol_t %= INTERNAL_SAMPLES_PER_SYMBOL
        
        filtered_samples, self._filter_state = scipy.signal.lfilter(
            self._filter,
            1,
            buffer,
            zi=self._filter_state
        )

        decimated_samples = filtered_samples[::3]

        shifted_samples = []

        for sample in decimated_samples:
            shifted_samples.append(
                (sample * cmath.exp(complex(imag=-self._phase))).real
            )
            self._phase += self._phase_advance
            self._phase %= 2 * cmath.pi
        
        return shifted_samples

    def _get_bits(self, n: int) -> list[int]:
        bits = self._bit_provider.get_bits(n)
        
        if self.enable_scrambler:
            bits = self._scrambler.scramble(bits)

        return bits

class V22(modem.IAnalogProtocol):
    class _State(enum.Enum):
        CALLER_WAITING_FOR_2250HZ = enum.auto()
        CALLER_HOLDING_2250HZ = enum.auto()
        CALLER_2250HZ_DETECTED = enum.auto()
        CALLER_SENDING_SCRAMBLED_1 = enum.auto()
        CALLER_SCRAMBLED_1_DETECTED = enum.auto()
        CALLEE_SENDING_UNSCRAMBLED_1 = enum.auto()
        CALLEE_SENDING_SCRAMBLED_1 = enum.auto()
        DATA = enum.auto()

    class _OneBitProvider(modem.IBitProvider):
        def get_bits(self, n: int) -> list[int]:
            return [1] * n
        
    class _HandshakeBitReceiver(modem.IBitReceiver):
        def __init__(self) -> None:
            self._consecutive_ones = 0

        def receive_bits(self, bits: list[int]) -> None:
            for bit in bits:
                if bit == 0:
                    self._consecutive_ones = 0

                else:
                    self._consecutive_ones += 1

        @property
        def consecutive_ones(self) -> int:
            return self._consecutive_ones

        def reset(self) -> None:
            self._consecutive_ones = 0

    def __init__(
        self,
        bit_protocol: modem.IBitProtocol,
        role: modem.Role,
        connect_callback: typing.Callable[[int, int], None] | None = None
    ) -> None:
        self._bit_protocol = bit_protocol
        self._lock = threading.RLock()

        if role == modem.Role.CALLER:
            self._state = V22._State.CALLER_WAITING_FOR_2250HZ

        else:
            self._state = V22._State.CALLEE_SENDING_UNSCRAMBLED_1

        self._tone_detector = modem.util.goertzel.SlidingGoertzel(
            SAMPLE_RATE_EXTERNAL,
            2250 if role == modem.Role.CALLER else 1050,
            800
        )
        self._timer: float = 0
        self._phase: float = 0
        self._handshake_bit_receiver = V22._HandshakeBitReceiver()
        self._handshake_bit_sender = V22._OneBitProvider()
        self._receiver = V22Receiver(role, self._handshake_bit_receiver)
        self._sender = V22Sender(role, self._handshake_bit_sender)
        self._connect_callback = connect_callback
        self._tone_generator = modem.util.tone.ToneGenerator(
            SAMPLE_RATE_EXTERNAL,
            2250
        )

    def receive_samples(self, samples: list[float]) -> None:
        match self._state:
            case V22._State.CALLER_WAITING_FOR_2250HZ:
                self._tone_detector.receive_samples(samples)

                if self._tone_detector.get_value() >= TONE_THRESHOLD_UP:
                    print("[V22] Detected 2250 Hz tone.")
                    self._timer = 0.155
                    self._change_state(V22._State.CALLER_HOLDING_2250HZ)
                
            case V22._State.CALLER_HOLDING_2250HZ:
                self._tone_detector.receive_samples(samples)

                if self._tone_detector.get_value() < TONE_THRESHOLD_DOWN:
                    print("[V22] Lost 2250 Hz tone.")
                    self._change_state(V22._State.CALLER_WAITING_FOR_2250HZ)
                
                else:
                    self._timer -= len(samples) / SAMPLE_RATE_EXTERNAL

                    if self._timer <= 0:
                        print("[V22] 2250 Hz tone held for 155ms.")
                        self._change_state(V22._State.CALLER_2250HZ_DETECTED)
                        self._timer = 0.456

            case V22._State.CALLER_2250HZ_DETECTED:
                self._timer -= len(samples) / SAMPLE_RATE_EXTERNAL

                if self._timer <= 0:
                    print("[V22] Sending scrambled 1.")
                    self._change_state(V22._State.CALLER_SENDING_SCRAMBLED_1)
            
            case V22._State.CALLER_SENDING_SCRAMBLED_1:
                self._receiver.receive_samples(samples)

                if(
                    self._handshake_bit_receiver.consecutive_ones >= 1200 * 0.27
                    and self._receiver.get_transition_rate() >= 0.4
                ):
                    print("[V22] Detected scrambled 1.")
                    self._change_state(V22._State.CALLER_SCRAMBLED_1_DETECTED)
                    self._timer = 0.765

            case V22._State.CALLER_SCRAMBLED_1_DETECTED:
                self._receiver.receive_samples(samples)
                self._timer -= len(samples) / SAMPLE_RATE_EXTERNAL

                if self._timer <= 0:
                    print("[V22] Switching to data mode.")

                    if self._connect_callback is not None:
                        self._connect_callback(1200, 1200)

                    self._change_state(V22._State.DATA)

            case V22._State.CALLEE_SENDING_UNSCRAMBLED_1:
                self._receiver.receive_samples(samples)

                if(
                    self._handshake_bit_receiver.consecutive_ones >= 1200 * 0.27
                    and self._receiver.get_transition_rate() >= 0.4
                ):
                    print("[V22] Sending scrambled 1.")
                    self._change_state(V22._State.CALLEE_SENDING_SCRAMBLED_1)
                    self._timer = 0.765

            case V22._State.CALLEE_SENDING_SCRAMBLED_1:
                self._timer -= len(samples) / SAMPLE_RATE_EXTERNAL
                self._receiver.receive_samples(samples)

                if self._timer <= 0:
                    print("[V22] Switching to data mode.")

                    if self._connect_callback is not None:
                        self._connect_callback(1200, 1200)

                    self._change_state(V22._State.DATA)

            case V22._State.DATA:
                self._receiver.receive_samples(samples)
    
    def get_samples(self, n: int) -> list[float]:
        match self._state:
            case V22._State.CALLER_SENDING_SCRAMBLED_1:
                samples = self._sender.get_samples(n)

            case V22._State.CALLER_SCRAMBLED_1_DETECTED:
                samples = self._sender.get_samples(n)

            case V22._State.CALLEE_SENDING_UNSCRAMBLED_1:
                samples = self._tone_generator.get_samples(n)

            case V22._State.CALLEE_SENDING_SCRAMBLED_1:
                samples = self._sender.get_samples(n)

            case V22._State.DATA:
                samples = self._sender.get_samples(n)

            case _:
                samples = [0] * n
        
        return samples
    
    def _change_state(self, state: _State) -> None:
        self._state = state
        self._receiver.enable_transition_counter = state in (
            V22._State.CALLER_SENDING_SCRAMBLED_1,
            V22._State.CALLEE_SENDING_UNSCRAMBLED_1
        )
        self._sender.bit_provider = (
            self._bit_protocol if state == V22._State.DATA
            else self._handshake_bit_sender
        )
        self._receiver.bit_receiver = (
            self._bit_protocol if state == V22._State.DATA
            else self._handshake_bit_receiver
        )
