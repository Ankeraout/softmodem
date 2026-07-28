package fr.ankeraout.softmodem.sip;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SIPClient {
	private static final int SOCKET_TIMEOUT = 1000;
	private static final int TAG_LENGTH = 8;
	private static final int RTP_BUFFER_SIZE = 160;
	private static final int PTIME_MS = 20;
	private static final int REGISTER_INTERVAL = 60000;
	private static final int MAX_MESSAGE_SIZE = 1024;
	
	private SIPClientState state;
	private String username;
	private String password;
	private String domain;
	private int serverPort;
	private int localPort;
	private String localIP;
	private DatagramSocket socket;
	private int registerCseq;
	private String registerTag;
	private String registerCallID;
	private Thread registerThread;
	private Thread receiveThread;
	private int nextRtpPort;
	private int cseq;
	private HashMap<String, SIPCall> calls;
	private String registerNonce;
	private String registerRealm;
	private String serverIP;
	
	public SIPClient(String username, String password, String domain, int serverPort, int localPort) throws SocketException {
		this.username = username;
		this.password = password;
		this.domain = domain;
		this.serverIP = domain;
		this.serverPort = serverPort;
		this.localPort = localPort;
		this.localIP = SIPClient.getLocalIP();
		this.nextRtpPort = 10000;
		this.cseq = 0;
		this.registerCseq = 0;
		this.calls = new HashMap<String, SIPCall>();
		this.state = SIPClientState.STOPPED;
	}
	
	public SIPClientState getState() {
		return this.state;
	}
	
	public void start() throws Exception {
		synchronized(this) {
			if(this.state != SIPClientState.STOPPED) {
				throw new Exception("The client is already started.");
			}
			
			this.socket = new DatagramSocket(this.localPort);
			this.socket.connect(new InetSocketAddress(this.domain, this.serverPort));
			this.socket.setSoTimeout(SOCKET_TIMEOUT);
			
			this.registerCseq = 0;
			this.registerTag = SIPClient.generateTag();
			this.registerCallID = this.generateCallID();
			this.state = SIPClientState.STARTING;
			
			this.receiveThread = new Thread(this::receiveThreadMain, "SIP receive thread");
			this.registerThread = new Thread(this::registerThreadMain, "SIP register thread");
			this.receiveThread.start();
			this.registerThread.start();
		}
	}
	
	public void stop() throws Exception {
		synchronized(this) {
			if((this.state != SIPClientState.REGISTERING) && (this.state != SIPClientState.REGISTERED)) {
				throw new Exception("The client is not started.");
			}
			
			this.state = SIPClientState.STOPPING;
		}
		
		this.registerThread.join();
		this.receiveThread.join();
		
		synchronized(this) {
			this.state = SIPClientState.STOPPED;
		}
	}
	
	public SIPCall dial(String number) throws Exception {
		synchronized(this) {
			if(this.state != SIPClientState.REGISTERED) {
				throw new Exception("SIP client is not registered.");
			}
			
			RTPSession rtpSession = new RTPSession(this.localIP, this.allocateRtpPort(), SIPClient.RTP_BUFFER_SIZE);
			rtpSession.start();
			
			String callID = this.generateCallID();
			String tag = SIPClient.generateTag();
			SIPCall call = new SIPCall(callID, tag, rtpSession, number);
			
			int cseq = this.registerCseq + 1;
			
			call.setCseqInvite(cseq);
			this.calls.put(callID, call);
			
			call.addHangupListener(() -> this.terminateCall(call));
			
			this.sendInvite(call, number, cseq);
			
			return call;
		}
	}
	
	private int allocateRtpPort() {
		int port;
		
		synchronized(this) {
			port = this.nextRtpPort;
			this.nextRtpPort += 2;
		}
		
		return port;
	}
	
	private void terminateCall(SIPCall call) {
		try {
			this.sendByeOrCancel(call);
		} catch(IOException e) {
			
		}
		
		this.cleanupCall(call);
	}
	
	private void sendByeOrCancel(SIPCall call) throws IOException {
		String uri = "sip:" + this.domain;
		String from_uri = String.format("sip:%s@%s", this.username, this.domain);
		int cseq;
		
		synchronized(this) {
			cseq = this.cseq++;
		}
		
		List<String> lines = new LinkedList<String>();
		
		if(call.getState() == SIPCallState.CONNECTED) {
			lines.add(String.format("BYE %s SIP/2.0", uri));
			
			String to = String.format("To: <%s>", uri);
			
			if(call.getRemoteTag() != null) {
				to += ";tag=" + call.getRemoteTag();
			}
			
			lines.add(to);
		} else if((call.getState() == SIPCallState.DIALING) || (call.getState() == SIPCallState.RINGING)) {
			lines.add(String.format("CANCEL %s SIP/2.0", uri));
			lines.add(String.format("To: <%s>", uri));
			lines.add(String.format("CSeq: %d CANCEL", cseq));
		}
		
		lines.add(String.format("Via: SIP/2.0/UDP %s:%d;branch=%s", this.localIP, this.localPort, SIPClient.generateBranch()));
		lines.add(String.format("From: <%s>;tag=%s", from_uri, call.getTag()));
		lines.add("Call-ID: " + call.getCallID());
		lines.add("Max-Forwards: 70");
		lines.add("Content-Length: 0");
		lines.add("");
		lines.add("");
		
		byte[] data = String.join("\r\n", lines).getBytes();
		DatagramPacket packet = new DatagramPacket(data, data.length);
		this.socket.send(packet);
	}
	
	private void cleanupCall(SIPCall call) {
		call.getRtpSession().stop();
		
		synchronized(this) {
			this.calls.remove(call.getCallID());
		}
	}
	
	private String buildSdp(int rtpPort) {
		return String.join(
			"\r\n",
			new String[]{
				"v=0",
				"o=sip_client 0 0 IN IP4 " + this.localIP,
				"s=SIP Call",
				"c=IN IP4 " + this.localIP,
				"t=0 0",
				"m=audio " + rtpPort + " RTP/AVP 0",
				"a=rtpmap:0 PCMU/8000",
				"a=ptime:" + SIPClient.PTIME_MS,
				"a=sendrecv",
				""
			}
		);
	}
	
	private String buildInvite(SIPCall call, String uri, int cseq, String sdp, String authHeader) {
		byte[] sdpBytes = sdp.getBytes();
		
		List<String> lines = new ArrayList<String>(
			Arrays.asList(
				new String[] {
					"INVITE " + uri + " SIP/2.0",
					"Via: SIP/2.0/UDP " + this.localIP + ":" + this.localPort + ";branch=" + SIPClient.generateBranch(),
					"From: <sip:" + this.username + "@" + this.domain + ">;tag=" + call.getTag(),
					"To: <" + uri + ">",
					"Call-ID: " + call.getCallID(),
					"CSeq: " + cseq + " INVITE",
					"Contact: <sip:" + this.username + "@" + this.localIP + ":" + this.localPort + ">",
					"Max-Forwards: 70",
					"Content-Type: application/sdp",
					"Content-Length: " + sdpBytes.length
				}
			)
		);
		
		if(authHeader != null) {
			lines.add(authHeader);
		}
		
		lines.add("");
		lines.add(sdp);
		
		return String.join("\r\n", lines);
	}
	
	private void handleResponse(String message) throws NoSuchAlgorithmException, IOException {
		String cseq = SIPClient.parseHeader(message, "CSeq");
		
		if(cseq == null) {
			return;
		}
		
		String[] split = cseq.split(" ");
		
		System.out.println(message);
		
		switch(split[split.length - 1]) {
		case "REGISTER":
			this.handleResponseRegister(message);
			break;
			
		case "INVITE":
			this.handleResponseInvite(message);
			break;

		case "BYE":
			this.handleResponseBye(message);
			break;
		}
	}
	
	private void handleResponseRegister(String message) throws NoSuchAlgorithmException, IOException {
		Integer code = SIPClient.parseStatusCode(message);
		
		if(code == null) {
			return;
		}
		
		switch(code) {
		case 401:
			Map<String, String> data = SIPClient.parseWwwAuthenticate(
				SIPClient.parseHeader(message, "WWW-Authenticate")
			);
			this.registerRealm = data.get("realm");
			this.registerNonce = data.get("nonce");
			this.sendRegister();
			
		case 200:
			synchronized(this) {
				this.state = SIPClientState.REGISTERED;
			}
		}
	}
	
	private void handleResponseInvite(String message) throws IOException, NoSuchAlgorithmException {
		Integer code = SIPClient.parseStatusCode(message);
		String toHeader = SIPClient.parseHeader(message, "To");
		String callID = SIPClient.parseHeader(message, "Call-ID");
		
		if(code == null || callID == null) {
			return;
		}
		
		SIPCall call;
		
		synchronized(this) {
			call = this.calls.get(callID);
		}
		
		if(call == null) {
			return;
		}
		
		if(toHeader != null) {
			Matcher matcher = Pattern.compile("tag=([\\w.+%-]+)").matcher(toHeader);
			
			if(matcher.find()) {
				call.setRemoteTag(matcher.group(1));
			}
		}
		
		switch(code) {
		case 100:
			call.setState(SIPCallState.DIALING);
			break;
			
		case 180:
			call.setState(SIPCallState.RINGING);
			break;
			
		case 200:
			int bodyStart = message.indexOf("\r\n\r\n") + 4;
			
			if(bodyStart == -1) {
				return;
			}
			
			String sdp = message.substring(bodyStart);
			Matcher remotePortMatcher = Pattern.compile("m=audio\\s+(\\d+)").matcher(sdp);

			if(!remotePortMatcher.find()) {
				return;
			}
			
			String remotePort = remotePortMatcher.group(1);
			Matcher remoteIPMatcher = Pattern.compile("c=IN IP4 ([^\\s\\r\\n]+)").matcher(sdp);
			String remoteIP;
			
			if(remoteIPMatcher.find()) {
				remoteIP = remoteIPMatcher.group(1);
			} else {
				remoteIP = this.serverIP;
			}
			
			call.getRtpSession().setRemote(remoteIP, Integer.parseInt(remotePort));
			System.out.println("Remote set");
			
			String uri = "sip:" + call.getNumber() + "@" + this.domain;
			String to = "To: <" + uri + ">";
			
			if(call.getRemoteTag() != null) {
				to += ";tag=" + call.getRemoteTag();
			}
			
			String contactHeader = SIPClient.parseHeader(message, "Contact");
			
			byte[] response = String.join(
				"\r\n",
				new String[] {
					"ACK " + contactHeader.substring(1, contactHeader.length() - 1) + " SIP/2.0",
					"Via: SIP/2.0/UDP " + this.localIP + ":" + this.localPort + ";branch=" + SIPClient.generateBranch(),
					"From: <sip:" + this.username + "@" + this.domain + ">;tag=" + call.getTag(),
					to,
					"Call-ID: " + callID,
					"CSeq: " + call.getCseqInvite() + " ACK",
					"Max-Forwards: 70",
					"Content-Length: 0",
					"",
					""
				}
			).getBytes();
			
			DatagramPacket packet = new DatagramPacket(response, response.length);
			this.socket.send(packet);
			System.out.println("Response sent");
			call.setState(SIPCallState.CONNECTED);
			break;
		
		case 401:
			String authHeader = SIPClient.parseHeader(message, "WWW-Authenticate");
			
			if(authHeader != null) {
				this.resendInviteWithAuth(call, SIPClient.parseWwwAuthenticate(authHeader));
			}
			
			break;
			
		default:
			if(code >= 400) {
				call.setState(SIPCallState.TERMINATED);
				this.cleanupCall(call);
			}
			
			break;
		}
	}
	
	private void resendInviteWithAuth(SIPCall call, Map<String, String> parameters) throws NoSuchAlgorithmException, IOException {
		String realm = parameters.getOrDefault("realm", "");
		String nonce = parameters.getOrDefault("nonce", "");
		String uri = "sip:" + call.getNumber() + "@" + this.domain;
		String response = this.getDigestResponse(realm, nonce, "INVITE", uri);
		
		String authHeader = String.format(
			"Authorization: Digest username=\"%s\",realm=\"%s\",nonce=\"%s\",uri=\"%s\",response=\"%s\",algorithm=MD5",
			this.username,
			realm,
			nonce,
			uri,
			response
		);
		
		int cseq;
		
		synchronized(this) {
			cseq = this.cseq++;
		}
		
		call.setCseqInvite(cseq);
		String sdp = this.buildSdp(call.getRtpSession().getLocalPort());
		byte[] data = this.buildInvite(call, uri, cseq, sdp, authHeader).getBytes();
		DatagramPacket packet = new DatagramPacket(data, data.length);
		
		this.socket.send(packet);
	}
	
	private void handleResponseBye(String message) {
		Integer code = SIPClient.parseStatusCode(message);
		
		if(code == null) {
			return;
		}
		
		String callID = SIPClient.parseHeader(message, "Call-ID");
		
		if(callID == null) {
			return;
		}
		
		SIPCall call;
		
		synchronized(this) {
			call = this.calls.get(callID);
		}
		
		if(call == null) {
			return;
		}
		
		call.setState(SIPCallState.TERMINATED);
		this.cleanupCall(call);
	}
	
	private void handleRequest(String message) throws IOException {
		String firstLine = message.split("\r\n")[0];
		String method = firstLine.split("\\s")[0];
		
		if(!method.equals("BYE")) {
			return;
		}
		
		String callID = SIPClient.parseHeader(message, "Call-ID");
		
		if(callID == null) {
			return;
		}
		
		SIPCall call;
		
		synchronized(this) {
			call = this.calls.get(callID);
		}
		
		if(call == null) {
			return;
		}
		
		byte[] data = String.join(
			"\r\n",
			new String[] {
				"SIP/2.0 200 OK",
				"Via: " + SIPClient.parseHeader(message, "Via"),
				"From: " + SIPClient.parseHeader(message, "From"),
				"To:" + SIPClient.parseHeader(message, "To"),
				"Call-ID: " + callID,
				"CSeq: " + SIPClient.parseHeader(message, "CSeq"),
				"Content-Length: 0",
				"",
				""
			}
		).getBytes();
		
		DatagramPacket packet = new DatagramPacket(data, data.length);
		this.socket.send(packet);
		
		call.setState(SIPCallState.TERMINATED);
		this.cleanupCall(call);
	}
	
	private void sendRegister() throws NoSuchAlgorithmException, IOException {
		int cseq;
		
		synchronized(this) {
			this.registerCseq++;
			cseq = this.registerCseq;
		}
		
		String fromUri = "sip:" + this.username + "@" + this.domain;
		List<String> lines = new ArrayList<String>(
			Arrays.asList(
				new String[] {
					"REGISTER sip:" + this.domain + " SIP/2.0",
					"Via: SIP/2.0/UDP " + this.localIP + ":" + this.localPort + ";branch=" + SIPClient.generateBranch(),
					"From: <" + fromUri + ">;tag=" + this.registerTag,
					"To: <" + fromUri + ">",
					"Call-ID: " + this.registerCallID,
					"CSeq: " + cseq + " REGISTER",
					"Contact: <sip:" + this.username + "@" + this.localIP + ":" + this.localPort + ">",
					"Expires: 300",
					"Max-Forwards: 70",
					"Content-Length: 0"
				}
			)
		);
		
		if(this.registerNonce != null && this.registerRealm != null) {
			String uri = "sip:" + this.domain;
			String response = this.getDigestResponse(this.registerRealm, this.registerNonce, "REGISTER", uri);
			String[] parts = new String[] {
				"Authorization: Digest username=\"" + this.username + "\"",
				"realm=\"" + this.registerRealm + "\"",
				"nonce=\"" + this.registerNonce + "\"",
				"uri=\"" + uri + "\"",
				"response=\"" + response + "\"",
				"algorithm=MD5"
			};
			
			lines.add(String.join(",", parts));
		}
		
		lines.add("");
		lines.add("");
		byte[] data = String.join("\r\n", lines).getBytes();
		
		DatagramPacket packet = new DatagramPacket(data, data.length);
		this.socket.send(packet);
	}
	
	private void sendInvite(SIPCall call, String number, int cseq) throws IOException {
		byte[] data = this.buildInvite(
			call,
			"sip:" + number + "@" + this.domain,
			cseq,
			this.buildSdp(call.getRtpSession().getLocalPort()),
			null
		).getBytes();
		
		DatagramPacket packet = new DatagramPacket(data, data.length);
		this.socket.send(packet);
	}
	
	private void registerThreadMain() {
		long lastRegisterTime = System.currentTimeMillis() - SIPClient.REGISTER_INTERVAL;
		
		this.state = SIPClientState.REGISTERING;
		
		while(this.state != SIPClientState.STOPPING) {
			long currentTime = System.currentTimeMillis();
			
			if(currentTime - lastRegisterTime >= SIPClient.REGISTER_INTERVAL) {
				try {
					this.sendRegister();
				} catch (NoSuchAlgorithmException e) {
					e.printStackTrace();
					return;
				} catch (IOException e) {
					e.printStackTrace();
					return;
				}
				
				lastRegisterTime = currentTime;
			} else {
				try {
					Thread.sleep(SIPClient.SOCKET_TIMEOUT);
				} catch (InterruptedException e) {
					// Nothing to do.
				}
			}
		}
	}
	
	private void receiveThreadMain() {
		while(this.state != SIPClientState.STOPPING) {
			DatagramPacket packet = new DatagramPacket(new byte[SIPClient.MAX_MESSAGE_SIZE], SIPClient.MAX_MESSAGE_SIZE);
			
			try {
				this.socket.receive(packet);
			} catch(SocketTimeoutException e) {
				// Do nothing
				continue;
			} catch (IOException e) {
				break;
			}
			
			String message;
			
			try {
				message = new String(packet.getData(), 0, packet.getLength(), StandardCharsets.UTF_8);
			} catch(Exception e) {
				// Invalid packet, ignore it.
				continue;
			}
			
			if(message.startsWith("SIP/2.0")) {
				try {
					this.handleResponse(message);
				} catch(Exception e) {
					// Invalid packet, ignore it.
				}
			} else {
				try {
					this.handleRequest(message);
				} catch(Exception e) {
					// Invalid packet, ignore it.
				}
			}
		}
	}
	
	private String getDigestResponse(String realm, String nonce, String method, String uri) throws NoSuchAlgorithmException {
		String ha1 = SIPClient.getMd5Checksum(
			String.format("%s:%s:%s", this.username, realm, this.password)
		);
		String ha2 = SIPClient.getMd5Checksum(String.format("%s:%s", method, uri));
		return SIPClient.getMd5Checksum(String.format("%s:%s:%s", ha1, nonce, ha2));
	}
	
	private String generateCallID() {
		return SIPClient.generateRandomHexString(16) + "@" + this.domain;
	}
	
	private static String parseHeader(String message, String header) {
		Matcher matcher = Pattern.compile("^" + header + "\\s*:\\s*(.+)\\r?$", Pattern.CASE_INSENSITIVE | Pattern.MULTILINE).matcher(message);
		return matcher.find() ? matcher.group(1).strip() : null;
	}
	
	private static Integer parseStatusCode(String message) {
		Matcher matcher = Pattern.compile("SIP/2\\.0\\s+(\\d{3})").matcher(message);
		return matcher.find() ? Integer.parseInt(matcher.group(1)) : null;
	}
	
	private static Map<String, String> parseWwwAuthenticate(String headerValue) {
		Map<String, String> result = new HashMap<String, String>();
		final String[] keyList = new String[] {
			"realm",
			"nonce",
			"qop",
			"algorithm"
		};
		
		for(String key : keyList) {
			Matcher matcher = Pattern.compile(key + "=\"?([^\",\\s]+)\"?", Pattern.CASE_INSENSITIVE).matcher(headerValue);
			
			if(matcher.find()) {
				result.put(key, matcher.group(1));
			}
		}
		
		return result;
	}
	
	private static String generateRandomHexString(int n) {
		byte[] data = new byte[n / 2 + (n % 2 == 0 ? 0 : 1)];
		new Random().nextBytes(data);
		return SIPClient.byteArrayToHex(data).substring(0, n);
	}
	
	private static String generateTag() {
		return SIPClient.generateRandomHexString(SIPClient.TAG_LENGTH);
	}
	
	private static String generateBranch() {
		return "z9hG4bK" + SIPClient.generateRandomHexString(16);
	}
	
	private static String getLocalIP() throws SocketException {
		DatagramSocket socket = new DatagramSocket();
		socket.connect(new InetSocketAddress("8.8.8.8", 80));
		String address = socket.getLocalAddress().getHostAddress();
		socket.close();
		return address;
	}
	
	private static String byteArrayToHex(byte[] data) {
		StringBuilder sb = new StringBuilder();
		
		for(byte b : data) {
			sb.append(String.format("%02x", b & 0xff));
		}
		
		return sb.toString();
	}
	
	private static String getMd5Checksum(String str) throws NoSuchAlgorithmException {
		MessageDigest digest = MessageDigest.getInstance("MD5");
		digest.update(str.getBytes());
		return SIPClient.byteArrayToHex(digest.digest());
	}
}
