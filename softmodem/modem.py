import softmodem
import softmodem.protocol.bit.uart
import softmodem.protocol.byte.v250
import threading
import time

class Modem(softmodem.IModem, softmodem.IByteSender):
    def __init__(
        self,
        phone: softmodem.IPhone,
        byte_receiver: softmodem.IByteReceiver
    ) -> None:
        self._phone = phone
        self._lock = threading.RLock()
        self._call: softmodem.ICall | None = None
        self._byte_receiver: softmodem.IByteReceiver = byte_receiver
        self._v250 = softmodem.protocol.byte.v250.V250(phone, self)
        self._v250.byte_receiver = byte_receiver
        self._data_session = softmodem.DataSession(
            bit_protocol=softmodem.protocol.bit.uart.UART(self._v250)
        )
        self._call_thread: threading.Thread | None = None
    
    @property
    def state(self):
        with self._lock:
            if self._call is None:
                return softmodem.ModemState.IDLE
            
            match self._call.state:
                case softmodem.CallState.DIALING:
                    return softmodem.ModemState.DIALING
                
                case softmodem.CallState.RINGING:
                    if self._call.direction == softmodem.CallDirection.INCOMING:
                        return softmodem.ModemState.RINGING
                    
                    else:
                        return softmodem.ModemState.DIALING
                    
                case softmodem.CallState.CONNECTED:
                    return softmodem.ModemState.CONNECTED
                
                case softmodem.CallState.ENDED:
                    return softmodem.ModemState.IDLE
                
    @property
    def data_session(self) -> softmodem.DataSession:
        return self._data_session
                
    def send_bytes(self, data: bytes) -> None:
        self._v250.send_bytes(data)

    def call(self, number: str) -> None:
        with self._lock:
            if self.state != softmodem.ModemState.IDLE:
                raise Exception("There is already an active call.")
            
            print("[Modem] Calling {:s}...".format(number))
            
            self._call = self._phone.call(number)
            self._call_thread = threading.Thread(
                target=self._call_thread_main,
                name="Call thread",
                daemon=True
            )
            self._call_thread.start()

    def hangup(self) -> None:
        with self._lock:
            if self._call is not None:
                if self._call.state != softmodem.CallState.ENDED:
                    self._call.hangup()

            self._call = None

    def _call_thread_main(self) -> None:
        with self._lock:
            if self._call is None:
                return
            
            call = self._call

        # Wait for the call to connect
        while True:
            if call.state == softmodem.CallState.ENDED:
                # Call did not connect
                self._call = None
                print("[Modem] Call did not connect.")
                return
            
            elif call.state == softmodem.CallState.CONNECTED:
                # Call connected
                print("[Modem] Call connected.")
                break
            
            time.sleep(0.1)
        
        # Call connected
        threading.Thread(
            name="Call RX thread",
            target=self._call_rx_main,
            daemon=True
        ).start()

        self._data_session.start_time = time.monotonic() - 0.2
        self._data_session.samples_sent = 0

        while call.state == softmodem.CallState.CONNECTED:
            current_time = time.monotonic()
            elapsed_time = current_time - self._data_session.start_time
            samples_to_send = elapsed_time * 8000

            if samples_to_send - self._data_session.samples_sent >= 160:
                samples = self._data_session.analog_protocol.get_samples(160)
                call.write_samples(samples)
                self._data_session.samples_sent += 160
            
            time.sleep(0.001)

        print("[TX thread] Call ended.")

    def _call_rx_main(self) -> None:
        with self._lock:
            if self._call is None:
                return
            
            call = self._call
                
        while call.state == softmodem.CallState.CONNECTED:
            samples = call.read_samples(1)
            self._data_session.analog_protocol.receive_samples(samples)

        print("[RX thread] Call ended.")
