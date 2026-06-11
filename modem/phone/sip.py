import modem
import modem.codec.pcm8u
import random
import sip.client
import time
import typing

class SIPCall(modem.ICall):
    def __init__(self, call: sip.client.SIPCall) -> None:
        self._call = call
        self._codec = modem.codec.pcm8u.PCM8U()

    def read_audio(
        self,
        n: int,
        timeout: typing.Optional[float] = None
    ) -> list[float]:
        return self._codec.decode(self._call.read_audio(n, timeout))

    def write_audio(self, data: list[float]) -> None:
        self._call.write_audio(self._codec.encode(data))

    def hangup(self) -> None:
        self._call.hangup()

    def get_state(self) -> modem.CallState:
        match self._call.state:
            case sip.client.SIPCallState.DIALING:
                return modem.CallState.DIALING
            
            case sip.client.SIPCallState.RINGING:
                return modem.CallState.RINGING
            
            case sip.client.SIPCallState.CONNECTED:
                return modem.CallState.ANSWERED
            
            case _:
                return modem.CallState.ENDED

class SIPPhone(modem.IPhone):
    def __init__(
        self,
        username: str,
        password: str,
        host: str,
        port: int = 5060
    ) -> None:
        super().__init__()
        self._client = sip.client.SIPClient(
            username,
            password,
            host,
            server_port=port,
            rtp_port_start=random.randint(10000, 18000) & ~1
        )
        self._client.start()

        while self._client.state in (
            sip.client.SIPClientState.STARTING,
            sip.client.SIPClientState.REGISTERING
        ):
            time.sleep(0.1)

        if self._client.state != sip.client.SIPClientState.REGISTERED:
            raise Exception("Failed to register.")
    
    def call(self, number: str) -> SIPCall:
        return SIPCall(self._client.dial(number))
