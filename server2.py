#!/usr/bin/env python3
#
# Author: K. Walsh <kwalsh@cs.holycross.edu>
# Date: 4 April 2017
#
# Server for a simple TCP-like semi-reliable protocol on top of UDP. 
#
# What it does: This version expects the first 8 bytes of each packet to contain
# a sequence number and a magic number. The magic number is completely ignored.
# Every time a packet arrives, an 8-byte ACK is sent back, consisting of the
# magic number 0xAAAAAAAA followed by the sequence number just received. 
# 
# What it doesn't do: There is no real attempt to detect missing packets, send
# NACKs, use cumulative acknowledgements, or do any sort of flow-control. The
# code in datasink.py will keep track of duplicates and rearrange mis-ordered
# packets, so we don't need to worry about that here.
#
# Run the program like this:
#   python3 server.py 1.2.3.4 6000
# This will listen for data on UDP 1.2.3.4:6000. The IP address should be the IP
# for our own host.
# Edited by Kevin Graziosi Nov 2024
#   - Added cumulative acks

import socket
import sys
import time
import struct
import datasink
import trace

# setting verbose = 0 turns off most printing
# setting verbose = 1 turns on a little bit of printing
# setting verbose = 2 turns on a lot of printing
# setting verbose = 3 turns on all printing
verbose = datasink.verbose = 2

# setting tracefile = None disables writing a trace file for the server
# tracefile = None
tracefile = "server_packets.csv"

def main(host, port):
    print("Listening for UDP packets at %s:%d" % (host, port))
    server_addr = ("", port)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # Makes a UDP socket!
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(server_addr)

    trace.init(tracefile,
            "Log of all packets received by server", 
            "SeqNo", "TimeArrived", "NumTimesSeen")
    datasink.init(host)

    last_cum_ack = -1
    out_of_order_packets = {}
    start = time.time()
    while True:
        # wait for a packet, and record the time it arrived
        (packet, client_addr) = s.recvfrom(4000)
        tRecv = time.time()

        # split the packet into header (first 8 bytes) and payload (the rest)
        hdr = packet[0:8]
        payload = packet[8:]

        # unpack integers from the header
        (magic, seqno) = struct.unpack(">II", hdr)


        if verbose >= 2:
            print("Got a packet containing %d bytes from %s" % (len(packet), str(client_addr)))
            print("  packet had magic = 0x%08x and seqno = %d" % (magic, seqno))

        if seqno == last_cum_ack + 1:
            process_packet(seqno, payload, start, tRecv)
            last_cum_ack = seqno
        
            while last_cum_ack + 1 in out_of_order_packets:
                last_cum_ack += 1
                payload = out_of_order_packets.pop(last_cum_ack)
                process_packet(last_cum_ack, payload, start, tRecv)
            
            send_cum_ack(s, client_addr, last_cum_ack)
            
        elif seqno > last_cum_ack + 1:
            out_of_order_packets[seqno] = payload
            if verbose >= 2:
                print(f"  Out of order packet received with seqno {seqno}")

def process_packet(seqno, payload, start, tRecv):
    numTimesSeen = datasink.deliver(seqno, payload)
    if verbose >= 2:
        print(f"Processing packet with seqno {seqno}")
        print(f"Packet has been seen {numTimesSeen} times, including this time")
    trace.write(seqno, tRecv - start, numTimesSeen)

def send_cum_ack(s, client_addr, last_cum_ack):
    if verbose >= 2:
        print(f"Sending cum ack up to seqno {last_cum_ack}")
    ack = bytearray(struct.pack(">II", 0xAAAAAAAA, last_cum_ack))
    s.sendto(ack, client_addr)


if __name__ == "__main__":
    if len(sys.argv) <= 2:
        print("To listen for data on UDP port 6000, try running:")
        print("   python3 server.py server-ip-address 6000")
        sys.exit(0)
    host = sys.argv[1]
    port = int(sys.argv[2])
    main(host, port)
