import cmath
import enum
import modem
import modem.analog_protocols.v22
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

class V22bisReceiver(modem.IAnalogReceiver):
    _Unscrambler = modem.analog_protocols.v22.V22Receiver._Unscrambler
        
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
            0.1,
            0.00001
        )
        self._previous_symbol: complex | None = None
        self._previous_symbol_quadrant: int = 1
        self.enable_unscrambler: bool = True
        self._unscrambler = V22bisReceiver._Unscrambler()
        self.enable_transition_counter: bool = True
        self._transition_counter = self._TransitionCounter(int(2400 * 0.27))
        self._costas = modem.util.costas.Costas(
            modem.util.costas.Costas.slicer_qam16,
            0.1,
            0.0001,
            40
        )
        self._agc = modem.util.agc.AGC(0.0001)
        self._symbols = []
        self._speed = 1200

    @property
    def speed(self) -> int:
        return self._speed
    
    @speed.setter
    def speed(self, value: int) -> None:
        if value not in (1200, 2400):
            raise ValueError("Invalid bitrate value.")

        self._costas._slicer = (
            modem.util.costas.Costas.slicer_qam16 if value == 2400
            else modem.util.costas.Costas.slicer_qpsk
        )

    def get_transition_rate(self) -> float:
        return self._transition_counter.get_transition_count() / (2400 * 0.27)
    
    def filter_samples(self, samples: list[float]) -> list[complex]:
        samples_mixed = []

        for sample in samples:
            samples_mixed.append(sample * cmath.exp(complex(imag=-self._phase)))
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
            symbol_quadrant = V22bisReceiver._get_quadrant(symbol)

            if self._previous_symbol is not None:
                bits = V22bisReceiver._get_quadrant_dibit(
                    self._previous_symbol_quadrant,
                    symbol_quadrant
                )

                if self._speed == 2400:
                    last_dibit = V22bisReceiver._get_last_dibit(
                        symbol_quadrant,
                        symbol * 2 / 3
                    )

                    bits += last_dibit
                
                if self.enable_transition_counter:
                    self._transition_counter.receive_bits(bits)

                if self.enable_unscrambler:
                    bits = self._unscrambler.unscramble(bits)

                self.bit_receiver.receive_bits(bits)

            self._previous_symbol = symbol
            self._previous_symbol_quadrant = symbol_quadrant

    @staticmethod
    def _get_last_dibit(quadrant: int, symbol: complex) -> int:
        match quadrant:
            case 2:
                symbol *= cmath.exp(complex(imag=-cmath.pi / 2))

            case 3:
                symbol *= cmath.exp(complex(imag=cmath.pi))

            case 4:
                symbol *= cmath.exp(complex(imag=cmath.pi / 2))

        return [
            1 if symbol.imag >= 2 * 2 ** 0.5 / 6 else 0,
            1 if symbol.real >= 2 * 2 ** 0.5 / 6 else 0
        ]

    @staticmethod
    def _get_quadrant(symbol: complex) -> int:
        if symbol.real < 0:
            if symbol.imag < 0:
                return 3
            
            else:
                return 2
        
        elif symbol.imag < 0:
            return 4
        
        else:
            return 1

    @staticmethod
    def _get_quadrant_dibit(previous_quadrant: int, quadrant: int) -> list[int]:
        match (quadrant - previous_quadrant) % 4:
            case 1:
                return [0, 0]
            
            case 2:
                return [1, 0]
            
            case 3:
                return [1, 1]
            
            case _:
                return [0, 1]

