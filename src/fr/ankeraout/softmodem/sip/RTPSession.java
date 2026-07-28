package fr.ankeraout.softmodem.sip;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.util.Random;

public class RTPSession {
	private final static int RTP_HEADER_SIZE = 12;
	
	private String localIP;
	private int localPort;
	private String remoteIP;
	private int remotePort;
	private int seq;
	private int ts;
	private int ssrc;
	private AudioBuffer buffer;
	private DatagramSocket socket;
	private boolean running;
	private Thread receiveThread;
	private boolean suspendReceive;
	
	public RTPSession(String localIP, int localPort, int bufferSize) {
		this.localIP = localIP;
		this.localPort = localPort;
		this.remoteIP = null;
		this.remotePort = 0;
		
		Random random = new Random();
		
		this.seq = random.nextInt(0x10000);
		this.ts = random.nextInt();
		this.ssrc = random.nextInt();
		
		this.buffer = new AudioBuffer();
		this.socket = null;
		this.running = false;
		this.receiveThread = null;
		this.suspendReceive = false;
	}
	
	public void start() throws SocketException {
		this.socket = new DatagramSocket(new InetSocketAddress(this.localIP, this.localPort));
		this.socket.setSoTimeout(1000);
		this.running = true;
		this.receiveThread = new Thread(this::receiveThreadMain, "RTP receive thread");
		this.receiveThread.start();
	}
	
	public void stop() {
		this.running = false;
		
		if(this.receiveThread != null) {
			try {
				this.receiveThread.join();
			} catch (InterruptedException e) {
				// Will never happen
			}
		}
		
		if(this.socket != null) {
			this.socket.close();
			this.socket = null;
		}
	}
	
	public void sendPacket(byte[] data) throws IOException {
		synchronized(this) {
			if(this.remoteIP == null || this.remotePort == 0 || this.socket == null) {
				return;
			}
			
			byte[] header = this.buildHeader();
			this.seq = (this.seq + 1) & 0xffff;
			this.ts = (this.ts + data.length) & 0xffffffff;
			
			byte[] packetData = new byte[data.length + RTPSession.RTP_HEADER_SIZE];
			System.arraycopy(header, 0, packetData, 0, RTPSession.RTP_HEADER_SIZE);
			System.arraycopy(data, 0, packetData, RTPSession.RTP_HEADER_SIZE, data.length);
			
			this.socket.send(new DatagramPacket(packetData, packetData.length));
		}
	}
	
	public int getLocalPort() {
		return this.localPort;
	}
	
	public void setRemote(String ip, int port) throws SocketException {
		this.remoteIP = ip;
		this.remotePort = port;
		
		if(this.socket != null) {
			this.suspendReceive = true;
			this.socket.connect(new InetSocketAddress(ip, port));
			this.suspendReceive = false;
		}
	}
	
	public AudioBuffer getBuffer() {
		return this.buffer;
	}
	
	private void receiveThreadMain() {
		byte[] data = new byte[4096];
		DatagramPacket packet = new DatagramPacket(data, data.length);
		
		while(this.running) {
			if(this.suspendReceive) {
				try {
					Thread.sleep(100);
				} catch (InterruptedException e) {
					// Will not happen
				}
				
				continue;
			}
			
			try {
				packet.setLength(data.length);
				this.socket.receive(packet);
			} catch(SocketTimeoutException e) {
				// Nothing to do
				continue;
			} catch(IOException e) {
				break;
			}
			
			if(packet.getLength() < RTPSession.RTP_HEADER_SIZE) {
				// Ignore the invalid packet
				continue;
			}
			
			this.buffer.write(data, RTPSession.RTP_HEADER_SIZE, packet.getLength() - RTP_HEADER_SIZE);
		}
	}
	
	private byte[] buildHeader() {
		byte[] buffer = new byte[RTP_HEADER_SIZE];
		
		buffer[0] = (byte)0x80;
		buffer[1] = 0x00;
		buffer[2] = (byte)(this.seq >> 8);
		buffer[3] = (byte)this.seq;
		buffer[4] = (byte)(this.ts >> 24);
		buffer[5] = (byte)(this.ts >> 16);
		buffer[6] = (byte)(this.ts >> 8);
		buffer[7] = (byte)this.ts;
		buffer[8] = (byte)(this.ssrc >> 24);
		buffer[9] = (byte)(this.ssrc >> 16);
		buffer[10] = (byte)(this.ssrc >> 8);
		buffer[11] = (byte)this.ssrc;
		
		return buffer;
	}
}
