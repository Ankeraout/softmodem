# Softmodem
This project is a software modem written in Python.

## Features
- SIP client
- ITU-T V.21 support
- ITU-T V.22 support (no V.22bis)
- Call recording (WAV PCM linear 8-bit 8 kHz) of both RX and TX signals

## Usage
Create a `config.json` file based on the `config.json.example` template, then
run:
```sh
python3 -m modem
```

The application will listen for an incoming connection on port TCP 6666.
The following clients can connect to this port:
- Terminal clients such as Telnet or PuTTY
- Virtual machines with COM port forwarding (useful for realistic simulation)

## Known bugs
- The modem is sometimes in an unstable state after disconnecting/hanging up a
call. It is preferrable to restart the application after a call, even if the
call failed.
