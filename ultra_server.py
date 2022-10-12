import socket
import threading
import time
import base64
import sys
import time

# ultra96 server to receive the message from the laptop
class Server(threading.Thread):
    def __init__(self, port_num):
        super().__init__()

        # TCP/IP socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_address = ('', port_num)
        self.connection = None
        self.has_received = False

        print("[Ultra96 Server] Starting on %s" % port_num)

        self.server_socket.bind(self.server_address)
        self.expecting_packet = threading.Event()
        self.shutdown = threading.Event()

    # listens for a connection from the laptop
    def setup_connection(self):
        print('[Ultra96 Server] Waiting for laptop')

        self.expecting_packet.clear()
        self.server_socket.listen(1)
        self.connection, client_address = self.server_socket.accept()

        print("[Ultra96 Server] Connected")

    # closes
    def stop(self):
        try:
            self.connection.shutdown(SHUT_RDWR)
            self.connection.close()
        except OSError:
            # connection already closed
            pass

        print('[Ultra96 Server] Closed')

    def run(self):
        self.setup_connection()

        while not self.shutdown.is_set():
            try:
                data = self.connection.recv(1024)

                if data:
                    self.has_received = True
                    print('[Ultra96 Server] received: ', data.decode("utf8"))
                    

                self.has_received = False
                time.sleep(1)

            except Exception as _:
                traceback.print_exc()
                self.stop()

def main():
    if len(sys.argv) != 2:
        print('[Ultra96 Server] Port number')
        sys.exit()

    port_num = sys.argv[1]
    
    u_server = Server(int(port_num))

    u_server.run()


if __name__ == '__main__':
    main()
