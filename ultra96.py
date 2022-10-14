from argparse import Action
from re import M
import re
import socket
from symbol import eval_input
import threading
import time
import base64
import sys
import time
import json
import traceback
from numpy import empty
import paho.mqtt.client as mqtt
from os import getcwd, path
from pathlib import Path
from sys import path as sp
from datetime import datetime
from datetime import timedelta
import queue

sp.append(path.join((Path.cwd()).parent,"jupyter_notebooks","capstoneml","scripts"))
from start_detector import Detector
from GameEngine import GameEngine

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes

curr_state = {
    "p1": {
        "hp": 100,
        "action": 'none',
        "bullets": 6,
        "grenades": 2,
        "shield_time": 0,
        "shield_health": 0,
        "num_shield": 3,
        "num_deaths": 0
        },
    "p2": {
        "hp": 100,
        "action": 'none',
        "bullets": 6,
        "grenades": 2,
        "shield_time": 0,
        "shield_health": 0,
        "num_shield": 3,
        "num_deaths": 0
        }
}

# AI buffer
AI_buffer = queue.Queue()
AI_lock = threading.Lock()
# internal comm buffer
IMU_buffer = queue.Queue(20)
GUN_buffer = queue.Queue()
vest_buffer = queue.Queue()
internal_lock = threading.Lock()
# eval server buffer
eval_buffer = queue.Queue()
eval_lock = threading.Lock()
# send to visualizer buffer
vis_send_buffer = queue.Queue()
vis_send_lock = threading.Lock()
# receive from visualizer buffer
vis_recv_buffer = queue.Queue()
vis_recv_lock = threading.Lock()

def read_state(lock):
    lock.acquire()
    data = curr_state
    lock.release()
    return data

def input_state(data, lock):
    global curr_state
    lock.acquire()
    curr_state = data
    lock.release()

def read_data(buffer, lock):
    lock.acquire()
    data = buffer.get()
    lock.release()
    return data

def input_data(buffer, lock, data):
    lock.acquire()
    buffer.put(data)
    lock.release()

# for AI
class AIDetector(threading.Thread):
    def __init__(self):
        super().__init__()
        self.detector = Detector()

    def predict_action(self, data):
        actions = ["logout", "grenade", "idle", "reload", "shield"]
        r = self.detector.eval_data(data, 0)

        return actions[r]

    def run(self):
        # DEBUGGING
        action = "none"
        last_detected = "none"
        
        # start game engine
        game_engine = GameEngine(curr_state)
        game_engine.start()

        # start ultra96 client to eval server thread
        my_client = Client(ip_addr, port_num, group_id, secret_key)
        my_client.start()
        
        while action != "logout":
            while IMU_buffer.full():
                data = read_data(IMU_buffer, internal_lock)
                action = self.predict_action(data["V"])
                
                if (action != "idle"):
                    print("Predicted:\t", action, "\t\tPrev_detect:", last_detected)
                    last_detected = action
                    input_data(AI_buffer, AI_lock, action)

            if not AI_buffer.empty():
                # action in AI_buffer should not be idle
                # !!! for now all the actions are done by player 1
                # !!! for 2 player game, need extra logic to check the action for p1 or p2
                action = read_data(AI_buffer, AI_lock)
                temp = game_engine.performAction(action)
                # temp should not have bullet hit, data should be ready to send to eval
                input_state(temp)
                input_data(eval_buffer, eval_lock, temp)              

            if not vis_recv_buffer.empty():
                # visualizer sends player that is hit by grenade
                read_data(vis_recv_buffer, vis_recv_lock)
                # yes1 means that p1 grenade hit p2
                # !!! this is enough for 1 player game
                # !!! will need extra checks for 2 player game
                game_engine.performAction('yes1')
                # !!! doesn't need to send the grenade hit to eval server
                # !!! but need to send to visualiser

            if not GUN_buffer.empty():
                # does the shoot action
                read_data(GUN_buffer, internal_lock)
                # !!! this is enough for 1 player game
                # !!! will need extra checks for 2 player game
                temp = game_engine.performAction('shoot')
                # this output is needed by eval server
                input_state(temp)
                input_data(eval_buffer, eval_lock, temp)

            if not vest_buffer.empty():
                read_data(vest_buffer, internal_lock)
                # bullet1 means that p1 bullet hit p2
                # !!! this is enough for 1 player game
                # !!! will need extra checks for 2 player game
                game_engine.performAction('bullet1')
                # !!! doesn't need to send the bullet hit to eval server
                # !!! but need to send to visualiser

            state = read_state()
            state["p1"]["shield_time"] = int(state["p1"]["shield_time"])

            if (state["p1"]["shield_time"] > 0):
                time.sleep(0.66)
                state["p1"]["shield_time"] -= 1
                if state["p1"]["shield_time"] == 0:
                    state["p1"]["shield_health"] = 0
                    input_data(vis_send_buffer, vis_send_lock, temp)
                    mqtt_p.publish()

            if (state["p1"]["shield_time"] > 0):
                
                delayed1_time = datetime.now() + timedelta(seconds=1)
                delayed10_time = datetime.now() + timedelta(seconds=10)
                
                if (datetime.now() == delayed1_time):
                    state["p1"]["shield_time"] -= 1
                if state["p1"]["shield_time"] == 0:
                    state["p1"]["shield_health"] = 0
                    input_data(vis_send_buffer,state_lock, temp)
                    if (datetime.now() == delayed10_time): 
                        state_lock.acquire()
                        mqtt_p.publish()
                        state_lock.release()

                input_state(state)
           
            #     # state_publish(mqtt_p)

