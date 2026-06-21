import datetime
import softmodem
import softmodem.codec.pcm16
import softmodem.protocol.analog.bell103
import softmodem.protocol.bit.uart
import softmodem.protocol.byte.v250
import threading
import time
import wave

class Modem(softmodem.IModem, softmodem.IByteSender):
    def __init__(
        self,
        phone: softmodem.IPhone,
        byte_receiver: softmodem.IByteReceiver,
        record: bool,
        enable_v21: bool,
        enable_v22: bool
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
        self._wave_rx: wave.Wave_write | None = None
        self._wave_tx: wave.Wave_write | None = None
        self._record_codec: softmodem.ICodec = softmodem.codec.pcm16.PCM16()
        self._record = record
        self._enable_v21 = enable_v21
        self._enable_v22 = enable_v22
    
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

            if self._record:
                record_file_name = datetime.datetime.now().strftime(
                    "record/%Y%m%d%H%M%S_"
                )
                self._wave_rx = wave.open(record_file_name + "_rx.wav", "wb")
                self._wave_rx.setframerate(8000)
                self._wave_rx.setnchannels(1)
                self._wave_rx.setsampwidth(2)
                self._wave_tx = wave.open(record_file_name + "_tx.wav", "wb")
                self._wave_tx.setframerate(8000)
                self._wave_tx.setnchannels(1)
                self._wave_tx.setsampwidth(2)
            
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

        self._data_session.analog_protocol = (
            softmodem.protocol.analog.bell103.Bell103(
                self._data_session.bit_protocol,
                call.direction,
                self._connect_callback
            )
        )
        
        # Call connected
        threading.Thread(
            name="Call RX thread",
            target=self._call_rx_main,
            daemon=True
        ).start()

        self._data_session.start_time = time.monotonic() - 0.02
        self._data_session.samples_sent = 0

        while call.state == softmodem.CallState.CONNECTED:
            current_time = time.monotonic()
            elapsed_time = current_time - self._data_session.start_time
            samples_to_send = elapsed_time * 8000

            if samples_to_send - self._data_session.samples_sent >= 160:
                samples = self._data_session.analog_protocol.get_samples(160)
                samples = [s * 0.5 for s in samples]
                call.write_samples(samples)

                if self._record:
                    self._wave_tx.writeframes(
                        self._record_codec.encode(samples)
                    )

                self._data_session.samples_sent += 160
            
            time.sleep(0.01)

        print("[TX thread] Call ended.")

    def _call_rx_main(self) -> None:
        with self._lock:
            if self._call is None:
                return
            
            call = self._call
                
        while call.state == softmodem.CallState.CONNECTED:
            samples = call.read_samples(160, 0.02)

            if len(samples) > 0:
                if self._record:
                    self._wave_rx.writeframes(
                        self._record_codec.encode(samples)
                    )
                
                self._data_session.analog_protocol.receive_samples(samples)

        print("[RX thread] Call ended.")

    def _connect_callback(self, downlink_speed: int, uplink_speed: int) -> None:
        self._byte_receiver.receive_bytes(
            "CONNECT {:d}/{:d}\r\n".format(
                downlink_speed,
                uplink_speed
            ).encode()
        )
        self._data_session.download_speed = downlink_speed
        self._data_session.upload_speed = uplink_speed
