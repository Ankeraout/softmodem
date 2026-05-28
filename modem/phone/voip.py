import modem
import modem.codec.pcm8
import pyVoIP.VoIP

class VoIPCall(modem.ICall):
    def __init__(self, call: pyVoIP.VoIP.VoIPCall) -> None:
        self._codec = modem.codec.pcm8.PCM8()
        self._call = call

    def read_audio(self, n: int) -> list[float]:
        return self._codec.decode(self._call.read_audio(n))

    def write_audio(self, data: list[float]) -> None:
        self._call.write_audio(self._codec.encode(data))

    def hangup(self) -> None:
        self._call.hangup()

    def get_state(self) -> modem.CallState:
        match self._call.state:
            case pyVoIP.VoIP.CallState.DIALING:
                return modem.CallState.DIALING
            
            case pyVoIP.VoIP.CallState.RINGING:
                return modem.CallState.RINGING
            
            case pyVoIP.VoIP.CallState.ANSWERED:
                return modem.CallState.ANSWERED
            
            case pyVoIP.VoIP.CallState.ENDED:
                return modem.CallState.ENDED

class VoIPPhone(modem.IPhone):
    def __init__(self, server: str, port: int, username: str, password: str) -> None:
        self._phone = pyVoIP.VoIP.VoIPPhone(server, port, username, password)
        self._phone.start()

    def call(self, number: str) -> modem.ICall:
        return VoIPCall(self._phone.call(number))
