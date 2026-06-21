import dataclasses
import json
import socket
import softmodem.modem
import softmodem.phone.sip
import softmodem.util.socket
import threading
import traceback

@dataclasses.dataclass
class Configuration:
    server: str
    port: int
    user: str
    password: str
    record: bool
    enable_v21: bool
    enable_v22: bool

class Application:
    def __init__(self) -> None:
        self._stop_request = False
        print("[softmodem] Loading configuration...")
        self.load_configuration()

    def load_configuration(
        self,
        file_name: str = "config.json"
    ) -> Configuration:
        with open(file_name, "r") as f:
            configuration_dict = json.load(f)

        if not isinstance(configuration_dict, dict):
            raise Exception("Invalid configuration file.")
        
        if "sip" not in configuration_dict:
            raise Exception("Missing \"sip\" object in the configuration file.")
        
        sip = configuration_dict["sip"]

        if any(x not in sip for x in ("server", "port", "user", "password")):
            raise Exception("Incomplete SIP configuration.")
        
        if "modem" not in configuration_dict:
            raise Exception(
                "Missing \"modem\" object in the configuration file."
            )
        
        modem = configuration_dict["modem"]

        if "record" not in modem:
            raise Exception("Missing \"record\" value in modem object.")

        if "enable_v21" not in modem:
            raise Exception("Missing \"enable_v21\" value in modem object.")

        if "enable_v22" not in modem:
            raise Exception("Missing \"enable_v22\" value in modem object.")
        
        self._configuration = Configuration(
            sip["server"],
            sip["port"],
            sip["user"],
            sip["password"],
            modem["record"],
            modem["enable_v21"],
            modem["enable_v22"]
        )

    def run(self) -> None:
        print("[softmodem] Creating server socket...")
        server_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP
        )
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        server_socket.bind(("0.0.0.0", 6666))
        server_socket.listen()
        server_socket.settimeout(1)

        print("[softmodem] Connecting to the SIP provider...")
        self._phone = softmodem.phone.sip.SIPPhone(
            self._configuration.user,
            self._configuration.password,
            self._configuration.server,
            self._configuration.port
        )

        print("[softmodem] Waiting for incoming connections...")

        self._stop_request = False

        while not self._stop_request:
            try:
                client_socket, client_address = server_socket.accept()
                client_socket.setsockopt(
                    socket.IPPROTO_TCP,
                    socket.TCP_NODELAY,
                    1
                )
                client_socket.settimeout(1)

                print(
                    "[softmodem] Accepted incoming connection from "
                    "{:s}.".format(
                        str(client_address)
                    )
                )

                client_thread = threading.Thread(
                    target=self._client_thread_main,
                    name="Client thread {:s}".format(str(client_address)),
                    args=(client_socket,),
                    daemon=True
                )
                client_thread.start()

            except TimeoutError:
                pass

            except KeyboardInterrupt:
                self._stop_request = True
                print("[softmodem] Received keyboard interrupt, exiting.")

            except:
                self._stop_request = True
                print("[softmodem] Exception in main thread, exiting.")

        return 0

    def _client_thread_main(
        self,
        client_socket: socket.socket
    ) -> None:
        byte_receiver = softmodem.util.socket.SocketByteReceiver(client_socket)
        modem = softmodem.modem.Modem(
            self._phone,
            byte_receiver,
            self._configuration.record,
            self._configuration.enable_v21,
            self._configuration.enable_v22
        )

        while not self._stop_request:
            try:
                received_bytes = client_socket.recv(1500)

                if len(received_bytes) == 0:
                    break

                modem.send_bytes(received_bytes)

            except TimeoutError:
                pass

            except Exception as e:
                print(
                    "[{:s}] Exception:".format(
                        threading.current_thread().name
                    )
                )
                traceback.print_exc(e)

        print(
            "[{:s}] Connection closed.".format(
                threading.current_thread().name
            )
        )

        client_socket.close()

if __name__ == "__main__":
    exit(Application().run())