# for visualizer
class MQTTClient():
    def __init__(self, topic, client_name):
        self.topic = topic
        self.client = mqtt.Client(client_name)
        self.client.connect('test.mosquitto.org')
        self.client.subscribe(self.topic)

    # publish message to topic
    def publish(self):
        if not vis_send_buffer.empty():
            state = read_data(vis_send_buffer, vis_send_lock)
            message = json.dumps(state)
            # publishing message to topic
            self.client.publish(self.topic, message, qos = 1)

    def receive(self):
        def on_message(client, data, message):
            input_data(vis_recv_buffer, vis_recv_lock, message.payload.decode())
            print("[MQTT] Received: ", message.payload.decode())

        self.client.on_message = on_message
        self.client.subscribe(self.topic)

    def stop(self):
        self.client.unsubscribe()
        self.client.loop_stop()
        self.client.disconnect()

# eval_client
class Client(threading.Thread):
    def __init__(self, ip_addr, port_num, group_id, secret_key):
        super().__init__()
        # set up a TCP/IP socket to the port number
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_address = (ip_addr, port_num)
        self.secret_key = secret_key
        self.group_id = group_id
        # start connection
        self.socket.connect(self.server_address)
        
        print("[Evaluation Client] Connected: ", self.server_address)

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
        print("data to eval", m)
        self.socket.sendall(m.encode("utf-8"))
        self.socket.sendall(encrypted_text)
        print("[Evaluation Client] Sent data")

    # receive from eval server
    def receive(self):
        data = b''
        while not data.endswith(b'_'):
            _d = self.socket.recv(1)
            if not _d:
                data = b''
                break
            data += _d

        if len(data) == 0:
            print('no more data from the client')
            self.stop()

        data = data.decode("utf-8")
        length = int(data[:-1])

        data = b''
        while len(data) < length:
            _d = self.socket.recv(length - len(data))
            if not _d:
                data = b''
                break
            data += _d
        
        if len(data) == 0:
            print('no more data from the client')
            self.stop()

        msg = data.decode("utf8")  # Decode raw bytes to UTF-8
        # game_state_received = self.decrypt_message(msg)
        # msg = temp.split('_')[1]
        return msg

    def run(self):
        print("[Eval Server]: RUNNING...")
        
        while True:
            while len(eval_buffer):
                try:
                    state = read_data(eval_buffer, threading.Lock())
                    
                    input_data(vis_send_buffer, vis_send_lock, state)
                    mqtt_p.publish()
                    
                    # del state['p1']['bullet_hit']
                    # del state['p2']['bullet_hit']
                    self.send_data(state)
                    # print("data to eval", state)
                    expected_state = self.receive()
                    print("received from eval ", expected_state)
                    expected_state = json.loads(expected_state)
                    expected_state['p1']['bullet_hit'] = 'no'
                    expected_state['p2']['bullet_hit'] = 'no'
                    input_state(expected_state)
                    #input_data(vis_send_buffer, threading.Lock(), expected_state)
                    
                except Exception as e:
                    print(e)
            
    def stop(self):
        self.socket.close()
        print('[Evaluation Client] Closed')

# receive from relay laptop
class Server(threading.Thread):
    def __init__(self, port_num):
        super().__init__()
        # TCP/IP socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_address = ('', port_num)
        self.connection = None

        print("[Ultra96 Server] Starting on %s" % port_num)

        self.server_socket.bind(self.server_address)

    # listens for a connection from the laptop
    def setup_connection(self):
        print('[Ultra96 Server] Waiting for laptop')
        
        self.server_socket.listen(1)
        self.connection, client_address = self.server_socket.accept()

        print("[Ultra96 Server] Connected")

        return client_address

    def run(self):
        self.setup_connection()
        AI_detector = AIDetector()
        AI_detector.start()

        while True:
            try:
                data = self.connection.recv(1024)
                data = data.decode('utf8')
                # print("[Ultra96 Server] Received from laptop: ", data)

                i = 0
                j = 0
                while j < len(data):
                    if data[i] != '{':
                        i += 1
                    if data[j] == '}' and data[i] == '{':
                        json_data = json.loads(data[i:j+1])

                        if json_data["D"] == "IMU":
                            input_data(IMU_buffer, internal_lock, json_data)
                        elif json_data["D"] == "GUN":
                            input_data(GUN_buffer, internal_lock, json_data)
                        else:
                            input_data(vest_buffer, internal_lock, json_data)
                        
                        i = j + 1

                    j += 1
                
            except Exception as _:
                traceback.print_exc()
                self.stop()

    # closes
    def stop(self):
        self.server_socket.close()

        print('[Ultra96 Server] Closed')

if __name__ == "__main__":
    if len(sys.argv) != 6:
        print('[Ultra96] Invalid number of arguments')
        print('python ultra96.py [Eval IP address] [Eval Port] [Group ID] [Secret Key] [Local Port]')
        sys.exit()

    ip_addr = sys.argv[1]
    port_num = int(sys.argv[2])
    group_id = sys.argv[3]
    secret_key = sys.argv[4]
    port_server = sys.argv[5]

    # start thread for receiving from laptop
    u_server = Server(int(port_server))
    u_server.start()

    # receiving from vis
    mqtt_r = MQTTClient('grenade17', 'receive')
    mqtt_r.receive()
    mqtt_r.client.loop_start()

    mqtt_p = MQTTClient('visualizer17', 'publish')
    mqtt_p.client.loop_start()
    
    #mqtt_p.terminate()
    #mqtt_r.terminate()