class V22bisSender(modem.IAnalogProvider):
    _Scrambler = modem.analog_protocols.v22.V22Sender._Scrambler
        
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
        self._quadrant_phase = 0
        self._scrambler = V22bisSender._Scrambler()
        self.enable_scrambler = True
        self._symbol_t = 0
        self._speed = 1200

    def get_samples(self, n: int) -> list[float]:
        buffer = []

        for _ in range(n * 3):
            if self._symbol_t == 0:
                bits = self.bit_provider.get_bits(
                    4 if self._speed == 2400 else 2
                )

                if self.enable_scrambler:
                    bits = self._scrambler.scramble(bits)
                
                match bits[:2]:
                    case [0, 0]:
                        self._quadrant_phase += cmath.pi / 2

                    case [1, 0]:
                        self._quadrant_phase += cmath.pi

                    case [1, 1]:
                        self._quadrant_phase -= cmath.pi / 2

                self._quadrant_phase %= 2 * cmath.pi

                if self._speed == 2400:
                    match bits[2:4]:
                        case [0, 0]:
                            symbol = complex(2 ** 0.5 / 6, 2 ** 0.5 / 6)

                        case [0, 1]:
                            symbol = complex(2 ** 0.5 / 2, 2 ** 0.5 / 6)

                        case [1, 0]:
                            symbol = complex(2 ** 0.5 / 6, 2 ** 0.5 / 2)

                        case [1, 1]:
                            symbol = complex(2 ** 0.5 / 2, 2 ** 0.5 / 2)
                    
                else:
                    symbol = complex(2 ** 0.5 / 2, 2 ** 0.5 / 2)

                symbol *= cmath.exp(complex(imag=self._quadrant_phase))
                buffer.append(symbol)
            
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
                (sample * cmath.exp(complex(imag=self._phase))).real
            )
            self._phase += self._phase_advance
            self._phase %= 2 * cmath.pi
        
        return shifted_samples

