import modem.analog_protocols.fsk
import typing

SAMPLES_PER_SECOND = 8000
SYMBOLS_PER_SECOND = 300
SYMBOL_FREQUENCIES = {
    modem.DataDirection.RX: {
        modem.Role.CALLER: [2025, 2225],
        modem.Role.CALLEE: [1070, 1270],
    },
    modem.DataDirection.TX: {
        modem.Role.CALLER: [1070, 1270],
        modem.Role.CALLEE: [2025, 2225]
    }
}

class Bell103Receiver(modem.analog_protocols.fsk.FSKReceiver):
    def __init__(self, bit_receiver: modem.IBitReceiver, role: modem.Role) -> None:
        super().__init__(
            bit_receiver,
            SYMBOL_FREQUENCIES[modem.DataDirection.RX][role][0],
            SYMBOL_FREQUENCIES[modem.DataDirection.RX][role][1],
            SAMPLES_PER_SECOND,
            SYMBOLS_PER_SECOND
        )

class Bell103Sender(modem.analog_protocols.fsk.FSKSender):
    def __init__(self, bit_provider: modem.IBitProvider, role: modem.Role) -> None:
        super().__init__(
            bit_provider,
            SYMBOL_FREQUENCIES[modem.DataDirection.TX][role][0],
            SYMBOL_FREQUENCIES[modem.DataDirection.TX][role][1],
            SAMPLES_PER_SECOND,
            SYMBOLS_PER_SECOND
        )

class Bell103(modem.IAnalogProtocol):
    def __init__(
        self,
        bit_protocol: modem.IBitProtocol,
        role: modem.Role,
        connect_callback: typing.Callable[[int, int], None] | None = None
    ) -> None:
        self._analog_receiver = Bell103Receiver(bit_protocol, role)
        self._analog_sender = Bell103Sender(bit_protocol, role)
        self._modem = modem
        self._connect_sent = False
        self._connect_callback = connect_callback

    def receive_samples(self, samples: list[float]) -> None:
        if not self._connect_sent:
            if self._connect_callback is not None:
                self._connect_callback(300, 300)

            self._connect_sent = True

        self._analog_receiver.receive_samples(samples)
    
    def get_samples(self, n: int) -> list[float]:
        return self._analog_sender.get_samples(n)
