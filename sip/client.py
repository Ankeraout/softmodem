# TODO: rewrite this without AI

import hashlib
import logging
import random
import re
import socket
import threading
import time
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)

class SIPStatus(Enum):
    STOPPED     = auto()
    STARTING    = auto()
    REGISTERING = auto()
    REGISTERED  = auto()
    STOPPING    = auto()


CRLF               = "\r\n"
G711_ULAW_PT       = 0
G711_ULAW_RATE     = 8000
PTIME_MS           = 20
SAMPLES_PER_PACKET = G711_ULAW_RATE * PTIME_MS // 1000

def _random_tag(n: int = 8) -> str:
    return hex(random.getrandbits(n * 4))[2:].zfill(n)

def _random_branch() -> str:
    return "z9hG4bK" + _random_tag(16)

def _random_call_id(domain: str) -> str:
    return f"{_random_tag(16)}@{domain}"

def _digest_response(username: str, password: str, realm: str,
                     nonce: str, method: str, uri: str) -> str:
    ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    return hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()

def _parse_header(msg: str, header: str) -> Optional[str]:
    pattern = re.compile(rf"^{re.escape(header)}\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    m = pattern.search(msg)
    return m.group(1).strip() if m else None

def _parse_status_code(msg: str) -> Optional[int]:
    m = re.match(r"SIP/2\.0\s+(\d{3})", msg)
    return int(m.group(1)) if m else None

def _parse_www_authenticate(header_val: str) -> dict:
    result = {}
    for key in ("realm", "nonce", "qop", "algorithm"):
        m = re.search(rf'{key}="?([^",\s]+)"?', header_val, re.IGNORECASE)
        if m:
            result[key] = m.group(1)
    return result

def _parse_sdp_port(sdp: str) -> Optional[int]:
    m = re.search(r"m=audio\s+(\d+)", sdp)
    return int(m.group(1)) if m else None

def _parse_sdp_connection(sdp: str) -> Optional[str]:
    m = re.search(r"c=IN IP4 ([^\s\r\n]+)", sdp)
    return m.group(1) if m else None

def _build_sdp(local_ip: str, rtp_port: int) -> str:
    lines = [
        "v=0",
        f"o=sip_client 0 0 IN IP4 {local_ip}",
        "s=SIP Call",
        f"c=IN IP4 {local_ip}",
        "t=0 0",
        f"m=audio {rtp_port} RTP/AVP {G711_ULAW_PT}",
        f"a=rtpmap:{G711_ULAW_PT} PCMU/{G711_ULAW_RATE}",
        f"a=ptime:{PTIME_MS}",
        "a=sendrecv",
    ]
    return CRLF.join(lines) + CRLF

class AudioBuffer:
    def __init__(self, maxsize: int = 0):
        self._buf       = bytearray()
        self._lock      = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._maxsize   = maxsize

    def write(self, data: bytes) -> int:
        if not data:
            return 0
        with self._not_empty:
            if self._maxsize:
                total = len(self._buf) + len(data)
                if total > self._maxsize:
                    del self._buf[:total - self._maxsize]
            self._buf.extend(data)
            self._not_empty.notify_all()
        return len(data)

    def read(self, n: int, timeout: Optional[float] = None) -> bytes:
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        with self._not_empty:
            while len(self._buf) < n:
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._not_empty.wait(timeout=remaining)
                else:
                    self._not_empty.wait()
            take   = min(n, len(self._buf))
            result = bytes(self._buf[:take])
            del self._buf[:take]
            return result

    def available(self) -> int:
        with self._lock:
            return len(self._buf)

    def clear(self) -> None:
        with self._not_empty:
            self._buf.clear()

class RTPSession:
    RTP_HEADER_SIZE = 12

    def __init__(self, local_ip: str, local_port: int, recv_buf_max: int = 0):
        self.local_ip   = local_ip
        self.local_port = local_port

        self._remote_ip:   Optional[str] = None
        self._remote_port: Optional[int] = None

        self._seq  = random.randint(0, 0xFFFF)
        self._ts   = random.randint(0, 0xFFFFFFFF)
        self._ssrc = random.randint(0, 0xFFFFFFFF)
        self._rtp_lock = threading.Lock()

        self.recv_buffer = AudioBuffer(maxsize=recv_buf_max)

        self._sock: Optional[socket.socket] = None
        self._running = False
        self._recv_thread: Optional[threading.Thread] = None

    def set_remote(self, ip: str, port: int) -> None:
        self._remote_ip   = ip
        self._remote_port = port

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.local_ip, self.local_port))
        self._sock.settimeout(0.5)
        self._running = True

        self._recv_thread = threading.Thread(
            target=self._recv_loop, daemon=True, name="rtp-recv"
        )
        self._recv_thread.start()

    def stop(self) -> None:
        self._running = False
        if self._recv_thread:
            self._recv_thread.join(timeout=2)
        if self._sock:
            self._sock.close()
            self._sock = None

    def send_packet(self, payload: bytes) -> None:
        if not (self._remote_ip and self._remote_port and self._sock):
            return
        with self._rtp_lock:
            header = self._build_rtp_header()
            self._seq = (self._seq + 1) & 0xFFFF
            self._ts  = (self._ts  + len(payload)) & 0xFFFFFFFF
        try:
            self._sock.sendto(header + payload, (self._remote_ip, self._remote_port))
        except OSError:
            pass

    def _recv_loop(self) -> None:
        while self._running:
            try:
                data, _ = self._sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            if len(data) < self.RTP_HEADER_SIZE:
                continue

            payload = data[self.RTP_HEADER_SIZE:]
            if payload:
                self.recv_buffer.write(payload)

    def _build_rtp_header(self) -> bytes:
        return (
            bytes([0x80, G711_ULAW_PT & 0x7F])
            + self._seq.to_bytes(2, "big")
            + self._ts.to_bytes(4, "big")
            + self._ssrc.to_bytes(4, "big")
        )

