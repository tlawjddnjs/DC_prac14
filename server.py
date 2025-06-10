import socket
import os
import struct
import time

FLAGS = _ = None
DEBUG = False

CHUNK_SIZE = 1500
PAYLOAD_SIZE = 1456
WINDOW_SIZE = 4  # 2^m - 1 형태로 설정
TIMEOUT = 0.5
SEQ_MODULO = 16
file_info = {}

def load_file_info():
    for fname in os.listdir('.'):
        if os.path.isfile(fname):
            file_info[fname] = os.path.getsize(fname)

def calculate_checksum(buf: bytes) -> int:
    if len(buf) & 1:
        buf += b'\x00'
    s = sum((buf[i] << 8) + buf[i+1] for i in range(0, len(buf), 2))
    s = ~s & 0xFFFF
    return s

def make_packet(seq: int, data: bytes) -> bytes:
    seq_bytes = struct.pack('>H', seq)
    checksum = calculate_checksum(seq_bytes + b'\x00\x00' + data)
    checksum_bytes = struct.pack('>H', checksum)
    return seq_bytes + checksum_bytes + data

def main():
    if DEBUG:
        print(f'Parsed arguments {FLAGS}')
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((FLAGS.address, FLAGS.port))
    print(f'Listening on {sock}')

    while True:
        try:
            data, client = sock.recvfrom(2**16)
            message = data.decode('utf-8').strip()
            print(f'Received {message} from {client}')

            if message.startswith("INFO "):
                filename = message[5:].strip()
                if filename in file_info:
                    size = str(file_info[filename])
                    sock.sendto(size.encode('utf-8'), client)
                else:
                    sock.sendto("404 Not Found".encode('utf-8'), client)

            elif message.startswith("DOWNLOAD"):
                filename = message[8:].strip()
                if filename not in file_info:
                    continue

                with open(filename, 'rb') as f:
                    base = 0
                    next_seq = 0
                    packets = []
                    total = file_info[filename]
                    while True:
                        chunk = f.read(PAYLOAD_SIZE)
                        if not chunk:
                            break
                        packets.append(chunk)

                acked = base
                last_ack_time = time.time()
                sock.settimeout(TIMEOUT)  # ✅ 타임아웃 설정

                while acked < len(packets):
                    while next_seq < acked + WINDOW_SIZE and next_seq < len(packets):
                        pkt = make_packet(next_seq % SEQ_MODULO, packets[next_seq])
                        sock.sendto(pkt, client)
                        print(f'Sent seq={next_seq % SEQ_MODULO}')
                        next_seq += 1

                    try:
                        ack_raw, _ = sock.recvfrom(2)
                        ack = struct.unpack('>H', ack_raw)[0]
                        print(f"Received ACK={ack}")
                        while acked < len(packets) and (acked % SEQ_MODULO) != ack:
                            acked += 1
                        if (acked % SEQ_MODULO) == ack:
                            acked += 1
                        last_ack_time = time.time()
                    except socket.timeout:
                        print("Timeout. Resending from base.")
                        next_seq = acked

                print(f'File transfer complete: {filename}')

        except KeyboardInterrupt:
            print('Shutting down...')
            break
        except Exception as e:
            print(f'Error: {e}')
            continue

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--address', type=str, default='0.0.0.0')
    parser.add_argument('--port', type=int, default=3034)
    FLAGS, _ = parser.parse_known_args()
    DEBUG = FLAGS.debug
    load_file_info()
    main()
