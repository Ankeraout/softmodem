import abc
import enum
import typing

VERSION = "0.1.0"
T = typing.TypeVar("T")

class Role(enum.Enum):
    CALLER = 0
    CALLEE = 1

class DataDirection(enum.Enum):
    RX = 0
    TX = 1

class IByteSender(abc.ABC):
    @abc.abstractmethod
    def send_bytes(self, data: bytes) -> None:
        pass

class IByteReceiver(abc.ABC):
    @abc.abstractmethod
    def receive_bytes(self, data: bytes) -> None:
        pass

class IByteProtocol(IByteReceiver, IByteSender):
    pass

class IBitSender(abc.ABC):
    @abc.abstractmethod
    def send_bits(self, bits: list[int]) -> None:
        pass

class IBitProvider(abc.ABC):
    @abc.abstractmethod
    def get_bits(self, n: int) -> list[int]:
        pass

class IBitReceiver(abc.ABC):
    @abc.abstractmethod
    def receive_bits(self, bits: list[int]) -> None:
        pass

class IBitProtocol(IBitProvider, IBitReceiver, IByteSender):
    pass

class IAnalogProvider(abc.ABC):
    @abc.abstractmethod
    def get_samples(self, n: int) -> list[float]:
        pass

class IAnalogReceiver(abc.ABC):
    @abc.abstractmethod
    def receive_samples(self, samples: list[float]) -> None:
        pass

class IAnalogProtocol(IAnalogProvider, IAnalogReceiver):
    pass

class ICodec(abc.ABC, typing.Generic[T]):
    @abc.abstractmethod
    def decode(self, data: T) -> list[float]:
        pass

    @abc.abstractmethod
    def encode(self, samples: list[float]) -> T:
        pass

class CallState(enum.Enum):
    DIALING = 0
    RINGING = 1
    ANSWERED = 2
    ENDED = 3

class ICall(abc.ABC):
    @abc.abstractmethod
    def read_audio(
        self,
        n: int,
        timeout: typing.Optional[float] = None
    ) -> list[float]:
        pass

    @abc.abstractmethod
    def write_audio(self, data: list[float]) -> None:
        pass

    @abc.abstractmethod
    def hangup(self) -> None:
        pass

    @abc.abstractmethod
    def get_state(self) -> CallState:
        pass

class IPhone(abc.ABC):
    @abc.abstractmethod
    def call(self, number: str) -> ICall:
        pass

class IModem(abc.ABC):
    def __init__(self) -> None:
        self._analog_protocol: IAnalogProtocol | None = None
        self._bit_protocol: IBitProtocol | None = None
        self._byte_protocol: IByteProtocol | None = None

    @property
    def analog_protocol(self) -> IAnalogProtocol | None:
        return self._analog_protocol
    
    @analog_protocol.setter
    def analog_protocol(self, value: IAnalogProtocol | None) -> None:
        self._analog_protocol = value

    @property
    def bit_protocol(self) -> IBitProtocol | None:
        return self._bit_protocol
    
    @bit_protocol.setter
    def bit_protocol(self, value: IBitProtocol | None) -> None:
        self._bit_protocol = value

    @property
    def byte_protocol(self) -> IByteProtocol | None:
        return self._byte_protocol
    
    @byte_protocol.setter
    def byte_protocol(self, value: IByteProtocol | None) -> None:
        self._byte_protocol = value

    @abc.abstractmethod
    def call(self, number: str) -> None:
        pass

    @abc.abstractmethod
    def hangup(self) -> None:
        pass

    @property
    @abc.abstractmethod
    def call_state(self) -> CallState:
        pass
