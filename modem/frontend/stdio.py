import modem
import os
import sys
import termios
import time

class Stdio(modem.IByteReceiver):
    def __init__(self, byte_sender: modem.IByteSender | None = None) -> None:
        self._byte_sender = byte_sender

    def run(self) -> None:
        oldattr = termios.tcgetattr(sys.stdin.fileno())
        newattr = oldattr
        newattr[3] &= ~termios.ICANON
        newattr[3] &= ~termios.ECHO
        newattr[6][termios.VMIN] = 1
        newattr[6][termios.VTIME] = 0
        termios.tcsetattr(sys.stdin, termios.TCSANOW, newattr)

        try:
            while True:
                data = os.read(sys.stdin.fileno(), 1)
                print(data)
                self._byte_sender.send_bytes(data)
                time.sleep(0.25)

        except KeyboardInterrupt:
            pass

        termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, oldattr)

    @property
    def byte_sender(self) -> modem.IByteSender | None:
        return self._byte_sender
    
    @byte_sender.setter
    def byte_sender(self, byte_sender: modem.IByteSender | None) -> None:
        self._byte_sender = byte_sender

    def receive_bytes(self, data: bytes) -> None:
        os.write(sys.stdout.fileno(), data)
