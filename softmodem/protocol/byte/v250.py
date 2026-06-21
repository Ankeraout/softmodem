import enum
import softmodem
import threading
import time
import traceback
import typing

COMMAND_BUFFER_LENGTH = 80

class ModemState(enum.Enum):
    COMMAND = enum.auto()
    COMMAND_a = enum.auto()
    COMMAND_A = enum.auto()
    COMMAND_AT = enum.auto()
    DATA = enum.auto()
    DATA_PLUS_1 = enum.auto()
    DATA_PLUS_2 = enum.auto()
    DATA_PLUS_3 = enum.auto()

class V250(softmodem.IByteProtocol):
    def __init__(
        self,
        phone: softmodem.IPhone,
        modem: softmodem.IModem
    ) -> None:
        self._phone: softmodem.IPhone = phone
        self._modem = modem
        self._byte_receiver: softmodem.IByteReceiver | None = None
        self._command_buffer: str = ""
        self._s_register: list[int] = [0] * 11
        self._state: ModemState = ModemState.COMMAND
        self._echo: bool = True
        self._quiet: bool = False
        self._command_handlers: dict[str, typing.Callable[[], bool]] = {
            "D": self._command_handler_d,
            "E": self._command_handler_e,
            "H": self._command_handler_h,
            "I": self._command_handler_i,
            "O": self._command_handler_o,
            "Q": self._command_handler_q,
            "S": self._command_handler_s,
            "V": self._command_handler_v,
            "Z": self._command_handler_z
        }
        self._command_parser_index: int = 0
        self._escape_start_time: float = 0.0
        self._alarm_thread = threading.Thread(target=self._alarm_thread_main)
        self._alarm_thread.start()
        self.reset()

    @property
    def byte_receiver(self) -> softmodem.IByteReceiver | None:
        return self._byte_receiver
    
    @byte_receiver.setter
    def byte_receiver(self, byte_receiver: softmodem.IByteReceiver | None) -> None:
        self._byte_receiver = byte_receiver

    def send_bytes(self, data: bytes) -> None:
        with self._modem._lock:
            for byte in data:
                if self._echo:
                    if self._byte_receiver is not None:
                        self._byte_receiver.receive_bytes(bytes([byte]))

                match self._state:
                    case ModemState.COMMAND:
                        if byte == ord('A'):
                            self._state = ModemState.COMMAND_A
                        
                        elif byte == ord('a'):
                            self._state = ModemState.COMMAND_a

                    case ModemState.COMMAND_A:
                        if byte == ord('T'):
                            self._state = ModemState.COMMAND_AT
                            self._command_buffer = ""

                        elif byte == ord('A'):
                            self._state = ModemState.COMMAND_A

                        elif byte == ord('a'):
                            self._state = ModemState.COMMAND_a

                        else:
                            self._state = ModemState.COMMAND
                    
                    case ModemState.COMMAND_a:
                        if byte == ord('t'):
                            self._state = ModemState.COMMAND_AT
                            self._command_buffer = ""

                        elif byte == ord('A'):
                            self._state = ModemState.COMMAND_A

                        elif byte == ord('a'):
                            self._state = ModemState.COMMAND_a

                        else:
                            self._state = ModemState.COMMAND

                    case ModemState.COMMAND_AT:
                        if byte == self._s_register[3]:
                            self._state = ModemState.COMMAND
                            self._execute_command()
                        
                        elif byte == self._s_register[5]:
                            if len(self._command_buffer) > 0:
                                self._command_buffer = self._command_buffer[:-1]

                        else:
                            if len(self._command_buffer) < COMMAND_BUFFER_LENGTH:
                                self._command_buffer += chr(byte & 0x7f)
                    
                    case ModemState.DATA:
                        if byte == ord('+'):
                            self._state = ModemState.DATA_PLUS_1
                        
                        else:
                            self._send_byte(byte)
                        
                    case ModemState.DATA_PLUS_1:
                        if byte == ord('+'):
                            self._state = ModemState.DATA_PLUS_2
                        
                        else:
                            self._send_byte(ord('+'))
                            self._send_byte(byte)
                            self._state = ModemState.DATA
                        
                    case ModemState.DATA_PLUS_2:
                        if byte == ord('+'):
                            self._state = ModemState.DATA_PLUS_3
                            self._escape_start_time = time.time()
                        
                        else:
                            self._send_byte(ord('+'))
                            self._send_byte(ord('+'))
                            self._send_byte(byte)
                            self._state = ModemState.DATA
                        
                    case ModemState.DATA_PLUS_3:
                        if byte == ord('+'):
                            self._send_byte(ord('+'))
                            self._state = ModemState.DATA_PLUS_3
                            self._escape_start_time = time.time()
                        
                        else:
                            self._send_byte(ord('+'))
                            self._send_byte(ord('+'))
                            self._send_byte(ord('+'))
                            self._send_byte(byte)
                            self._state = ModemState.DATA

    def receive_bytes(self, data: bytes):
        with self._modem._lock:
            if self._byte_receiver is not None and self._state in (
                ModemState.DATA,
                ModemState.DATA_PLUS_1,
                ModemState.DATA_PLUS_2,
                ModemState.DATA_PLUS_3
            ):
                self._byte_receiver.receive_bytes(data)

    def reset(self):
        self._s_register = [
            0,
            0,
            0,
            13,
            10,
            8,
            0,
            0,
            0,
            0,
            0
        ]
        self._state = ModemState.COMMAND
        self._command_buffer = ""
        self._echo = True
        self._quiet = False
        self._command_parser_index: int = 0

    def _execute_command(self) -> None:
        print("Execute command: {:s}".format(self._command_buffer))

        self._command_parser_index = 0

        while self._command_parser_index < len(self._command_buffer):
            command = self._command_buffer[self._command_parser_index].upper()
            self._command_parser_index += 1

            if command in self._command_handlers:
                try:
                    if not self._command_handlers[command]():
                        return
                    
                except Exception as e:
                    self._send_response("ERROR")
                    traceback.print_exc(e)
                    return

            else:
                self._send_response("ERROR")
                return
        
        self._send_response("OK")

    def _send_byte(self, byte: int) -> None:
        with self._modem._lock:
            self._modem.data_session.bit_protocol.send_bytes(byte.to_bytes())

    def _command_parse_peek(self) -> str:
        if self._command_parser_index == len(self._command_buffer):
            return ""
        
        else:
            return self._command_buffer[self._command_parser_index]
    
    def _command_parse_next(self) -> str:
        if self._command_parser_index < len(self._command_buffer):
            self._command_parser_index += 1
        
        return self._command_parse_peek()

    def _command_parse_int(self) -> int:
        value: int = 0
        character = self._command_parse_peek()

        if not character.isdigit():
            raise Exception("Failed to parse digit.")

        while character.isdigit():
            value = (value * 10) + int(character)
            character = self._command_parse_next()
        
        return value
    
    def _command_handler_d(self) -> bool:
        dial_string = ""

        while self._command_parse_peek() not in ('', ';'):
            dial_string += self._command_parse_peek()
            self._command_parse_next()

        if dial_string[0] in ('t', 'T', 'p', 'P'):
            dial_string = dial_string[1:]
        
        self._state = ModemState.DATA
        self._modem.call(dial_string)
        
        return False

    def _command_handler_e(self) -> bool:
        value = self._command_parse_int()

        if value == 0:
            self._echo = False

        elif value == 1:
            self._echo = True

        else:
            self._send_response("ERROR")
            return False
        
        return True
    
    def _command_handler_h(self) -> bool:
        if self._modem.state != softmodem.ModemState.IDLE:
            self._modem.hangup()

        else:
            self._send_response("ERROR")
            return False
        
        return True
    
    def _command_handler_i(self) -> bool:
        value = self._command_parse_int()
        self._send_response("SoftModem 0.1.0")
        return True
    
    def _command_handler_o(self) -> bool:
        if self._modem.state != softmodem.ModemState.IDLE:
            self._state = ModemState.DATA
            return True
        
        else:
            self._send_response("ERROR")
            return False

    def _command_handler_q(self) -> bool:
        value = self._command_parse_int()

        if value == 0:
            self._quiet = False

        elif value == 1:
            self._quiet = True

        else:
            self._send_response("ERROR")
            return False
        
        return True
    
    def _command_handler_s(self) -> bool:
        register_number = self._command_parse_int()

        if register_number >= len(self._s_register):
            self._send_response("ERROR")
            return False
        
        command_type = self._command_parse_peek()
        self._command_parse_next()

        if command_type == '?':
            self._send_response(str(self._s_register[register_number]))

        elif command_type == '=':
            self._s_register[register_number] = self._command_parse_int()

        return True

    def _command_handler_v(self) -> bool:
        value = self._command_parse_int()

        if value != 1:
            self._send_response("ERROR")
            return False
        
        return True
    
    def _command_handler_z(self) -> bool:
        self.reset()
        return True
    
    def _send_response(self, response: str) -> None:
        if self._byte_receiver is not None:
            self._byte_receiver.receive_bytes(
                "{:c}{:c}{:s}{:c}{:c}".format(
                    self._s_register[3],
                    self._s_register[4],
                    response,
                    self._s_register[3],
                    self._s_register[4]
                ).encode()
            )

    def _alarm_thread_main(self) -> None:
        while True:
            with self._modem._lock:
                if self._state in (
                    ModemState.DATA,
                    ModemState.DATA_PLUS_1,
                    ModemState.DATA_PLUS_2,
                    ModemState.DATA_PLUS_3
                ):
                    if (
                        (self._state == ModemState.DATA_PLUS_3)
                        and (time.time() >= (self._escape_start_time + 1))
                    ):
                        self._state = ModemState.COMMAND
                        self._send_response("OK")

            time.sleep(0.1)
