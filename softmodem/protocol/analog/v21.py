import softmodem.protocol.analog.fsk
import typing

SAMPLES_PER_SECOND = 8000
SYMBOLS_PER_SECOND = 300
SYMBOL_FREQUENCIES = {
    softmodem.DataDirection.RX: {
        softmodem.CallDirection.OUTGOING: [1850, 1650],
        softmodem.CallDirection.INCOMING: [1180, 980]
    },
    softmodem.DataDirection.TX: {
        softmodem.CallDirection.OUTGOING: [1180, 980],
        softmodem.CallDirection.INCOMING: [1850, 1650]
    }
}

class V21Receiver(softmodem.protocol.analog.fsk.FSKReceiver):
    def __init__(
        self,
        bit_receiver: softmodem.IBitReceiver,
        call_direction: softmodem.CallDirection
    ) -> None:
        super().__init__(
            bit_receiver,
            SYMBOL_FREQUENCIES[softmodem.DataDirection.RX][call_direction][0],
            SYMBOL_FREQUENCIES[softmodem.DataDirection.RX][call_direction][1],
            SAMPLES_PER_SECOND,
            SYMBOLS_PER_SECOND
        )

class V21Sender(softmodem.protocol.analog.fsk.FSKSender):
    def __init__(
        self,
        bit_provider: softmodem.IBitProvider,
        call_direction: softmodem.CallDirection
    ) -> None:
        super().__init__(
            bit_provider,
            SYMBOL_FREQUENCIES[softmodem.DataDirection.TX][call_direction][0],
            SYMBOL_FREQUENCIES[softmodem.DataDirection.TX][call_direction][1],
            SAMPLES_PER_SECOND,
            SYMBOLS_PER_SECOND
        )

class V21(softmodem.IAnalogProtocol):
    def __init__(
        self,
        bit_protocol: softmodem.IBitProtocol,
        call_direction: softmodem.CallDirection,
        connect_callback: typing.Callable[[int, int], None] | None = None
    ) -> None:
        self._analog_receiver = V21Receiver(bit_protocol, call_direction)
        self._analog_sender = V21Sender(bit_protocol, call_direction)
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
