#!/usr/bin/env python3
#
# Author: K. Walsh <kwalsh@cs.holycross.edu>
# Date: 4 April 2017
# Modified: 20 October 2023
#
# Pipelined client for a simple and slightly-reliable protocol on top of UDP. 
#
# What it does: This version implements a simple pipelined (or "window-based")
# protocol. It sends N UDP packets, waits for an ACK, sends one more, waits for
# an ACK, etc.
#   state 0. Client waits for data to be available to send. If none, then exit.
#   state 1. Client sends one UDP packet. The server will respond with an ACK.
#            If there are fewer than N packets outstanding, go to state 0, else
#            go to state 2.
#   state 2. Client waits for ACK with oldest outstanding seqno. If it
#            arrives within T seconds, then go back to state 0. If
#            the wrong ACK arrives, discard it and go to state 2. If a timeout
#            occurs, go to state 3.
#   state 3. Resend all outstanding packets, then go to state 2.
# A 4-byte sequence number is included in each packet, so the server can detect
# duplicates, detect missing packets, and sort any mis-ordered packets back into
# the correct order. A 4-byte "magic" integer (0xBAADCAFE) is also included with
# each packet, for no reason at all (you can replace it with something else, or
# remove it entirely).
#
# What it doesn't do: There are no NACKs, and this makes only a little effort to
# match up ACKs numbers with corresponding data packets. Any ACKs that arrive
# out of order are ignored, and when timeouts occur, it assumes all recent
# packets have been lost and it retransmits all of them.
#
# Run the program like this:
#   python client_pipelined.py 1.2.3.4 6000 50 0.030
# This will send data to a server at IP address 1.2.3.4 port 6000, using
# pipeline with N=100 outstanding packets and 0.030 second (30 ms) timeout.
# Edited by Kevin Graziosi Nov 2024
# -Changed it so cumulative acks work

import socket
import sys
import time
import struct
import datasource
import trace

# setting verbose = 0 turns off most printing
# setting verbose = 1 turns on a little bit of printing
# setting verbose = 2 turns on a lot of printing
# setting verbose = 3 turns on all printing
verbose = 3

tracefile = "client_pipelined_packets.csv"
# tracefile = None # This will disable writing a trace file for the client

def main(host, port, n, t):
    print("Sending UDP packets to %s:%d using N=%d pipelining and timeout T=%f seconds" % (host, port, n, t))
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # Makes a UDP socket!
    
    trace.init(tracefile,
            "Log of all packets sent and ACKs received by client", 
            "SeqNo", "TimeSent", "AckNo", "timeACKed")

    start = time.time()

    magic = 0xBAADCAFE # a value to be included in every data packet
    seqno = 0 # sequence number for the next data packet to be sent
    desired_ackno = 0 # ACK number that we must next wait for
    hdr = None # header for the next data packet to be sent
    body = None # data to be sent in the next data packet to be sent
    have_more_data = True # keep track of whether we have more data to send
    outstanding = { } # a dictionary containing outstanding packets
    state = 0 # the current state for our protocol

    # keep going if there more data OR some data is not yet acknowledged
    while have_more_data or len(outstanding) > 0:
        if state == 0: #  wait for data to be available to send
            body = datasource.wait_for_data(seqno)
            if body == None:
                have_more_data = False
                state = 2 # no more data, so now just wait for ACKs
            else:
                state = 1 # go to state 1, to send the next packet
        
        elif state == 1: # send one data packet
            # make a header, create a packet, and send it
            hdr = bytearray(struct.pack(">II", magic, seqno))
            pkt = hdr + body
            tSend = time.time()
            s.sendto(pkt, (host, port))

            # print stuff
            if verbose >= 3 or (verbose >= 1 and seqno < 5 or seqno % 1000 == 0):
                print("Sent packet with seqno %d" % (seqno))

            # write info about the packet (but without the ACK) to the log file
            trace.write(seqno, tSend - start, 0, 0)

            # record this packet in the outstanding set
            outstanding[seqno] = pkt

            # prepare for the next packet
            seqno += 1

            if len(outstanding) >= n: state = 2 # go to state 2
            else: state = 0 # go back to state 0

        elif state == 2: # Wait for the desired ACK

            s.settimeout(t)
            try:
                (ack, addr) = s.recvfrom(100)
                tRecv = time.time()
                # unpack integers from the ACK packet, then print some messages
                (magack, ackno) = struct.unpack(">II", ack)
                if verbose >= 3 or (verbose >= 1 and seqno < 5 or seqno % 1000 == 0 or ackno != desired_ackno):
                    print("Got ack with seqno %d while waiting for %d" % (ackno, desired_ackno))
                # write info about the ACK to the log file
                trace.write(0, 0, ackno, tRecv - start)

                if ackno >= desired_ackno:
                    for i in range(desired_ackno, ackno + 1):
                        if i in outstanding:
                            del outstanding[i]
                    desired_ackno = ackno + 1
                    if len(outstanding) < n and have_more_data:
                        state = 0
                    else:
                        state = 2
                elif ackno < desired_ackno:
                    print(f"Received duplicate or out-of-order ACK {ackno}, waiting for {desired_ackno}.")
                    state = 2

            except (socket.timeout, socket.error):
                print(f"Timeout, ACK {desired_ackno} didn't arrive quick enough!")
                state = 3

        elif state == 3: # Resend all outstanding packets.
            # Do we care what order we resend the packets? Maybe? Think about it.
            # If we like, we could loop over the dictionary like this:
            #    for resend_seqno, resend_pkt in outstanding.items(): ...
            # and the packets would be sent in sorted order, because python3.7
            # and above keeps items in a dictionary in the same order they were
            # added to the dictionary.
            #
            # Here, we also know that the outstanding packets are exactly those
            # from desired_ackno, up to (but not including) seqno. So we can
            # loop over that range...
            tSend = time.time()
            for i in range(desired_ackno, seqno):
                pkt = outstanding[i]
                s.sendto(pkt, (host, port))
                # print stuff and record in trace file
                if verbose >= 2:
                    print("Re-sent packet with seqno %d" % (i))
                trace.write(seqno, tSend - start, 0, 0)
            state = 2

        else:
            print(f"OOPS! Should never be in state {state}")
            break

    end = time.time()
    elapsed = end - start
    print("Finished sending all packets!")
    print("Elapsed time: %0.4f s" % (elapsed))
    trace.close()

if __name__ == "__main__":
    if len(sys.argv) <= 3:
        print("To send data to server 1.2.3.4 port 6000, try running:")
        print("   python client.py 1.2.3.4 6000")
        sys.exit(0)
    host = sys.argv[1]
    port = int(sys.argv[2])
    n = int(sys.argv[3])
    t = float(sys.argv[4])
    main(host, port, n, t)
