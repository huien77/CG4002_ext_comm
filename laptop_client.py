import socket
import base64
import threading
import sshtunnel
import time
import sys

# connecting to ultra96
class UltraClient(threading.Thread):
    def __init__(self, user, passw, port):
        self.ip_addr = '192.168.95.244'
        self.buff_size = 256
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.user = user
        self.passw = passw
        self.port = port
        self.is_start = threading.Event()

    # sshtunneling into sunfire
    def start_tunnel(self):
        # open tunnel to sunfire
        tunnel1 = sshtunnel.open_tunnel(
            # host for sunfire at port 22
            ('stu.comp.nus.edu.sg', 22),
            # ultra96 address
            remote_bind_address = ('192.168.95.244', 22),
            ssh_username = self.user,
            ssh_password = self.passw,
            block_on_close = False
            )
        tunnel1.start()
        
        print('[Tunnel Opened] Tunnel into Sunfire: ' + str(tunnel1.local_bind_port))

        # sshtunneling into ultra96
        tunnel2 = sshtunnel.open_tunnel(
            # ssh to ultra96
            ssh_address_or_host = ('localhost', tunnel1.local_bind_port),
            # local host
            remote_bind_address=('127.0.0.1', self.port),
            ssh_username = 'xilinx',
            ssh_password = 'xilinx',
            local_bind_address = ('127.0.0.1', self.port), #localhost to bind it to
            block_on_close = False
            )
        tunnel2.start()
        print('[Tunnel Opened] Tunnel into Xilinx')

        return tunnel2.local_bind_address

    # sending dummy data to ultra96
    def send(self, data):
        self.client.sendall(data.encode("utf8"))

    def run(self):
        add = self.start_tunnel()
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.connect(add)
        print(f"[ULTRA96 CONNECTED] Connected to Ultra96")
        
        while True:
            try:
                data = input("Random Keystroke: ")
                self.send(data)
            except ConnectionRefusedError:
                self.is_start.clear()
                print("connection refused")
            except Exception as e:
                print(e)
                break

        self.client.close()
        print("[CLOSED]")

def main():
    if len(sys.argv) != 4:
        print("input sunfire username and password, port")
        sys.exit()

    user = sys.argv[1]
    passw = sys.argv[2]
    port = int(sys.argv[3])

    client = UltraClient(user, passw, port)
    client.run()

if __name__ == '__main__':
    main()
