import argparse
import socket
import sys
import time

from utils import PacketHeader, compute_checksum


def sender(receiver_ip, receiver_port, window_size):
    """Open socket and send message from sys.stdin."""
    # Create UDP socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Set socket timeout for non-blocking receive
    s.settimeout(0.01)
    
    # Read input data
    message = sys.stdin.buffer.read()
    
    # Calculate max payload size (1472 bytes max packet - 16 bytes header)
    max_payload_size = 1456
    
    # Split message into chunks
    chunks = []
    for i in range(0, len(message), max_payload_size):
        chunks.append(message[i:i+max_payload_size])
    
    # Initialize variables for sliding window
    base = 0                     # First unacknowledged packet
    next_seq_num = 0             # Next sequence number to use
    packets = {}                 # Buffer for sent packets {seq_num: packet_data}
    total_packets = len(chunks) + 2  # START + all DATA chunks + END
    timer_start = time.time()    # Timer for retransmissions
    
    # Send START packet (seq_num=0)
    start_header = PacketHeader(type=0, seq_num=0, length=0)
    start_header.checksum = compute_checksum(start_header)
    start_packet = bytes(start_header)
    s.sendto(start_packet, (receiver_ip, receiver_port))
    packets[0] = start_packet
    next_seq_num = 1
    
    # Main loop - continue until all packets are acknowledged
    while base < total_packets:
        # Check for retransmission timeout (500ms)
        current_time = time.time()
        if current_time - timer_start >= 0.5:
            # Retransmit all unacknowledged packets in the current window
            for seq_num in range(base, min(next_seq_num, base + window_size)):
                if seq_num in packets:
                    s.sendto(packets[seq_num], (receiver_ip, receiver_port))
            # Reset timer
            timer_start = current_time
        
        # Send new packets that fit in the window
        while next_seq_num < base + window_size and next_seq_num < total_packets:
            # Special case: END packet
            if next_seq_num == total_packets - 1:
                # Send END packet
                end_header = PacketHeader(type=1, seq_num=next_seq_num, length=0)
                end_header.checksum = compute_checksum(end_header)
                end_packet = bytes(end_header)
                s.sendto(end_packet, (receiver_ip, receiver_port))
                packets[next_seq_num] = end_packet
                next_seq_num += 1
                
                # Special handling when waiting for END acknowledgment
                # When waiting for END acknowledgment
                end_timer_start = time.time()
                while time.time() - end_timer_start < 0.5:
                    try:
                        ack_pkt, _ = s.recvfrom(2048)
                        ack_header = PacketHeader(ack_pkt[:16])
                        
                        if ack_header.type == 3 and ack_header.seq_num == total_packets:
                            base = total_packets
                            break
                    except socket.timeout:
                        # Keep trying until timeout
                        pass
                    except ConnectionResetError:
                        # Handle Windows-specific connection reset
                        pass
            else:
                # Send DATA packet
                chunk_idx = next_seq_num - 1  # Adjust index (seq_num starts at 1 for DATA)
                data_chunk = chunks[chunk_idx]
                data_header = PacketHeader(type=2, seq_num=next_seq_num, length=len(data_chunk))
                data_header.checksum = compute_checksum(data_header / data_chunk)
                data_packet = bytes(data_header / data_chunk)
                s.sendto(data_packet, (receiver_ip, receiver_port))
                packets[next_seq_num] = data_packet
                next_seq_num += 1
        
        # Process incoming ACKs
                # Process incoming ACKs
        try:
            ack_pkt, _ = s.recvfrom(2048)
            ack_header = PacketHeader(ack_pkt[:16])
            
            if ack_header.type == 3:  # ACK
                # Handle cumulative ACK
                if ack_header.seq_num > base:
                    # Remove acknowledged packets from buffer
                    for seq_num in range(base, ack_header.seq_num):
                        if seq_num in packets:
                            del packets[seq_num]
                    
                    # Window has advanced, update base and reset timer
                    base = ack_header.seq_num
                    timer_start = time.time()
        except socket.timeout:
            # No ACK received, continue
            pass
        except ConnectionResetError:
            # Windows-specific error when socket is closed by remote host
            # Just ignore and continue like a timeout
            pass
    
    # Close socket
    s.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "receiver_ip", help="The IP address of the host that receiver is running on"
    )
    parser.add_argument(
        "receiver_port", type=int, help="The port number on which receiver is listening"
    )
    parser.add_argument(
        "window_size", type=int, help="Maximum number of outstanding packets"
    )
    args = parser.parse_args()

    sender(args.receiver_ip, args.receiver_port, args.window_size)


if __name__ == "__main__":
    main()
