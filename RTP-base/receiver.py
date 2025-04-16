import argparse
import socket
import sys

from utils import PacketHeader, compute_checksum


def receiver(receiver_ip, receiver_port, window_size):
    """Listen on socket and print received message to sys.stdout."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((receiver_ip, receiver_port))
    
    # Initialize state
    in_connection = False
    expected_seq_num = 0  # Start with seq_num 0 (for START packet)
    buffer = {}  # Store out-of-order packets: {seq_num: data}
    
    while True:
        # Receive packet
        pkt, address = s.recvfrom(2048)
        
        # Extract header and payload
        pkt_header = PacketHeader(pkt[:16])
        msg = pkt[16:16 + pkt_header.length]
        
        # Verify checksum
        pkt_checksum = pkt_header.checksum
        pkt_header.checksum = 0
        computed_checksum = compute_checksum(pkt_header / msg)
        
        # If checksum doesn't match, drop the packet
        if pkt_checksum != computed_checksum:
            continue
        
        # Handle packet based on its type
        if pkt_header.type == 0:  # START
            if not in_connection:
                in_connection = True
                expected_seq_num = 1  # Next expected is DATA with seq_num 1
                buffer.clear()
                
                # Send ACK for START with seq_num 1
                ack_header = PacketHeader(type=3, seq_num=1, length=0)
                ack_header.checksum = compute_checksum(ack_header)
                s.sendto(bytes(ack_header), address)
            # Ignore START if already in connection
        
        elif pkt_header.type == 1:  # END
            if in_connection:
                # End connection and send ACK
                in_connection = False
                ack_header = PacketHeader(type=3, seq_num=pkt_header.seq_num + 1, length=0)
                ack_header.checksum = compute_checksum(ack_header)
                s.sendto(bytes(ack_header), address)
                
                # Exit program
                break
        
        elif pkt_header.type == 2:  # DATA
            if in_connection:
                # Drop packets outside the window
                if pkt_header.seq_num >= expected_seq_num + window_size:
                    continue
                
                if pkt_header.seq_num == expected_seq_num:
                    # Output the received message
                    sys.stdout.buffer.write(msg)
                    sys.stdout.flush()
                    
                    # Update expected_seq_num
                    expected_seq_num += 1
                    
                    # Process any buffered packets that can now be delivered in order
                    while expected_seq_num in buffer:
                        sys.stdout.buffer.write(buffer[expected_seq_num])
                        sys.stdout.flush()
                        del buffer[expected_seq_num]
                        expected_seq_num += 1
                    
                    # Send cumulative ACK with next expected seq_num
                    ack_header = PacketHeader(type=3, seq_num=expected_seq_num, length=0)
                    ack_header.checksum = compute_checksum(ack_header)
                    s.sendto(bytes(ack_header), address)
                
                elif pkt_header.seq_num > expected_seq_num:
                    # Buffer out-of-order packet
                    buffer[pkt_header.seq_num] = msg
                    
                    # Send ACK with expected seq_num (cumulative ACK)
                    ack_header = PacketHeader(type=3, seq_num=expected_seq_num, length=0)
                    ack_header.checksum = compute_checksum(ack_header)
                    s.sendto(bytes(ack_header), address)
                
                else:  # pkt_header.seq_num < expected_seq_num
                    # This is a duplicate packet, send cumulative ACK
                    ack_header = PacketHeader(type=3, seq_num=expected_seq_num, length=0)
                    ack_header.checksum = compute_checksum(ack_header)
                    s.sendto(bytes(ack_header), address)


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

    receiver(args.receiver_ip, args.receiver_port, args.window_size)


if __name__ == "__main__":
    main()
