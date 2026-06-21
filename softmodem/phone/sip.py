import softmodem.codec.pcm8u
import random
import softmodem.sip
import time
import typing

class SIPCall(softmodem.ICall):
    def __init__(
        self,
        call: softmodem.sip.SIPCall,
        direction: softmodem.CallDirection
    ) -> None:
        self._call = call
        self._codec = softmodem.codec.pcm8u.PCM8U()
        self._direction = direction

    @property
    def state(self) -> softmodem.CallState:
        match self._call.state:
            case softmodem.sip.SIPCallState.DIALING:
                return softmodem.CallState.DIALING
            
            case softmodem.sip.SIPCallState.RINGING:
                return softmodem.CallState.RINGING
            
            case softmodem.sip.SIPCallState.CONNECTED:
                return softmodem.CallState.CONNECTED
            
            case _:
                return softmodem.CallState.ENDED

    @property
    def direction(self):
        return self._direction
    
    def accept(self) -> None:
        pass

    def decline(self) -> None:
        pass

    def hangup(self) -> None:
        self._call.hangup()

    def read_samples(
        self,
        n: int,
        timeout: typing.Optional[float] = None
    ) -> list[float]:
        return self._codec.decode(self._call.read_audio(n, timeout))

    def write_samples(self, data: list[float]) -> None:
        self._call.write_audio(self._codec.encode(data))

class SIPPhone(softmodem.IPhone):
    def __init__(
        self,
        username: str,
        password: str,
        host: str,
        port: int = 5060
    ) -> None:
        super().__init__()
        self._client = softmodem.sip.SIPClient(
            username,
            password,
            host,
            server_port=port,
            rtp_port_start=random.randint(10000, 18000) & ~1
        )
        self._client.start()

        while self._client.state in (
            softmodem.sip.SIPClientState.STARTING,
            softmodem.sip.SIPClientState.REGISTERING
        ):
            time.sleep(0.1)

        if self._client.state != softmodem.sip.SIPClientState.REGISTERED:
            raise Exception("Failed to register.")
    
    def call(self, number: str) -> SIPCall:
        return SIPCall(
            self._client.dial(number),
            softmodem.CallDirection.OUTGOING
        )
