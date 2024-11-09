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
# NACKs, or do any sort of flow-control. The
# code in datasink.py will keep track of duplicates and rearrange mis-ordered
# packets, so we don't need to worry about that here.
#
# Run the program like this:
#   python3 server.py 1.2.3.4 6000
# This will listen for data on UDP 1.2.3.4:6000. The IP address should be the IP
# for our own host.
# Edited by Kevin Graziosi Nov 2024
# -Added cumulative acks

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

    last_acked_seqno = -1
    expected_seqno = 0

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

        if seqno > last_acked_seqno + 1:
            if verbose >= 2:
                print(f"Received out-of-order packet: expected seqno {last_acked_seqno + 1}, got {seqno}.")
            ack = bytearray(struct.pack(">II", 0xAAAAAAAA, last_acked_seqno))
            s.sendto(ack, client_addr)
            continue
        else:
            # give the packet to the consumer
            numTimesSeen = datasink.deliver(seqno, payload)

            if verbose >= 2:
                print("Got a packet containing %d bytes from %s" % (len(packet), str(client_addr)))
                print("  packet had magic = 0x%08x and seqno = %d" % (magic, seqno))
                print("  packet has been seen %d times, including this time" % (numTimesSeen))

            # write info about the packet to the log file
            trace.write(seqno, tRecv - start, numTimesSeen)

        last_acked_seqno = seqno

        # create and send an ACK
        if verbose >= 2:
            print("  sending ACK in reply containing seqno = %d" % (last_acked_seqno))
        ack = bytearray(struct.pack(">II", 0xAAAAAAAA, last_acked_seqno))
        s.sendto(ack, client_addr)


if __name__ == "__main__":
    if len(sys.argv) <= 2:
        print("To listen for data on UDP port 6000, try running:")
        print("   python3 server.py server-ip-address 6000")
        sys.exit(0)
    host = sys.argv[1]
    port = int(sys.argv[2])
    main(host, port)
