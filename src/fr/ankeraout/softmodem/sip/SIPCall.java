package fr.ankeraout.softmodem.sip;

import java.io.IOException;
import java.util.HashSet;

public class SIPCall {
	private String callID;
	private String tag;
	private RTPSession rtpSession;
	private String number;
	private HashSet<HangupListener> hangupListeners;
	private String remoteTag;
	private SIPCallState state;
	private int cseqInvite;
	
	public SIPCall(String callID, String tag, RTPSession rtpSession, String number) {
		this.callID = callID;
		this.tag = tag;
		this.rtpSession = rtpSession;
		this.number = number;
		
		this.state = SIPCallState.DIALING;
		this.cseqInvite = 0;
		this.remoteTag = null;
		
		this.hangupListeners = new HashSet<SIPCall.HangupListener>();
	}
	
	public void writeAudio(byte[] data) throws IOException {
		this.rtpSession.sendPacket(data);
	}
	
	public byte[] readAudio(int n, int timeoutMs) {
		synchronized(this) {
			if(this.state == SIPCallState.CONNECTED) {
				return this.rtpSession.getBuffer().read(n, timeoutMs);
			} else {
				return new byte[0];
			}
		}
	}
	
	public void hangup() {
		synchronized(this) {
			if(this.state != SIPCallState.TERMINATED) {			
				this.hangupListeners.forEach((listener) -> listener.onHangup());
				this.state = SIPCallState.TERMINATED;
			}
		}
	}
	
	public void setCseqInvite(int cseq) {
		this.cseqInvite = cseq;
	}
	
	public void addHangupListener(HangupListener listener) {
		this.hangupListeners.add(listener);
	}
	
	public SIPCallState getState() {
		return this.state;
	}
	
	public String getRemoteTag() {
		return this.remoteTag;
	}
	
	public String getTag() {
		return this.tag;
	}
	
	public String getCallID() {
		return this.callID;
	}

	public RTPSession getRtpSession() {
		return this.rtpSession;
	}
	
	public void setRemoteTag(String remoteTag) {
		this.remoteTag = remoteTag;
	}
	
	public void setState(SIPCallState state) {
		synchronized(this) {
			this.state = state;
		}
	}
	
	public String getNumber() {
		return this.number;
	}
	
	public int getCseqInvite() {
		return this.cseqInvite;
	}
	
	public static interface HangupListener {
		public void onHangup();
	}
}