class SIPCall:
    class State(Enum):
        CALLING    = auto()
        RINGING    = auto()
        CONNECTED  = auto()
        TERMINATED = auto()
        FAILED     = auto()

    def __init__(self, call_id: str, local_tag: str, rtp_session: RTPSession, number: str = ""):
        self.call_id   = call_id
        self.local_tag = local_tag
        self.number    = number

        self._state  = SIPCall.State.CALLING
        self._rtp    = rtp_session

        self._remote_tag:  Optional[str] = None
        self._cseq_invite: int = 0

        self._state_lock      = threading.Lock()
        self._connected_event = threading.Event()
        self._on_terminated   = None

    def write_audio(self, data: bytes) -> None:
        self._rtp.send_packet(data)

    def read_audio(self, n: int = SAMPLES_PER_PACKET,
                   timeout: Optional[float] = None) -> bytes:
        return self._rtp.recv_buffer.read(n, timeout=timeout)

    def wait_connected(self, timeout: float = 30.0) -> bool:
        return self._connected_event.wait(timeout)

    def hangup(self) -> None:
        if self._on_terminated:
            self._on_terminated()

    @property
    def state(self) -> "SIPCall.State":
        return self._state

    def _set_state(self, state: "SIPCall.State") -> None:
        with self._state_lock:
            self._state = state
        if state in (SIPCall.State.CONNECTED,
                     SIPCall.State.TERMINATED,
                     SIPCall.State.FAILED):
            self._connected_event.set()

    def __repr__(self) -> str:
        return f"<SIPCall {self.call_id} state={self._state.name}>"

