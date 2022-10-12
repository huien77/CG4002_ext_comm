import base64
import json
import socket
import sys
import threading
import time
##
##from os import path
##from pathlib import Path
##from system import path as sp
##sp.append(path.join(Path.cwd(),"jupyter_notebooks","capstoneml","scripts"))
##from start_detector import Detector

from random import randint
from ultra_server import Server #importing from ultra_server.py, same dir
from visualizer import MQTTClient

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

# for encryption
# BLOCK_SIZE = 16
PADDING = ' '

ACTIONS = ['shoot', 'shield', 'reload', 'grenade', 'logout']

# port_num 8000
# localhost 127.0.0.1
# secret_key 1234567812345678

# client runs on ultra96    
# client takes in ip_address of server, port number, group id and a secret key
class Client(threading.Thread):
    def __init__(self, ip_addr, port_num, group_id, secret_key):
        super(Client, self).__init__()

        # set up a TCP/IP socket to the port number
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_address = (ip_addr, port_num)
        # store secret key
        self.secret_key = secret_key
        # start connection
        self.socket.connect(server_address)

        self.timeout = 60
        self.has_no_response = False
        self.connection = None
        self.timer = None
        self.shutdown = threading.Event()
        
        print("[Evaluation Client] Connected!")

    def encrypt_message(self, message):
        # convert to a json string
        plain_text = json.dumps(message)
        
        iv = get_random_bytes(AES.block_size)
        aes_key = bytes(str(self.secret_key), encoding = "utf8")
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        encrypted_text = base64.b64encode(iv + cipher.encrypt(pad(plain_text.encode('utf-8'), AES.block_size)))

        # find length of encrypted text
        length = len(encrypted_text)
        
        return length, encrypted_text
    
    # send to eval server
    def send_data(self, send_dict):
        length, encrypted_text = self.encrypt_message(send_dict)
        m = str(length) + "_"
        self.socket.sendall(m.encode("utf-8"))
        self.socket.sendall(encrypted_text)

    # receive from eval server
    def receive(self):
        data = self.socket.recv(1024)
        msg = data.decode("utf8")
        return msg

    def stop(self):
        self.connection.close()
        self.shutdown.set()
        self.timer.cancel()


def main():
    if len(sys.argv) != 5:
        print('[Evaluation Client] Invalid number of arguments')
        print('python eval_client.py [IP address] [Port] [groupID] [secret key]')
        sys.exit()

    ip_addr = sys.argv[1]
    port_num = int(sys.argv[2])
    group_id = sys.argv[3]
    secret_key = sys.argv[4]
    port_server = 8086

    # start ultra96 server thread
    u_server = Server(int(port_server))
    u_server.start()

    mqtt = MQTTClient()
    mqtt.start()

    # start ultra96 client to eval server thread
    my_client = Client(ip_addr, port_num, group_id, secret_key)
    count = 0

    # start AI thread
    ##AI_detector = Detector()
    ##AI_detector.start()
    ## AI_detector.eval_data(data)
    
    with open("test_json.txt", 'r') as f:
        # a python dictionary
        data = json.load(f)
        
    while True:
        rand = randint(0, 4)
        # generate random action for p1
        if (u_server.has_received):
            i = 10
            while i != 0:
                data['p1']['shield_health'] -= 1
                        
                my_client.send_data(data)
                mqtt.publish(data)
                i -= 1
                sleep(1)

        recv_data = my_client.receive()
        print("[Evaluation Client] Received data: ", recv_data)
        time.sleep(2)

        count += 1
        
        if(count == 50):
            my_client.stop()

if __name__ == '__main__':
    main()
