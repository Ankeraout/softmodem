import enum
import modem

# TODO: implement parity

class Parity(enum.Enum):
    NONE = 0
    # EVEN = 1
    # ODD = 2

class UARTSender(modem.IBitProvider, modem.IByteSender):
    def __init__(self, data_bits: int, parity: Parity, stop_bits: int) -> None:
        if data_bits < 5 or data_bits > 8:
            raise ValueError("Invalid data bits value.")
        
        if stop_bits not in (1, 2):
            raise ValueError("Invalid stop bits value.")

        self._tx_buffer = []
        self._data_bits = data_bits
        self._parity = parity
        self._stop_bits = stop_bits

    def get_bits(self, n: int) -> list[int]:
        if len(self._tx_buffer) <= n:
            return_value = self._tx_buffer
            return_value += [1] * (n - len(return_value))
            self._tx_buffer = []

        else:
            return_value = self._tx_buffer[:n]
            self._tx_buffer = self._tx_buffer[n:]
        
        return return_value
    
    def send_bits(self, bits: list[int]) -> None:
        self._tx_buffer.extend(bits)

    def send_bytes(self, data: bytes) -> None:
        for byte in data:
            self._tx_buffer.append(0) # Start bit

            for bit in range(self._data_bits):
                self._tx_buffer.append(1 if byte & (1 << bit) != 0 else 0)

            for bit in range(self._stop_bits):
                self._tx_buffer.append(1)

class UARTReceiver(modem.IBitReceiver):
    def __init__(self, byte_receiver: modem.IByteReceiver, data_bits: int, parity: Parity, stop_bits: int):
        if data_bits < 5 or data_bits > 8:
            raise ValueError("Invalid data bits value.")
        
        if stop_bits not in (1, 2):
            raise ValueError("Invalid stop bits value.")

        self._rx_buffer = []
        self._data_bits = data_bits
        self._parity = parity
        self._stop_bits = stop_bits
        self._byte_receiver = byte_receiver
    
    def receive_bits(self, bits: list[int]) -> None:
        rx_buffer = bytearray()

        for bit in bits:
            if len(self._rx_buffer) != 0 or bit == 0:
                self._rx_buffer.append(bit)
            
            if len(self._rx_buffer) == self._data_bits + self._stop_bits + 1:
                if self._rx_buffer[self._data_bits + 1] != 1:
                    self._skip_until_next_start_bit()
                
                elif self._stop_bits == 2 and self._rx_buffer[self._data_bits + 2] != 1:
                    self._skip_until_next_start_bit()
                
                else:
                    byte = 0

                    for shift, bit in enumerate(self._rx_buffer[1:self._data_bits + 1]):
                        byte |= bit * (1 << shift)
                    
                    rx_buffer.append(byte)

                    self._rx_buffer.clear()
        
        if len(rx_buffer) != 0:
            self._byte_receiver.receive_bytes(bytes(rx_buffer))

    def _skip_until_next_start_bit(self) -> None:
        bits_to_skip = 1

        while bits_to_skip < len(self._rx_buffer) and self._rx_buffer[bits_to_skip] == 1:
            bits_to_skip += 1
        
        self._rx_buffer = self._rx_buffer[bits_to_skip:]

class UART(modem.IBitProtocol):
    def __init__(
        self,
        byte_receiver: modem.IByteReceiver,
        data_bits: int,
        parity: Parity,
        stop_bits: int
    ) -> None:
        self._receiver = UARTReceiver(
            byte_receiver,
            data_bits,
            parity,
            stop_bits
        )
        self._sender = UARTSender(data_bits, parity, stop_bits)

    def send_bits(self, bits: list[int]) -> None:
        self._sender.send_bits(bits)

    def get_bits(self, n: int) -> list[int]:
        return self._sender.get_bits(n)
    
    def receive_bits(self, bits: list[int]) -> None:
        return self._receiver.receive_bits(bits)
    
    def send_bytes(self, data: bytes) -> None:
        return self._sender.send_bytes(data)
