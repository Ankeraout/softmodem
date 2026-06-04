import enum
import hashlib
import random
import re
import socket
import threading
import time
import traceback
import typing

SIP_MAX_MESSAGE_SIZE = 65535
SAMPLES_PER_PACKET = 160
RTP_HEADER_SIZE = 12
PTIME_MS = 20

class SIPClientState(enum.Enum):
    STOPPED = enum.auto()
    STARTING = enum.auto()
    REGISTERING = enum.auto()
    REGISTERED = enum.auto()
    STOPPING = enum.auto()

class SIPCallState(enum.Enum):
    DIALING = enum.auto()
    RINGING = enum.auto()
    CONNECTED = enum.auto()
    TERMINATED = enum.auto()

class AudioBuffer:
    def __init__(self, max_size: int = 0):
        self._buffer = bytearray()
        self._lock = threading.RLock()
        self._fill_event = threading.Condition(self._lock)
        self._max_size = max_size

    def write(self, data: bytes) -> None:
        with self._lock:
            if self._max_size > 0:
                total_bytes = len(self._buffer) + len(data)

                if total_bytes > self._max_size:
                    del self._buffer[:total_bytes - self._max_size]
                
            self._buffer.extend(data)
            self._fill_event.notify_all()
        
    def read(self, n: int, timeout: typing.Optional[float] = None) -> bytes:
        deadline = time.monotonic() + timeout if timeout is not None else None

        with self._fill_event:
            while len(self._buffer) < n:
                if deadline is not None:
                    remaining = deadline - time.monotonic()

                    if remaining <= 0:
                        break

                    self._fill_event.wait(timeout)
                
                else:
                    self._fill_event.wait()
            
            byte_count = min(n, len(self._buffer))
            data = self._buffer[:byte_count]
            del self._buffer[:byte_count]

            return data

class RTPSession:
    def __init__(
        self,
        local_ip: str,
        local_port: int,
        buffer_size: int = 0
    ) -> None:
        self.local_ip = local_ip
        self.local_port = local_port

        self._remote_ip: typing.Optional[str] = None
        self._remote_port: typing.Optional[int] = None

        self._seq = random.randint(0, 0xffff)
        self._ts = random.randint(0, 0xffffffff)
        self._ssrc = random.randint(0, 0xffffffff)
        self._lock = threading.RLock()

        self._buffer = AudioBuffer(buffer_size)

        self._socket: typing.Optional[socket.socket] = None
        self._running: bool = False
        self._receive_thread: typing.Optional[threading.Thread] = None

    def set_remote(self, ip: str, port: int) -> None:
        self._remote_ip = ip
        self._remote_port = port
        self._socket.connect((self._remote_ip, self._remote_port))
    
    def start(self) -> None:
        self._socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
            socket.IPPROTO_UDP
        )
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self._socket.bind((self.local_ip, self.local_port))
        self._socket.settimeout(1)
        self._running = True

        self._receive_thread = threading.Thread(
            target=self._receive_thread_main,
            daemon=True,
            name="RTP receive"
        )
        self._receive_thread.start()

    def stop(self) -> None:
        self._running = False

        if self._receive_thread is not None:
            self._receive_thread.join()
        
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def send_packet(self, data: bytes) -> None:
        if (
            self._remote_ip is None
            or self._remote_port is None
            or self._socket is None
        ):
            return

        with self._lock:
            header = self._build_header()
            self._seq = (self._seq + 1) & 0xffff
            self._ts = (self._ts + len(data)) & 0xffffffff
        
        try:
            self._socket.send(header + data)

        except:
            pass

    def _receive_thread_main(self) -> None:
        while self._running:
            try:
                data = self._socket.recv(4096)

            except socket.timeout:
                continue

            except:
                break

            if len(data) < RTP_HEADER_SIZE:
                continue

            payload = data[RTP_HEADER_SIZE:]

            if len(payload) > 0:
                self._buffer.write(payload)

    def _build_header(self) -> None:
        return (
            b"\x80\x00"
            + self._seq.to_bytes(2, "big")
            + self._ts.to_bytes(4, "big")
            + self._ssrc.to_bytes(4, "big")
        )

