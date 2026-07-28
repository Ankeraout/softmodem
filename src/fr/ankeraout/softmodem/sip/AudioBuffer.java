package fr.ankeraout.softmodem.sip;

import java.util.ArrayDeque;
import java.util.Queue;

public class AudioBuffer {
	private Queue<Byte> buffer;
	
	public AudioBuffer() {
		this.buffer = new ArrayDeque<Byte>();
	}
	
	public void write(byte[] data, int offset, int length) {
		synchronized(this) {
			for(int i = offset; i < offset + length; i++) {
				this.buffer.add(data[i]);
			}
			
			this.notifyAll();
		}
	}
	
	public void write(byte[] data) {
		this.write(data, 0, data.length);
	}
	
	public byte[] read(int n, int timeoutMs) {
		long deadline = System.currentTimeMillis() + timeoutMs;
		byte[] data;
		
		synchronized(this) {		
			while(this.buffer.size() < n) {
				long remaining = deadline - System.currentTimeMillis();
				
				if(remaining <= 0) {
					break;
				}
				
				try {
					this.wait(timeoutMs);
				} catch (InterruptedException e) {
					// Nothing to do
				}
			}
			
			int length = Math.min(n, this.buffer.size());
			data = new byte[length];
			
			for(int i = 0; i < length; i++) {
				data[i] = this.buffer.poll();
			}
		}
		
		return data;
	}
}