class V22bis(modem.IAnalogProtocol):
    class _State(enum.Enum):
        CALLER_WAITING_FOR_2250HZ = enum.auto()
        CALLER_HOLDING_2250HZ = enum.auto()
        CALLER_2250HZ_DETECTED = enum.auto()
        CALLER_SENDING_UNSCRAMBLED_0011 = enum.auto()
        CALLER_SENDING_SCRAMBLED_1_1200 = enum.auto()
        CALLER_UNSCRAMBLED_0011_DETECTED = enum.auto()
        CALLER_SCRAMBLED_1_DETECTED = enum.auto()
        CALLER_RECEIVE_2400 = enum.auto()
        CALLER_SENDING_SCRAMBLED_1_2400 = enum.auto()
        CALLER_WAITING_SCRAMBLED_1_2400 = enum.auto()
        CALLEE_SENDING_UNSCRAMBLED_1 = enum.auto()
        DATA = enum.auto()
        
    class _PatternBitProvider(modem.IBitProvider):
        def __init__(self, pattern: list[int], enable_scrambler: bool = False) -> None:
            self._scrambler = V22bisSender._Scrambler()
            self.enable_scrambler = enable_scrambler
            self._pattern = pattern
            self._index = 0

        def get_bits(self, n: int) -> list[int]:
            bits = []

            for _ in range(n):
                bits.append(self._pattern[self._index])
                self._index += 1
                self._index %= len(self._pattern)

            if self.enable_scrambler:
                bits = self._scrambler.scramble(bits)
            
            return bits
        
        @property
        def pattern(self) -> list[int]:
            return self._pattern
        
        @pattern.setter
        def pattern(self, pattern: list[int]) -> None:
            self._pattern = pattern
            self._index = 0

    class _PatternBitReceiver(modem.IBitReceiver):
        def __init__(
            self,
            pattern: list[int],
            enable_unscrambler: bool = False
        ) -> None:
            self._unscrambler = V22bisReceiver._Unscrambler()
            self.enable_unscrambler = enable_unscrambler
            self._pattern = pattern
            self._index = 0
            self._count = 0
            self._best = 0

        def receive_bits(self, bits: list[int]) -> None:
            if self.enable_unscrambler:
                bits = self._unscrambler.unscramble(bits)

            for bit in bits:
                if bit == self._pattern[self._index]:
                    self._count += 1
                    self._index += 1
                    self._index %= len(self._pattern)

                    if self._count > self._best:
                        self._best = self._count
                
                else:
                    self._count = 0
                    self._index = 0

        @property
        def count(self) -> int:
            return self._count
        
        @property
        def best(self) -> int:
            return self._best
        
        def reset(self) -> None:
            self._count = 0
            self._best = 0
            self._index = 0
        
    class _HandshakeBitReceiver(modem.IBitReceiver):
        def __init__(self, receivers: list[modem.IBitReceiver]) -> None:
            self._receivers = receivers
        
        def receive_bits(self, bits: list[int]) -> None:
            for receiver in self._receivers:
                receiver.receive_bits(bits)
        
    def __init__(
        self,
        bit_protocol: modem.IBitProtocol,
        role: modem.Role,
        connect_callback: typing.Optional[typing.Callable[[int, int], None]] = None
    ) -> None:
        self._bit_protocol = bit_protocol
        self._connect_callback = connect_callback

        if role == modem.Role.CALLER:
            self._state = V22bis._State.CALLER_WAITING_FOR_2250HZ

        else:
            self._state = V22bis._State.CALLEE_SENDING_UNSCRAMBLED_1

        self._tone_detector = modem.util.goertzel.SlidingGoertzel(
            SAMPLE_RATE_EXTERNAL,
            2250 if role == modem.Role.CALLER else 1050,
            800
        )
        self._timer: float = 0
        self._phase: float = 0
        self._pattern_receiver_0011 = V22bis._PatternBitReceiver([0, 0, 1, 1])
        self._pattern_receiver_1 = V22bis._PatternBitReceiver([1], True)
        self._pattern_provider_0011 = V22bis._PatternBitProvider([0, 0, 1, 1])
        self._pattern_provider_1 = V22bis._PatternBitProvider([1], True)
        self._handshake_bit_receiver = V22bis._HandshakeBitReceiver(
            [
                self._pattern_receiver_0011,
                self._pattern_receiver_1
            ]
        )
        self._receiver = V22bisReceiver(role, self._handshake_bit_receiver)
        self._sender = V22bisSender(role, self._pattern_provider_1)
    
    def receive_samples(self, samples: list[float]):
        if self._timer > 0:
            self._timer -= len(samples) / SAMPLE_RATE_EXTERNAL

        match self._state:
            case V22bis._State.CALLER_WAITING_FOR_2250HZ:
                self._tone_detector.receive_samples(samples)

                if self._tone_detector.get_value() >= TONE_THRESHOLD_UP:
                    print("[V22bis] Detected 2250 Hz tone.")
                    self._timer = 0.155
                    self._change_state(V22bis._State.CALLER_HOLDING_2250HZ)
                
            case V22bis._State.CALLER_HOLDING_2250HZ:
                self._tone_detector.receive_samples(samples)

                if self._tone_detector.get_value() < TONE_THRESHOLD_DOWN:
                    print("[V22bis] Lost 2250 Hz tone.")
                    self._change_state(V22bis._State.CALLER_WAITING_FOR_2250HZ)
                
                else:
                    if self._timer <= 0:
                        print("[V22bis] 2250 Hz tone held for 155ms.")
                        self._change_state(V22bis._State.CALLER_2250HZ_DETECTED)
                        self._timer = 0.456

            case V22bis._State.CALLER_2250HZ_DETECTED:
                if self._timer <= 0:
                    print("[V22bis] Sending 0011.")
                    self._change_state(V22bis._State.CALLER_SENDING_UNSCRAMBLED_0011)
                    self._timer = 0.1

            case V22bis._State.CALLER_SENDING_UNSCRAMBLED_0011:
                if self._timer <= 0:
                    print("[V22bis] Sending scrambled 1 at 1200 bps.")
                    self._change_state(V22bis._State.CALLER_SENDING_SCRAMBLED_1_1200)
            
            case V22bis._State.CALLER_SENDING_SCRAMBLED_1_1200:
                self._receiver.receive_samples(samples)

                if self._pattern_receiver_0011.best >= 32:
                    print("[V22bis] Detected unscrambled 0011.")
                    self._change_state(V22bis._State.CALLER_UNSCRAMBLED_0011_DETECTED)
                    self._timer = 0.45
                
                elif (
                    self._pattern_receiver_1.count >= 0.27 * 1200
                    and self._receiver.get_transition_rate() >= 0.4
                ):
                    print("[V22bis] Detected scrambled 1.")
                    self._change_state(V22bis._State.CALLER_SCRAMBLED_1_DETECTED)
                    self._timer = 0.765

            case V22bis._State.CALLER_UNSCRAMBLED_0011_DETECTED:
                if self._timer <= 0:
                    print("[V22bis] Ready to receive at 2400 bps.")
                    self._change_state(V22bis._State.CALLER_RECEIVE_2400)
                    self._timer = 0.15

            case V22bis._State.CALLER_RECEIVE_2400:
                self._receiver.receive_samples(samples)

                if self._timer <= 0:
                    print("[V22bis] Sending scrambled 1 at 2400 bps.")
                    self._change_state(V22bis._State.CALLER_SENDING_SCRAMBLED_1_2400)
                    self._timer = 0.2

            case V22bis._State.CALLER_SENDING_SCRAMBLED_1_2400:
                self._receiver.receive_samples(samples)

                if self._timer <= 0:
                    print("[V22bis] Waiting for scrambled 1 at 2400 bps.")
                    self._change_state(V22bis._State.CALLER_WAITING_SCRAMBLED_1_2400)
                
            case V22bis._State.CALLER_WAITING_SCRAMBLED_1_2400:
                self._receiver.receive_samples(samples)

                if(
                    self._pattern_receiver_1.count >= 300
                    and self._receiver.get_transition_rate() >= 0.4
                ):
                    print("[V22bis] Switching to data mode.")

                    if self._connect_callback is not None:
                        self._connect_callback(2400, 2400)

                    self._change_state(V22bis._State.DATA)

                else:
                    print("\r[V22bis]", self._pattern_receiver_1.count, self._pattern_receiver_1.best, self._receiver.get_transition_rate(), end="    ")
            
            case V22bis._State.CALLER_SCRAMBLED_1_DETECTED:
                self._receiver.receive_samples(samples)
                
                if self._timer <= 0:
                    print("[V22bis] Switching to data mode.")

                    if self._connect_callback is not None:
                        self._connect_callback(1200, 1200)

                    self._change_state(V22bis._State.DATA)

            case V22bis._State.CALLEE_SENDING_UNSCRAMBLED_1:
                pass
    
    def get_samples(self, n: int) -> list[float]:
        if self._state in (
            V22bis._State.CALLER_SENDING_UNSCRAMBLED_0011,
            V22bis._State.CALLER_SENDING_SCRAMBLED_1_1200,
            V22bis._State.CALLER_UNSCRAMBLED_0011_DETECTED,
            V22bis._State.CALLER_SCRAMBLED_1_DETECTED,
            V22bis._State.CALLER_RECEIVE_2400,
            V22bis._State.CALLER_SENDING_SCRAMBLED_1_2400,
            V22bis._State.CALLER_WAITING_SCRAMBLED_1_2400,
            V22bis._State.DATA
        ):
            return self._sender.get_samples(n)
        
        else:
            return [0] * n
    
    def _change_state(self, state: "V22bis._State") -> None:
        # Default config: data mode at 2400 bps
        self._receiver.bit_receiver = self._bit_protocol
        self._receiver.enable_transition_counter = False
        self._receiver.enable_unscrambler = True
        self._receiver._speed = 2400
        self._sender.bit_provider = self._bit_protocol
        self._sender.enable_scrambler = True
        self._sender._speed = 2400
        self._pattern_provider_0011.enable_scrambler = False
        self._pattern_provider_1.enable_scrambler = False
        self._pattern_receiver_0011.enable_unscrambler = False
        self._pattern_receiver_1.enable_unscrambler = False

        match state:
            case V22bis._State.CALLER_SENDING_UNSCRAMBLED_0011:
                self._sender.bit_provider = self._pattern_provider_0011
                self._sender.enable_scrambler = False
                self._sender._speed = 1200
            
            case V22bis._State.CALLER_SENDING_SCRAMBLED_1_1200:
                self._receiver.bit_receiver = self._handshake_bit_receiver
                self._receiver.enable_transition_counter = True
                self._receiver.enable_unscrambler = False
                self._receiver._speed = 1200
                self._sender.bit_provider = self._pattern_provider_1
                self._sender._speed = 1200
                self._pattern_receiver_1.enable_unscrambler = True
                self._pattern_receiver_0011.reset()
                self._pattern_receiver_1.reset()
            
            case V22bis._State.CALLER_UNSCRAMBLED_0011_DETECTED:
                self._sender.bit_provider = self._pattern_provider_1
                self._sender._speed = 1200

            case V22bis._State.CALLER_RECEIVE_2400:
                self._receiver.bit_receiver = self._handshake_bit_receiver
                self._receiver.enable_transition_counter = True
                self._sender.bit_provider = self._pattern_provider_1
                self._sender._speed = 1200
                self._pattern_receiver_1.reset()

            case V22bis._State.CALLER_SENDING_SCRAMBLED_1_2400:
                self._receiver.bit_receiver = self._handshake_bit_receiver
                self._receiver.enable_transition_counter = True
                self._sender.bit_provider = self._pattern_provider_1

            case V22bis._State.CALLER_WAITING_SCRAMBLED_1_2400:
                self._receiver.bit_receiver = self._handshake_bit_receiver
                self._receiver.enable_transition_counter = True
                self._sender.bit_provider = self._pattern_provider_1

        self._state = state
