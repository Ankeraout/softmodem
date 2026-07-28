package fr.ankeraout.softmodem;

import fr.ankeraout.softmodem.sip.SIPCall;
import fr.ankeraout.softmodem.sip.SIPCallState;
import fr.ankeraout.softmodem.sip.SIPClient;
import fr.ankeraout.softmodem.sip.SIPClientState;

public class Main {
	public static void main(String[] args) throws Exception {
		SIPClient client = new SIPClient("user", "pass", "192.168.0.13", 5060, 5060);
		client.start();
		
		while(client.getState() != SIPClientState.REGISTERED) {
			Thread.sleep(1000);
		}
		
		SIPCall call = client.dial("user2");
		
		while(call.getState() == SIPCallState.DIALING || call.getState() == SIPCallState.RINGING) {
			Thread.sleep(1000);
		}
		
		byte[] blankSamples = new byte[160];
		
		while(call.getState() != SIPCallState.TERMINATED) {
			call.writeAudio(blankSamples);
			byte[] samples = call.readAudio(160, 1000);
		}
		
		System.out.println("Terminated");
	}
}