class SIPClient:
    def __init__(
        self,
        username:          str,
        password:          str,
        domain:            str,
        server_ip:         Optional[str] = None,
        server_port:       int  = 5060,
        local_ip:          Optional[str] = None,
        local_port:        int  = 5060,
        rtp_port_start:    int  = 10000,
        register_interval: int  = 60,
        recv_buf_max:      int  = 0,
    ):
        self._username  = username
        self._password  = password
        self._domain    = domain
        self._server_ip = server_ip or domain
        self._server_port    = server_port
        self._local_port     = local_port
        self._rtp_port_start = rtp_port_start
        self._register_interval = register_interval
        self._recv_buf_max   = recv_buf_max

        self._local_ip = local_ip or self._detect_local_ip()

        self._status      = SIPStatus.STOPPED
        self._status_lock = threading.Lock()

        self._sock: Optional[socket.socket] = None
        self._cseq      = 1
        self._cseq_lock = threading.Lock()

        self._active_calls: dict[str, SIPCall] = {}
        self._calls_lock = threading.Lock()

        self._recv_thread:     Optional[threading.Thread] = None
        self._register_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._reg_realm:   Optional[str] = None
        self._reg_nonce:   Optional[str] = None
        self._reg_call_id  = _random_call_id(self._domain)
        self._reg_cseq     = 0
        self._reg_tag      = _random_tag()

        self._next_rtp_port = rtp_port_start

    @property
    def status(self) -> SIPStatus:
        return self._status

    def start(self) -> None:
        if self._status != SIPStatus.STOPPED:
            raise RuntimeError("Le client est déjà démarré.")

        self._set_status(SIPStatus.STARTING)
        self._stop_event.clear()

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._local_ip, self._local_port))
        self._sock.settimeout(0.5)

        self._recv_thread = threading.Thread(
            target=self._recv_loop, daemon=True, name="sip-recv"
        )
        self._register_thread = threading.Thread(
            target=self._register_loop, daemon=True, name="sip-register"
        )
        self._recv_thread.start()
        self._register_thread.start()

    def stop(self) -> None:
        if self._status == SIPStatus.STOPPED:
            return

        self._set_status(SIPStatus.STOPPING)
        self._stop_event.set()

        with self._calls_lock:
            calls = list(self._active_calls.values())
        for call in calls:
            self._send_bye_or_cancel(call)
            call._rtp.stop()

        try:
            self._send_register(expires=0)
        except Exception:
            pass

        if self._recv_thread:
            self._recv_thread.join(timeout=3)
        if self._register_thread:
            self._register_thread.join(timeout=3)
        if self._sock:
            self._sock.close()
            self._sock = None

        self._set_status(SIPStatus.STOPPED)

    def dial(self, number: str) -> SIPCall:
        if self._status != SIPStatus.REGISTERED:
            raise RuntimeError("SIP client is not registered.")

        rtp = RTPSession(
            self._local_ip,
            self._alloc_rtp_port(),
            recv_buf_max=self._recv_buf_max,
        )
        rtp.start()

        call_id   = _random_call_id(self._domain)
        local_tag = _random_tag()
        call      = SIPCall(call_id, local_tag, rtp, number=number)

        with self._cseq_lock:
            cseq = self._cseq
            self._cseq += 1
        call._cseq_invite = cseq

        with self._calls_lock:
            self._active_calls[call_id] = call

        call._on_terminated = lambda: self._terminate_call(call)

        threading.Thread(
            target=self._invite_flow,
            args=(call, number, cseq),
            daemon=True,
            name=f"sip-call-{call_id[:8]}",
        ).start()

        return call
    
    def _invite_flow(self, call: SIPCall, number: str, cseq: int) -> None:
        target_uri = f"sip:{number}@{self._domain}"
        sdp        = _build_sdp(self._local_ip, call._rtp.local_port)
        self._send_raw(self._build_invite(call, target_uri, cseq, sdp))
        logger.debug(">> INVITE %s", target_uri)

    def _build_invite(self, call: SIPCall, target_uri: str,
                      cseq: int, sdp: str, auth_header: str = "") -> str:
        from_uri = f"sip:{self._username}@{self._domain}"
        contact  = f"sip:{self._username}@{self._local_ip}:{self._local_port}"
        sdp_b    = sdp.encode()
        lines = [
            f"INVITE {target_uri} SIP/2.0",
            f"Via: SIP/2.0/UDP {self._local_ip}:{self._local_port};branch={_random_branch()}",
            f"From: <{from_uri}>;tag={call.local_tag}",
            f"To: <{target_uri}>",
            f"Call-ID: {call.call_id}",
            f"CSeq: {cseq} INVITE",
            f"Contact: <{contact}>",
            "Max-Forwards: 70",
        ]
        if auth_header:
            lines.append(auth_header)
        lines += [
            "Content-Type: application/sdp",
            f"Content-Length: {len(sdp_b)}",
            "",
            sdp,
        ]
        return CRLF.join(lines)

    def _recv_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                self._dispatch(data.decode("utf-8", errors="replace"), addr)
            except Exception:
                logger.exception("SIP dispatch error")

    def _dispatch(self, msg: str, addr) -> None:
        if msg.startswith("SIP/2.0"):
            self._handle_response(msg)
        else:
            self._handle_request(msg, addr)

    def _handle_response(self, msg: str) -> None:
        code     = _parse_status_code(msg)
        call_id  = _parse_header(msg, "Call-ID")
        cseq_hdr = _parse_header(msg, "CSeq")
        if not code or not cseq_hdr:
            return
        method = cseq_hdr.split()[-1]

        if method == "REGISTER":
            if code == 401:
                auth_hdr = _parse_header(msg, "WWW-Authenticate")
                if auth_hdr:
                    p = _parse_www_authenticate(auth_hdr)
                    self._reg_realm = p.get("realm")
                    self._reg_nonce = p.get("nonce")
                    self._send_register_with_auth()
            elif code == 200:
                self._set_status(SIPStatus.REGISTERED)
            elif code >= 400:
                logger.error("REGISTER failed: %d", code)
            return

        if not call_id:
            return
        with self._calls_lock:
            call = self._active_calls.get(call_id)
        if not call:
            return

        if method == "INVITE":
            self._handle_invite_response(call, msg, code)
        elif method == "BYE" and code == 200:
            self._finalize_call(call)

    def _handle_invite_response(self, call: SIPCall, msg: str, code: int) -> None:
        to_hdr = _parse_header(msg, "To")
        if to_hdr:
            m = re.search(r"tag=([\w.+%-]+)", to_hdr)
            if m:
                call._remote_tag = m.group(1)

        if code == 100:
            call._set_state(SIPCall.State.CALLING)
        elif code == 180:
            call._set_state(SIPCall.State.RINGING)
        elif code == 200:
            body_start = msg.find(CRLF + CRLF)
            if body_start != -1:
                sdp         = msg[body_start + 4:]
                remote_ip   = _parse_sdp_connection(sdp) or self._server_ip
                remote_port = _parse_sdp_port(sdp)
                if remote_port:
                    call._rtp.set_remote(remote_ip, remote_port)
            self._send_ack(call)
            call._set_state(SIPCall.State.CONNECTED)
        elif code == 401:
            auth_hdr = _parse_header(msg, "WWW-Authenticate")
            if auth_hdr:
                self._resend_invite_with_auth(call, _parse_www_authenticate(auth_hdr))
        elif code >= 400:
            call._set_state(SIPCall.State.FAILED)
            self._cleanup_call(call)

    def _handle_request(self, msg: str, addr) -> None:
        first   = msg.split(CRLF)[0]
        method  = first.split()[0] if first else ""
        call_id = _parse_header(msg, "Call-ID")

        if method == "BYE" and call_id:
            with self._calls_lock:
                call = self._active_calls.get(call_id)
            if call:
                self._send_200_ok_bye(msg, addr)
                call._set_state(SIPCall.State.TERMINATED)
                self._cleanup_call(call)

    def _send_raw(self, msg: str) -> None:
        self._sock.sendto(msg.encode("utf-8"), (self._server_ip, self._server_port))

    def _send_register(self, expires: int = 3600, auth_header: str = "") -> None:
        with self._cseq_lock:
            self._reg_cseq += 1
            cseq = self._reg_cseq
        from_uri = f"sip:{self._username}@{self._domain}"
        contact  = f"sip:{self._username}@{self._local_ip}:{self._local_port}"
        lines = [
            f"REGISTER sip:{self._domain} SIP/2.0",
            f"Via: SIP/2.0/UDP {self._local_ip}:{self._local_port};branch={_random_branch()}",
            f"From: <{from_uri}>;tag={self._reg_tag}",
            f"To: <{from_uri}>",
            f"Call-ID: {self._reg_call_id}",
            f"CSeq: {cseq} REGISTER",
            f"Contact: <{contact}>",
            f"Expires: {expires}",
            "Max-Forwards: 70",
        ]
        if auth_header:
            lines.append(auth_header)
        lines += ["Content-Length: 0", "", ""]
        self._send_raw(CRLF.join(lines))

    def _send_register_with_auth(self) -> None:
        if not (self._reg_realm and self._reg_nonce):
            return
        uri  = f"sip:{self._domain}"
        resp = _digest_response(
            self._username, self._password,
            self._reg_realm, self._reg_nonce,
            "REGISTER", uri,
        )
        auth = (
            f'Authorization: Digest username="{self._username}",'
            f'realm="{self._reg_realm}",'
            f'nonce="{self._reg_nonce}",'
            f'uri="{uri}",'
            f'response="{resp}",'
            f'algorithm=MD5'
        )
        self._send_register(expires=self._register_interval, auth_header=auth)

    def _send_ack(self, call: SIPCall) -> None:
        target_uri = f"sip:{self._domain}"
        from_uri   = f"sip:{self._username}@{self._domain}"
        to_tag     = f";tag={call._remote_tag}" if call._remote_tag else ""
        lines = [
            f"ACK {target_uri} SIP/2.0",
            f"Via: SIP/2.0/UDP {self._local_ip}:{self._local_port};branch={_random_branch()}",
            f"From: <{from_uri}>;tag={call.local_tag}",
            f"To: <{target_uri}>{to_tag}",
            f"Call-ID: {call.call_id}",
            f"CSeq: {call._cseq_invite} ACK",
            "Max-Forwards: 70",
            "Content-Length: 0",
            "", "",
        ]
        self._send_raw(CRLF.join(lines))

    def _send_bye(self, call: SIPCall) -> None:
        target_uri = f"sip:{self._domain}"
        from_uri   = f"sip:{self._username}@{self._domain}"
        to_tag     = f";tag={call._remote_tag}" if call._remote_tag else ""
        with self._cseq_lock:
            cseq = self._cseq
            self._cseq += 1
        lines = [
            f"BYE {target_uri} SIP/2.0",
            f"Via: SIP/2.0/UDP {self._local_ip}:{self._local_port};branch={_random_branch()}",
            f"From: <{from_uri}>;tag={call.local_tag}",
            f"To: <{target_uri}>{to_tag}",
            f"Call-ID: {call.call_id}",
            f"CSeq: {cseq} BYE",
            "Max-Forwards: 70",
            "Content-Length: 0",
            "", "",
        ]
        self._send_raw(CRLF.join(lines))

    def _send_cancel(self, call: SIPCall) -> None:
        target_uri = f"sip:{self._domain}"
        from_uri   = f"sip:{self._username}@{self._domain}"
        lines = [
            f"CANCEL {target_uri} SIP/2.0",
            f"Via: SIP/2.0/UDP {self._local_ip}:{self._local_port};branch={_random_branch()}",
            f"From: <{from_uri}>;tag={call.local_tag}",
            f"To: <{target_uri}>",
            f"Call-ID: {call.call_id}",
            f"CSeq: {call._cseq_invite} CANCEL",
            "Max-Forwards: 70",
            "Content-Length: 0",
            "", "",
        ]
        self._send_raw(CRLF.join(lines))

    def _send_200_ok_bye(self, bye_msg: str, addr) -> None:
        resp = CRLF.join([
            "SIP/2.0 200 OK",
            f"Via: {_parse_header(bye_msg, 'Via')}",
            f"From: {_parse_header(bye_msg, 'From')}",
            f"To: {_parse_header(bye_msg, 'To')}",
            f"Call-ID: {_parse_header(bye_msg, 'Call-ID')}",
            f"CSeq: {_parse_header(bye_msg, 'CSeq')}",
            "Content-Length: 0",
            "", "",
        ])
        self._sock.sendto(resp.encode(), addr)

    def _resend_invite_with_auth(self, call: SIPCall, params: dict) -> None:
        realm      = params.get("realm", "")
        nonce      = params.get("nonce", "")
        target_uri = f"sip:{call.number}@{self._domain}"
        resp       = _digest_response(
            self._username, self._password, realm, nonce, "INVITE", target_uri
        )
        auth = (
            f'Authorization: Digest username="{self._username}",'
            f'realm="{realm}",'
            f'nonce="{nonce}",'
            f'uri="{target_uri}",'
            f'response="{resp}",'
            f'algorithm=MD5'
        )
        with self._cseq_lock:
            cseq = self._cseq
            self._cseq += 1
        call._cseq_invite = cseq
        sdp = _build_sdp(self._local_ip, call._rtp.local_port)
        self._send_raw(self._build_invite(call, target_uri, cseq, sdp, auth_header=auth))

    def _terminate_call(self, call: SIPCall) -> None:
        self._send_bye_or_cancel(call)
        self._cleanup_call(call)

    def _send_bye_or_cancel(self, call: SIPCall) -> None:
        if call.state == SIPCall.State.CONNECTED:
            self._send_bye(call)
        elif call.state in (SIPCall.State.CALLING, SIPCall.State.RINGING):
            self._send_cancel(call)

    def _finalize_call(self, call: SIPCall) -> None:
        call._set_state(SIPCall.State.TERMINATED)
        self._cleanup_call(call)

    def _cleanup_call(self, call: SIPCall) -> None:
        call._rtp.stop()
        with self._calls_lock:
            self._active_calls.pop(call.call_id, None)

    def _register_loop(self) -> None:
        self._set_status(SIPStatus.REGISTERING)
        self._send_register()

        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._register_interval - 10)
            if self._stop_event.is_set():
                break
            if self._status == SIPStatus.REGISTERED:
                logger.debug("SIP re-register")
                self._set_status(SIPStatus.REGISTERING)
                if self._reg_realm and self._reg_nonce:
                    self._send_register_with_auth()
                else:
                    self._send_register()

    def _set_status(self, status: SIPStatus) -> None:
        with self._status_lock:
            self._status = status
        logger.debug("SIP status: %s", status.name)

    def _alloc_rtp_port(self) -> int:
        port = self._next_rtp_port
        self._next_rtp_port += 2
        return port

    @staticmethod
    def _detect_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return "127.0.0.1"