class SIPCall:
    def __init__(
        self,
        call_id: str,
        tag: str,
        rtp_session: RTPSession,
        number: str
    ) -> None:
        self.call_id = call_id
        self.tag = tag
        self._rtp_session = rtp_session
        self.number = number

        self._state = SIPCallState.DIALING
        self._cseq_invite = 0
        self._remote_tag: typing.Optional[str] = None

        self._state_lock = threading.RLock()
        self._on_hangup: typing.Optional[typing.Callable[[], None]] = None

    def write_audio(self, data: bytes) -> None:
        self._rtp_session.send_packet(data)

    def read_audio(
        self,
        n: int = SAMPLES_PER_PACKET,
        timeout: typing.Optional[float] = None
    ) -> bytes:
        with self._state_lock:
            if self._state == SIPCallState.CONNECTED:
                return self._rtp_session._buffer.read(n, timeout)

            else:
                return b""
            
    def hangup(self) -> None:
        if self._on_hangup is not None:
            self._on_hangup()

    @property
    def state(self) -> SIPCallState:
        return self._state

    def _set_state(self, state: SIPCallState) -> None:
        with self._state_lock:
            self._state = state

class SIPClient:
    def __init__(
        self,
        username: str,
        password: str,
        domain: str,
        server_ip: typing.Optional[str] = None,
        server_port: int = 5060,
        local_ip: typing.Optional[str] = None,
        local_port: int = 5060,
        rtp_port_start: int = 10000,
        register_interval: int = 60,
        receive_buffer_size: int = 0
    ) -> None:
        self._username = username
        self._password = password
        self._domain = domain
        self._server_ip = server_ip if server_ip is not None else domain
        self._server_port = server_port
        self._local_ip = (
            local_ip if local_ip is not None
            else SIPClient._get_local_ip()
        )
        self._local_port = local_port
        self._rtp_port_start = rtp_port_start
        self._register_interval = register_interval
        self._receive_buffer_size = receive_buffer_size

        self._lock = threading.RLock()
        self._state = SIPClientState.STOPPED
        
        self._next_rtp_port = rtp_port_start

        self._register_thread: threading.Thread | None = None
        self._receive_thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._cseq: int = 0
        self._register_cseq: int = 0
        self._register_tag: str = ""
        self._register_call_id: str = ""
        self._register_realm: typing.Optional[str] = None
        self._register_nonce: typing.Optional[str] = None
        self._calls_lock = threading.RLock()
        self._calls: dict[str, SIPCall] = dict()

    @property
    def state(self) -> SIPClientState:
        return self._state
    
    def start(self) -> None:
        with self._lock:
            if self.state != SIPClientState.STOPPED:
                raise Exception("The client is already started.")
            
            self._socket = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM,
                socket.IPPROTO_UDP
            )
            self._socket.bind(
                (
                    socket.INADDR_ANY if self._local_ip is None
                    else self._local_ip,
                    self._local_port
                )
            )
            self._socket.connect((self._domain, self._server_port))
            self._socket.settimeout(1)

            self._register_cseq = 0
            self._register_tag = SIPClient._generate_tag()
            self._register_call_id = self._generate_call_id()

            self._state = SIPClientState.STARTING
            self._receive_thread = threading.Thread(
                target=self._receive_thread_main,
                name="SIP receive",
                daemon=True
            )
            self._register_thread = threading.Thread(
                target=self._register_thread_main,
                name="SIP register",
                daemon=True
            )
            self._receive_thread.start()
            self._register_thread.start()

    def stop(self) -> None:
        with self._lock:
            if self._state in (
                SIPClientState.STOPPING,
                SIPClientState.STOPPED
            ):
                raise Exception("The client is already stopping or stopped.")
            
            self._state = SIPClientState.STOPPING
            
        # TODO: stop all calls
        
        self._register_thread.join()
        self._receive_thread.join()

        with self._lock:
            self._state = SIPClientState.STOPPED

    def dial(self, number: str) -> SIPCall:
        if self._state != SIPClientState.REGISTERED:
            raise Exception("SIP client is not registered.")
        
        rtp_session = RTPSession(
            self._local_ip,
            self._allocate_rtp_port(),
            self._receive_buffer_size
        )
        rtp_session.start()

        call_id = self._generate_call_id()
        tag = SIPClient._generate_tag()
        call = SIPCall(call_id, tag, rtp_session, number)

        with self._lock:
            cseq = self._register_cseq + 1
            self._cseq = cseq

        call._cseq_invite = cseq

        with self._calls_lock:
            self._calls[call_id] = call
        
        call._on_hangup = lambda: self._terminate_call(call)

        threading.Thread(
            target=self._invite_thread_main,
            args=(call, number, cseq),
            daemon=True,
            name="SIP call {:s}".format(call_id)
        ).start()

        return call

    def _allocate_rtp_port(self) -> int:
        port = self._next_rtp_port
        self._next_rtp_port += 2
        return port

    def _terminate_call(self, call: SIPCall) -> None:
        self._send_bye_or_cancel(call)
        self._cleanup_call(call)

    def _send_bye_or_cancel(self, call: SIPCall) -> None:
        uri = f"sip:{self._domain}"
        from_uri = f"sip:{self._username}@{self._domain}"

        with self._lock:
            cseq = self._cseq + 1
            self._cseq = cseq

        if call.state == SIPCallState.CONNECTED:
            lines = [
                f"BYE {uri} SIP/2.0",
                f"To: <{uri}>{f";tag={call._remote_tag}" if call._remote_tag is not None else ""}"
            ]

        elif call.state in (SIPCallState.CALLING, SIPCallState.RINGING):
            lines = [
                f"CANCEL {uri} SIP/2.0",
                f"To: <{uri}>",
                f"CSeq: {cseq} CANCEL"
            ]

        lines.extend(
            [
                f"Via: SIP/2.0/UDP {self._local_ip}:{self._local_port};branch={SIPClient._generate_branch()}",
                f"From: <{from_uri}>;tag={call.tag}",
                f"Call-ID: {call.call_id}",
                "Max-Forwards: 70",
                "Content-Length: 0",
                "",
                ""
            ]
        )

        self._socket.send("\r\n".join(lines).encode())

    def _cleanup_call(self, call: SIPCall) -> None:
        call._rtp_session.stop()

        with self._calls_lock:
            del self._calls[call.call_id]

    def _invite_thread_main(
        self,
        call: SIPCall,
        number: str,
        cseq: int
    ) -> None:
        sdp = self._build_sdp(call._rtp_session.local_port)
        self._socket.send(
            self._build_invite(
                call,
                f"sip:{number}@{self._domain}",
                cseq,
                sdp
            ).encode()
        )

    def _build_sdp(self, rtp_port: int) -> str:
        return "\r\n".join(
            [
                "v=0",
                f"o=sip_client 0 0 IN IP4 {self._local_ip}",
                "s=SIP Call",
                f"c=IN IP4 {self._local_ip}",
                "t=0 0",
                f"m=audio {rtp_port} RTP/AVP 0",
                f"a=rtpmap:0 PCMU/8000",
                f"a=ptime:{PTIME_MS}",
                "a=sendrecv",
                ""
            ]
        )
    
    def _build_invite(
        self,
        call: SIPCall,
        uri: str,
        cseq: int,
        sdp: str,
        auth_header: typing.Optional[str] = None
    ) -> str:
        sdp_bytes = sdp.encode()

        lines = [
            f"INVITE {uri} SIP/2.0",
            f"Via: SIP/2.0/UDP {self._local_ip}:{self._local_port};branch={SIPClient._generate_branch()}",
            f"From: <sip:{self._username}@{self._domain}>;tag={call.tag}",
            f"To: <{uri}>",
            f"Call-ID: {call.call_id}",
            f"CSeq: {cseq} INVITE",
            f"Contact: <sip:{self._username}@{self._local_ip}:{self._local_port}>",
            "Max-Forwards: 70",
            "Content-Type: application/sdp",
            f"Content-Length: {len(sdp_bytes)}"
        ]

        if auth_header is not None:
            lines.append(auth_header)

        lines.append("")
        lines.append(sdp)

        return "\r\n".join(lines)

    def _register_thread_main(self) -> None:
        self._state = SIPClientState.REGISTERING
        time_last_register = 0

        while self._state != SIPClientState.STOPPING:
            current_time = time.monotonic()

            if current_time - time_last_register >= self._register_interval:
                self._send_register()
                time_last_register = current_time

            else:
                time.sleep(1)

    def _receive_thread_main(self) -> None:
        while self._state != SIPClientState.STOPPING:
            try:
                packet = self._socket.recv(SIP_MAX_MESSAGE_SIZE)

            except socket.timeout:
                continue

            try:
                packet_str = packet.decode()

                if packet_str.startswith("SIP/2.0"):
                    self._handle_response(packet_str)

                else:
                    self._handle_request(packet_str)

            except:
                print("Packet error")
                traceback.print_exc()
                # Ignore the packet
                continue

        print("[{:s}] Exiting".format(threading.current_thread().name))

    def _handle_response(self, message: str) -> None:
        cseq = SIPClient._parse_header(message, "CSeq")

        if cseq is None:
            return

        match cseq.split()[-1]:
            case "REGISTER":
                self._handle_response_register(message)

            case "INVITE":
                self._handle_response_invite(message)

            case "BYE":
                self._handle_response_bye(message)

    def _handle_response_register(self, message: str) -> None:
        code = SIPClient._parse_status_code(message)

        if code is None:
            return

        match code:
            case 401:
                data = SIPClient._parse_www_authenticate(
                    SIPClient._parse_header(
                        message,
                        "WWW-Authenticate"
                    )
                )
                self._register_realm = data["realm"]
                self._register_nonce = data["nonce"]
                self._send_register()

            case 200:
                with self._lock:
                    if self._state == SIPClientState.REGISTERING:
                        print("[SIP] Client registered")
                        self._state = SIPClientState.REGISTERED
            
            case _:
                print("[SIP] REGISTER failed: {:d}".format(code))

    def _handle_response_invite(self, message: str) -> None:
        code = SIPClient._parse_status_code(message)

        if code is None:
            return
        
        call_id = SIPClient._parse_header(message, "Call-ID")

        if call_id is None:
            return

        to_header = SIPClient._parse_header(message, "To")

        with self._calls_lock:
            if call_id not in self._calls:
                return

            call = self._calls[call_id]

        if to_header is not None:
            match = re.search(r"tag=([\w.+%-]+)", to_header)

            if match is not None:
                call._remote_tag = match.group(1)

        match code:
            case 100:
                call._set_state(SIPCallState.DIALING)

            case 180:
                call._set_state(SIPCallState.RINGING)

            case 200:
                try:
                    body_start = message.index("\r\n\r\n") + 4

                except:
                    return

                sdp = message[body_start:]
                remote_port = re.search(r"m=audio\s+(\d+)", sdp).group(1)

                if remote_port is None:
                    return

                remote_ip = re.search(r"c=IN IP4 ([^\s\r\n]+)", sdp).group(1)

                if remote_ip is None:
                    remote_ip = self._server_ip

                call._rtp_session.set_remote(remote_ip, int(remote_port))

                uri = f"sip:{call.number}@{self._domain}"

                self._socket.send(
                    "\r\n".join(
                        [
                            f"ACK {uri} SIP/2.0",
                            f"Via: SIP/2.0/UDP {self._local_ip}:{self._local_port};branch={SIPClient._generate_branch()}",
                            f"From: <sip:{self._username}@{self._domain}>;tag={call.tag}",
                            f"To: <{uri}>{f";tag={call._remote_tag}" if call._remote_tag is not None else ""}",
                            f"Call-ID: {call_id}",
                            f"CSeq: {call._cseq_invite} ACK",
                            "Max-Forwards: 70",
                            "Content-Length: 0",
                            "",
                            ""
                        ]
                    ).encode()
                )

                call._set_state(SIPCallState.CONNECTED)

            case 401:
                auth_header = SIPClient._parse_header(
                    message,
                    "WWW-Authenticate"
                )

                if auth_header is not None:
                    self._resend_invite_with_auth(
                        call,
                        SIPClient._parse_www_authenticate(auth_header)
                    )

            case _:
                if code >= 400:
                    call._set_state(SIPCallState.TERMINATED)
                    self._cleanup_call(call)

    def _resend_invite_with_auth(
        self,
        call: SIPCall,
        params: dict[str, str]
    ) -> None:
        realm = params.get("realm", "")
        nonce = params.get("nonce", "")
        uri = f"sip:{call.number}@{self._domain}"
        response = self._digest_response(realm, nonce, "INVITE", uri)
        
        auth_header = (
            f"Authorization: Digest username=\"{self._username}\","
            f"realm=\"{realm}\","
            f"nonce=\"{nonce}\","
            f"uri=\"{uri}\","
            f"response=\"{response}\","
            "algorithm=MD5"
        )

        with self._lock:
            cseq = self._cseq + 1
            self._cseq = cseq

        call._cseq_invite = cseq
        sdp = self._build_sdp(call._rtp_session.local_port)
        self._socket.send(
            self._build_invite(call, uri, cseq, sdp, auth_header).encode()
        )

    def _handle_response_bye(self, message: str) -> None:
        code = SIPClient._parse_status_code(message)

        if code is None:
            return
        
        call_id = SIPClient._parse_header(message, "Call-ID")

        if call_id is None:
            return

        with self._calls_lock:
            call = self._calls[call_id]

        if call is not None:
            call._set_state(SIPCallState.TERMINATED)
            self._cleanup_call(call)

    def _handle_request(self, message: str) -> None:
        first_line = message.split("\r\n")[0]

        if first_line is None:
            return

        method = first_line.split()[0]

        call_id = SIPClient._parse_header(message, "Call-ID")

        if call_id is None:
            return
        
        match method:
            case "BYE":
                with self._calls_lock:
                    if call_id not in self._calls:
                        return
                    
                    call = self._calls.get(call_id)

                self._socket.send(
                    "\r\n".join(
                        [
                            "SIP/2.0 200 OK",
                            f"Via: {SIPClient._parse_header(message, "Via")}",
                            f"From: {SIPClient._parse_header(message, "From")}",
                            f"To: {SIPClient._parse_header(message, "To")}",
                            f"Call-ID: {SIPClient._parse_header(message, "Call-ID")}",
                            f"CSeq: {SIPClient._parse_header(message, "CSeq")}",
                            "Content-Length: 0",
                            "",
                            ""
                        ]
                    ).encode()
                )

                call._set_state(SIPCallState.TERMINATED)
                self._cleanup_call(call)

    def _parse_header(msg: str, header: str) -> typing.Optional[str]:
        pattern = re.compile(
            rf"^{re.escape(header)}\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE
        )
        match = pattern.search(msg)
        return match.group(1).strip() if match else None

    def _parse_status_code(msg: str) -> typing.Optional[int]:
        match = re.match(r"SIP/2\.0\s+(\d{3})", msg)
        return int(match.group(1)) if match else None
    
    def _parse_www_authenticate(header_val: str) -> dict[str, str]:
        result = {}

        for key in ("realm", "nonce", "qop", "algorithm"):
            match = re.search(
                rf'{key}="?([^",\s]+)"?',
                header_val,
                re.IGNORECASE
            )

            if match:
                result[key] = match.group(1)

        return result

    def _send_register(self, expires: int = 300) -> None:
        with self._lock:
            self._register_cseq += 1
            cseq = self._register_cseq

            from_uri = f"sip:{self._username}@{self._domain}"

            packet_lines = [
                f"REGISTER sip:{self._domain} SIP/2.0",
                f"Via: SIP/2.0/UDP {self._local_ip}:{self._local_port};branch={SIPClient._generate_branch()}",
                f"From: <{from_uri}>;tag={self._register_tag}",
                f"To: <{from_uri}>",
                f"Call-ID: {self._register_call_id}",
                f"CSeq: {cseq} REGISTER",
                f"Contact: <sip:{self._username}@{self._local_ip}:{self._local_port}>",
                f"Expires: {expires}",
                "Max-Forwards: 70",
                "Content-Length: 0"
            ]

            if self._register_nonce is not None and self._register_realm is not None:
                uri = f"sip:{self._domain}"
                response = self._digest_response(
                    self._register_realm,
                    self._register_nonce,
                    "REGISTER",
                    uri
                )
                parts = [
                    f"Authorization: Digest username=\"{self._username}\"",
                    f"realm=\"{self._register_realm}\"",
                    f"nonce=\"{self._register_nonce}\"",
                    f"uri=\"{uri}\"",
                    f"response=\"{response}\"",
                    "algorithm=MD5"
                ]

                packet_lines.append(",".join(parts))
            
            packet_lines.extend(["", ""])
            
        self._socket.send("\r\n".join(packet_lines).encode())
    
    def _generate_call_id(self) -> str:
        return "{:s}@{:s}".format(
            SIPClient._generate_tag(16),
            self._domain
        )
    
    def _digest_response(
        self,
        realm: str,
        nonce: str,
        method: str,
        uri: str
    ) -> str:
        ha1 = hashlib.md5(
            f"{self._username}:{realm}:{self._password}".encode()
        ).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        return hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
    
    @staticmethod
    def _get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        
        except OSError:
            return "127.0.0.1"

    @staticmethod
    def _generate_tag(n: int = 8) -> str:
        return hex(random.getrandbits(n * 4))[2:].zfill(n)

    @staticmethod
    def _generate_branch() -> str:
        return "z9hG4bK" + SIPClient._generate_tag(16)
