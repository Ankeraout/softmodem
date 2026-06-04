import datetime
import modem.analog_protocols.v21
import modem.analog_protocols.v22
import modem.analog_protocols.v8
import modem.bit_protocols.uart
import modem.codec.pcm16
import modem
import pathlib
import threading
import time
import wave

class Modem(modem.IModem):
    def __init__(
        self,
        phone: modem.IPhone,
        record: bool,
        enable_v21: bool,
        enable_v22: bool
    ) -> None:
        super().__init__()
        self._phone = phone
        self._lock = threading.RLock()
        self._call: modem.ICall | None = None
        self._rx_call_thread: threading.Thread | None = None
        self._tx_call_thread: threading.Thread | None = None
        self._record = record
        self._codec = modem.codec.pcm16.PCM16()
        self._enable_v21 = enable_v21
        self._enable_v22 = enable_v22

        if record:
            pathlib.Path("record").mkdir(exist_ok=True)

    def call(self, number: str) -> None:
        with self._lock:
            if self._call is not None:
                raise Exception("Already in a call.")

            self._call = self._phone.call(number)

            self._bit_protocol = modem.bit_protocols.uart.UART(
                self.byte_protocol,
                8,
                modem.bit_protocols.uart.Parity.NONE,
                1
            )

            self._analog_protocol = modem.analog_protocols.v8.V8(
                modem.Role.CALLER,
                modem.analog_protocols.v8.Configuration(
                    v21_enabled=self._enable_v21,
                    v22_enabled=self._enable_v22,
                    v42_enabled=False
                ),
                self._connect_callback_v8
            )

            self._rx_call_thread = threading.Thread(
                target=self._call_rx_thread_main
            )
            self._rx_call_thread.start()

    @property
    def call_state(self):
        with self._lock:
            if self._call is None:
                return modem.CallState.ENDED
            
            else:
                return self._call.get_state()
    
    def hangup(self) -> None:
        with self._lock:
            if self._call is None:
                raise Exception("Not in a call.")
            
            else:
                self._call.hangup()
                self._call = None

    def _connect_callback_v8(
        self,
        configuration: modem.analog_protocols.v8.Configuration
    ) -> None:
        print("[Modem] V.8 configuration finished")
        print(configuration)

        if configuration.v22_enabled:
            self._analog_protocol = modem.analog_protocols.v22.V22(
                self._bit_protocol,
                modem.Role.CALLER,
                self._call_connected
            )

        elif configuration.v21_enabled:
            self._analog_protocol = modem.analog_protocols.v21.V21(
                self._bit_protocol,
                modem.Role.CALLER,
                self._call_connected
            )

        else:
            self.hangup()

    def _call_connected(self, speed_down: int, speed_up: int) -> None:
        self._byte_protocol.receive_bytes(
            "\r\nCONNECT {:d}/{:d}\r\n\r\n".format(speed_down, speed_up)
            .encode()
        )
            
    def _call_rx_thread_main(self) -> None:
        with self._lock:
            call = self._call

        if call is None or call.get_state() == modem.CallState.ENDED:
            return
        
        waiting: bool = True

        print("[analog-rx] Waiting")

        while waiting:
            if call.get_state() in (
                modem.CallState.DIALING,
                modem.CallState.RINGING
            ):
                time.sleep(0.1)
                
            else:
                waiting = False
            
        if call.get_state() == modem.CallState.ENDED:
            print("[analog-rx] Call ended.")
            self._byte_protocol.receive_bytes(b"\r\nNO DIALTONE\r\n\r\n")
            self._call = None
            self._rx_call_thread = None
            return
        
        print("[analog-rx] Call answered.")

        record_file_name = datetime.datetime.now().strftime(
            "record/%Y%m%d%H%M%S"
        )
        self._wave_rx = wave.open(record_file_name + "-rx.wav", "wb")
        self._wave_rx.setframerate(8000)
        self._wave_rx.setnchannels(1)
        self._wave_rx.setsampwidth(2)
        self._wave_tx = wave.open(record_file_name + "-tx.wav", "wb")
        self._wave_tx.setframerate(8000)
        self._wave_tx.setnchannels(1)
        self._wave_tx.setsampwidth(2)

        self._tx_call_thread = threading.Thread(
            target=self._call_tx_thread_main
        )
        self._tx_call_thread.start()
        
        calling = True

        while calling:
            if call.get_state() == modem.CallState.ENDED:
                calling = False

            else:
                samples_rx = self._call.read_audio(160, 0.1)

                if len(samples_rx) == 0:
                    continue

                if self._record:
                    self._wave_rx.writeframes(self._codec.encode(samples_rx))

                with self._lock:
                    if self._analog_protocol is not None:
                        self._analog_protocol.receive_samples(samples_rx)
        
        print("[analog-rx] Call ended.")
        self._rx_call_thread = None
        self._tx_call_thread.join()
        self._tx_call_thread = None

    def _call_tx_thread_main(self) -> None:
        with self._lock:
            call = self._call

        if call is None or call.get_state() == modem.CallState.ENDED:
            print("[analog-tx] Call ended.")
            return
        
        print("[analog-tx] Call answered.")
        
        t: float = time.time()

        while call.get_state() == modem.CallState.ANSWERED:
            # Generate samples
            with self._lock:
                if self._analog_protocol is not None:
                    tx_samples = [
                        s * 0.25 for s in self._analog_protocol.get_samples(160)
                    ]

                else:
                    tx_samples = [0] * 160

            if self._record:
                self._wave_tx.writeframes(self._codec.encode(tx_samples))

            # Wait until send time
            while time.time() < t:
                time.sleep(0.001)

            # Send samples
            call.write_audio(tx_samples)

            # Increase send time
            t += 0.02
        
        print("[analog-tx] Call ended.")
