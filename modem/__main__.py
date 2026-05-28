import dataclasses
import json
import modem.modem
import modem.byte_protocols.v250
import modem.frontend.tcp_server
import modem.phone.sip

@dataclasses.dataclass
class Configuration:
    server: str
    port: int
    user: str
    password: str
    record: bool
    enable_v21: bool
    enable_v22: bool

def main() -> int:
    print("Loading configuration...")
    configuration = load_configuration()

    print("Connecting to the SIP provider...")
    phone = modem.phone.sip.SIPPhone(
        configuration.user,
        configuration.password,
        configuration.server,
        configuration.port
    )
    
    print("Connected")

    frontend = modem.frontend.tcp_server.TCPServer("0.0.0.0", 6666)
    app = modem.modem.Modem(
        phone,
        configuration.record,
        configuration.enable_v21,
        configuration.enable_v22
    )
    v250 = modem.byte_protocols.v250.V250(phone, app)
    v250.byte_receiver = frontend
    frontend.byte_sender = v250
    app.byte_protocol = v250
    frontend.run()
    return 0

def load_configuration(file_name: str = "config.json") -> Configuration:
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
        raise Exception("Missing \"modem\" object in the configuration file.")
    
    modem = configuration_dict["modem"]

    if "record" not in modem:
        raise Exception("Missing \"record\" value in modem object.")

    if "enable_v21" not in modem:
        raise Exception("Missing \"enable_v21\" value in modem object.")

    if "enable_v22" not in modem:
        raise Exception("Missing \"enable_v22\" value in modem object.")
    
    return Configuration(
        sip["server"],
        sip["port"],
        sip["user"],
        sip["password"],
        modem["record"],
        modem["enable_v21"],
        modem["enable_v22"]
    )

if __name__ == "__main__":
    exit(main())
