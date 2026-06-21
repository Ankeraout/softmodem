import dataclasses
import enum
import math
import softmodem.protocol.analog.v21
import softmodem.protocol.bit.uart
import softmodem.util.byte_receiver
import softmodem.util.goertzel
import softmodem.util.tone
import typing

@dataclasses.dataclass
class Configuration:
    v21_enabled: bool = False
    v22_enabled: bool = False
    v42_enabled: bool = False

    def __and__(self, other: "Configuration") -> "Configuration":
        return Configuration(
            self.v21_enabled & other.v21_enabled,
            self.v22_enabled & other.v22_enabled
        )

class V8(softmodem.IAnalogProtocol):
    _SAMPLE_RATE = 8000
    _ANS_FREQUENCY = 2100
    _CI_MESSAGE_BYTES = b"\x00\xc1"
    _CJ_MESSAGE_BYTES = b"\x00\x00\x00"
    _ANS_THRESHOLD = 0.033

    class _State(enum.Enum):
        CALLER_INITIAL_DELAY = enum.auto()
        CALLER_SENDING_CI = enum.auto()
        CALLER_DELAY_CM = enum.auto()
        CALLER_SENDING_CM = enum.auto()
        CALLEE_INITIAL_DELAY = enum.auto()
        CALLEE_SENDING_ANS = enum.auto()
        CALLEE_SENDING_JM = enum.auto()
        FINISHING = enum.auto()
        DONE = enum.auto()

    def __init__(
        self,
        call_direction: softmodem.CallDirection,
        configuration: Configuration,
        connect_callback: typing.Callable[[Configuration], None] | None = None
    ) -> None:
        self._internal_config = configuration
        self._connect_callback = connect_callback
        self._byte_receiver = softmodem.util.byte_receiver.BufferByteReceiver()
        self._bit_protocol = softmodem.protocol.bit.uart.UART(
            self._byte_receiver
        )
        self._v21 = softmodem.protocol.analog.v21.V21(
            self._bit_protocol,
            call_direction
        )
        self._state: V8._State = (
            V8._State.CALLER_INITIAL_DELAY
            if call_direction == softmodem.CallDirection.OUTGOING
            else V8._State.CALLEE_INITIAL_DELAY
        )
        self._ans_detector = softmodem.util.goertzel.SlidingGoertzel(
            V8._SAMPLE_RATE,
            V8._ANS_FREQUENCY,
            V8._SAMPLE_RATE // 2
        )
        self._v21_delay = 0
        self._delay = (
            1 if call_direction == softmodem.CallDirection.OUTGOING else 0.2
        )
        self._ans_generator = softmodem.util.tone.ToneGenerator(
            V8._SAMPLE_RATE,
            V8._ANS_FREQUENCY
        )
        self._config_message = V8._configuration_to_message(configuration)
        self._config: Configuration | None = None

    def receive_samples(self, samples: list[float]) -> None:
        match self._state:
            case V8._State.CALLER_SENDING_CI:
                self._ans_detector.receive_samples(samples)
                
                if self._ans_detector.get_value() >= V8._ANS_THRESHOLD:
                    print("[V8] Caller detected ANS")
                    self._state = V8._State.CALLER_DELAY_CM
                    self._delay = 0.5
            
            case V8._State.CALLER_SENDING_CM:
                self._v21.receive_samples(samples)

                if self._byte_receiver.buffer.count(b"\xe0") == 4:
                    indices = []

                    for index, byte in enumerate(self._byte_receiver.buffer):
                        if byte == 0xe0:
                            indices.append(index)
                    
                    sizes = [
                        indices[i + 1] - indices[i]
                        for i in range(len(indices) - 1)
                    ]

                    if sizes[0] == sizes[1] and sizes[1] == sizes[2]:
                        size = sizes[0]
                        messages = [
                            self._byte_receiver.buffer[
                                indices[i]:indices[i] + size
                            ] for i in range(3)
                        ]

                        if (
                            messages[0] == messages[1]
                            and messages[1] == messages[2]
                        ):
                            print("[V8] Caller detected JM")
                            self._state = V8._State.FINISHING
                            self._config = (
                                self._internal_config
                                & V8._message_to_configuration(messages[0])
                            )
                            self._send_bytes(V8._CJ_MESSAGE_BYTES)
                            self._v21_delay += 10 * 8000 / 300

                    else:
                        del self._byte_receiver.buffer[:indices[1]]

            case V8._State.CALLEE_SENDING_ANS:
                self._v21.receive_samples(samples)

                if self._byte_receiver.buffer.count(b"\xe0") == 4:
                    indices = []

                    for index, byte in enumerate(self._byte_receiver.buffer):
                        if byte == 0xe0:
                            indices.append(index)
                    
                    sizes = [
                        indices[i + 1] - indices[i]
                        for i in range(len(indices) - 1)
                    ]

                    if sizes[0] == sizes[1] and sizes[1] == sizes[2]:
                        size = sizes[0]
                        messages = [
                            self._byte_receiver.buffer[
                                indices[i]:indices[i] + size
                            ] for i in range(3)
                        ]

                        if (
                            messages[0] == messages[1]
                            and messages[1] == messages[2]
                        ):
                            print("[V8] Callee detected CM")
                            self._state = V8._State.CALLEE_SENDING_JM
                            self._config = (
                                self._internal_config
                                & V8._message_to_configuration(messages[0])
                            )
                            self._config_message = V8._configuration_to_message(
                                self._config
                            )
                            self._byte_receiver.buffer.clear()

                    else:
                        del self._byte_receiver.buffer[:indices[1]]

            case V8._State.CALLEE_SENDING_JM:
                self._v21.receive_samples(samples)

                if V8._CJ_MESSAGE_BYTES in self._byte_receiver.buffer:
                    print("[V8] Callee detected CJ")
                    self._state = V8._State.FINISHING
                    self._v21_delay += 10 * 8000 / 300

    def get_samples(self, n: int) -> list[float]:
        match self._state:
            case V8._State.CALLER_INITIAL_DELAY:
                self._delay -= n / V8._SAMPLE_RATE

                if self._delay <= 0:
                    print("[V8] Caller sending CI")
                    self._state = V8._State.CALLER_SENDING_CI

                samples = [0] * n

            case V8._State.CALLER_SENDING_CI:
                while self._v21_delay <= n:
                    self._send_bits([1] * 10)
                    self._send_bytes(V8._CI_MESSAGE_BYTES)

                self._v21_delay -= n

                samples = self._v21.get_samples(n)

            case V8._State.CALLER_DELAY_CM:
                if self._v21_delay > 0:
                    self._v21_delay = max(self._v21_delay - n, 0)
                
                else:
                    self._delay -= n / V8._SAMPLE_RATE

                    if self._delay <= 0:
                        print("[V8] Caller sending CM")
                        self._state = V8._State.CALLER_SENDING_CM

                samples = [0] * n

            case V8._State.CALLER_SENDING_CM:
                while self._v21_delay <= n:
                    self._send_bits([1] * 10)
                    self._send_bytes(self._config_message)

                self._v21_delay -= n

                samples = self._v21.get_samples(n)

            case V8._State.CALLEE_INITIAL_DELAY:
                self._delay -= n / V8._SAMPLE_RATE

                if self._delay <= 0:
                    print("[V8] Callee sending ANS")
                    self._state = V8._State.CALLEE_SENDING_ANS
                    self._delay = 0.450

                samples = [0] * n

            case V8._State.CALLEE_SENDING_ANS:
                if self._delay <= 0:
                    self._ans_generator.phase_shift(math.pi)
                    self._delay = 0.450
                
                self._delay -= n / V8._SAMPLE_RATE

                samples = self._ans_generator.get_samples(n)

            case V8._State.CALLEE_SENDING_JM:
                while self._v21_delay <= n:
                    self._send_bits([1] * 10)
                    self._send_bytes(self._config_message)

                self._v21_delay -= n

                samples = self._v21.get_samples(n)

            case V8._State.FINISHING:
                self._v21_delay -= n

                if self._v21_delay <= 0:
                    self._state = V8._State.DONE

                    if self._connect_callback is not None:
                        self._connect_callback(self._config)

                samples = self._v21.get_samples(n)

            case V8._State.DONE:
                samples = [0] * n

        return samples

    @staticmethod
    def _configuration_to_message(configuration: Configuration) -> bytes:
        modn1 = 0x10
        modn2 = 0x10

        if configuration.v21_enabled:
            modn2 |= 0x80
        
        if configuration.v22_enabled:
            modn1 |= 0x02
        
        message_bytes = [0xe0, 0xc1, 0x05, modn1, modn2, 0x0d]

        if configuration.v42_enabled:
            message_bytes.append(0x2a)

        return bytes(message_bytes)
    
    @staticmethod
    def _message_to_configuration(message: bytes) -> Configuration:
        configuration = Configuration()
        modulation_found = False
        
        for index, byte in enumerate(message):
            if byte & 0x1f == 0x05:
                modulation_start_index = index
                modulation_found = True
                break

        if not modulation_found:
            return configuration
        
        modn1 = message[modulation_start_index + 1]
        modn2 = message[modulation_start_index + 2]

        configuration.v22_enabled = (modn1 & 0x02) != 0
        configuration.v21_enabled = (modn2 & 0x80) != 0
        configuration.v42_enabled = b"\x2a" in message

        return configuration
    
    def _send_bits(self, bits: list[int]) -> None:
        self._v21_delay += len(bits) * 8000 / 300
        self._bit_protocol.send_bits(bits)

    def _send_bytes(self, message: bytes) -> None:
        self._v21_delay += len(message) * 10 * 8000 / 300
        self._bit_protocol.send_bytes(message)
