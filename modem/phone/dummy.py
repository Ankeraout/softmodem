import modem

class DummyCall(modem.ICall):
    def __init__(self) -> None:
        self._state = modem.CallState.ANSWERED

    def read_audio(self, n: int) -> list[float]:
        return [0] * n

    def write_audio(self, data: list[float]) -> None:
        pass

    def hangup(self) -> None:
        print("DummyCall: hanging up")
        self._state = modem.CallState.ENDED

    def get_state(self) -> modem.CallState:
        return self._state

class DummyPhone(modem.IPhone):
    def call(self, number: str) -> modem.ICall:
        print("DummyPhone: calling {:s}".format(number))
        return DummyCall()
