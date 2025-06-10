import socket
import struct
import os
import threading
import time

SERVER_IP = '0.0.0.0'
SERVER_PORT = 3034
MTU = 1500
SEQ_MAX = 16  # 0~15
WINDOW_SIZE = 4
DATA_SIZE = MTU - 4
TIMEOUT = 0.5

def calculate_checksum(buf: bytes) -> int:
    if len(buf) & 1:
        buf += b'\x00'
    s = sum((buf[i] << 8) + buf[i+1] for i in range(0, len(buf), 2))
    s = ~s & 0xFFFF
    return s

class GBNServer:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((SERVER_IP, SERVER_PORT))
        self.sock.settimeout(0.1)
        print(f"[+] Listening on {SERVER_IP}:{SERVER_PORT}")
        self.clients = {}  # addr -> 상태 정보 저장 가능

    def listen(self):
        while True:
            try:
                data, addr = self.sock.recvfrom(MTU)
                if data.startswith(b'INFO'):
                    _, filename = data.decode().split(' ', 1)
                    self.handle_info(addr, filename.strip())
                elif data.startswith(b'DOWNLOAD'):
                    _, filename = data.decode().split(' ', 1)
                    threading.Thread(target=self.handle_download, args=(addr, filename.strip())).start()
                else:
                    # Ack 응답 처리: 다운 중에만 의미 있음
                    self.last_ack[addr] = struct.unpack('>H', data[:2])[0]
            except socket.timeout:
                continue

    def handle_info(self, addr, filename):
        if not os.path.exists(filename):
            self.sock.sendto(b'404 Not Found', addr)
            return
        size = os.path.getsize(filename)
        self.sock.sendto(str(size).encode('utf-8'), addr)
        print(f"[INFO] Sent file size ({size}) to {addr}")

    def handle_download(self, addr, filename):
        with open(filename, 'rb') as f:
            file_data = f.read()

        total_packets = (len(file_data) + DATA_SIZE - 1) // DATA_SIZE
        base = 0
        next_seq = 0
        timers = [None] * total_packets
        acked = [False] * total_packets
        self.last_ack = {addr: -1}  # 마지막 받은 ACK 번호

        def send_packet(i):
            seq = i % SEQ_MAX
            start = i * DATA_SIZE
            end = min(start + DATA_SIZE, len(file_data))
            data = file_data[start:end]
            packet = struct.pack('>H', seq) + struct.pack('>H', calculate_checksum(struct.pack('>H', seq) + data)) + data
            self.sock.sendto(packet, addr)
            print(f"[SEND] Seq={seq} (index={i})")

        def retransmit_window():
            print(f"[RETX] Timer expired. Resending window base={base}, next_seq={next_seq}")
            for i in range(base, next_seq):
                send_packet(i)

        # 전송 루프
        while base < total_packets:
            # 새 패킷 전송
            while next_seq < base + WINDOW_SIZE and next_seq < total_packets:
                send_packet(next_seq)
                timers[next_seq] = time.time()
                next_seq += 1

            # ACK 대기
            try:
                ack_data, _ = self.sock.recvfrom(MTU)
                ack_seq = struct.unpack('>H', ack_data[:2])[0]
                print(f"[ACK] Received: {ack_seq}")

                # base와 ack_seq 일치하면 슬라이드
                while base < total_packets and (base % SEQ_MAX) != ack_seq:
                    acked[base] = True
                    base += 1

                # 최종적으로 ack_seq까지 포함
                if base < total_packets and (base % SEQ_MAX) == ack_seq:
                    acked[base] = True
                    base += 1

            except socket.timeout:
                # 타임아웃 확인
                for i in range(base, next_seq):
                    if not acked[i] and time.time() - timers[i] > TIMEOUT:
                        retransmit_window()
                        break  # 한번만 재전송

        print("[+] File transfer complete")

if __name__ == '__main__':
    server = GBNServer()
    server.listen()
