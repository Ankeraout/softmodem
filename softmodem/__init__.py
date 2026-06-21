import abc
import dataclasses
import enum

class IAnalogProvider(abc.ABC):
    @abc.abstractmethod
    def get_samples(self, n: int) -> list[float]:
        pass

class IAnalogReceiver(abc.ABC):
    @abc.abstractmethod
    def receive_samples(self, samples: list[float]) -> None:
        pass

class IAnalogProtocol(IAnalogReceiver, IAnalogProvider):
    pass

class IBitProvider(abc.ABC):
    @abc.abstractmethod
    def get_bits(self, n: int) -> list[int]:
        pass

class IBitReceiver(abc.ABC):
    @abc.abstractmethod
    def receive_bits(self, bits: list[int]) -> None:
        pass

class IBitSender(abc.ABC):
    @abc.abstractmethod
    def send_bits(self, bits: list[int]) -> None:
        pass

class IBitProtocol(IBitProvider, IBitReceiver):
    pass

class IByteReceiver(abc.ABC):
    @abc.abstractmethod
    def receive_bytes(self, data: bytes) -> None:
        pass

class IByteSender(abc.ABC):
    @abc.abstractmethod
    def send_bytes(self, data: bytes) -> None:
        pass

class IByteProtocol(IByteReceiver, IByteSender):
    pass

class CallState(enum.Enum):
    DIALING = enum.auto()
    RINGING = enum.auto()
    CONNECTED = enum.auto()
    ENDED = enum.auto()

class CallDirection(enum.Enum):
    INCOMING = enum.auto()
    OUTGOING = enum.auto()

class ICall(abc.ABC):
    @property
    @abc.abstractmethod
    def state(self) -> CallState:
        pass

    @property
    @abc.abstractmethod
    def direction(self) -> CallDirection:
        pass

    @abc.abstractmethod
    def accept(self) -> None:
        pass

    @abc.abstractmethod
    def decline(self) -> None:
        pass

    @abc.abstractmethod
    def hangup(self) -> None:
        pass

    @abc.abstractmethod
    def read_samples(self, timeout: float | None = None) -> list[float]:
        pass

    @abc.abstractmethod
    def write_samples(self, samples: list[float]) -> None:
        pass

class IPhone(abc.ABC):
    @abc.abstractmethod
    def call(self, number: str) -> ICall:
        pass

class ModemState(enum.Enum):
    IDLE = enum.auto()
    DIALING = enum.auto()
    RINGING = enum.auto()
    CONNECTED = enum.auto()

class ICodec(abc.ABC):
    @abc.abstractmethod
    def encode(self, samples: list[float]) -> bytes:
        pass

    @abc.abstractmethod
    def decode(self, data: bytes) -> list[float]:
        pass

@dataclasses.dataclass
class DataSession:
    start_time: float | None = None
    download_speed: int | None = None
    upload_speed: int | None = None
    analog_protocol: IAnalogProtocol | None = None
    bit_protocol: IBitProtocol | None = None
    samples_sent: int = 0

class IModem(abc.ABC):
    @property
    @abc.abstractmethod
    def state(self) -> ModemState:
        pass

    @property
    @abc.abstractmethod
    def data_session(self) -> DataSession:
        pass

    @abc.abstractmethod
    def call(self, number: str) -> None:
        pass

    @abc.abstractmethod
    def hangup(self) -> None:
        pass
