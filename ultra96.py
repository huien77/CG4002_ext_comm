from argparse import Action
from re import M
import re
import socket
import threading
import time
import base64
import sys
import time
import json
import traceback
import paho.mqtt.client as mqtt
from os import getcwd, path
from pathlib import Path
from sys import path as sp

sp.append(path.join((Path.cwd()).parent,"jupyter_notebooks","capstoneml","scripts"))
from start_detector import Detector
from GameEngine import GameEngine

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes

# PLAYER_STATE = {
#     "p1": {
#         "hp": 100,
#         "action": None,
#         "bullets": 6,
#         "grenades": 2,
#         "shield_time": 0,
#         "shield_health": 0,
#         "num_shield": 3,
#         "num_deaths": 0
#         },
#     "p2": {
#         "hp": 100,
#         "action": None,
#         "bullets": 6,
#         "grenades": 2,
#         "shield_time": 0,
#         "shield_health": 0,
#         "num_shield": 3,
#         "num_deaths": 0
#         }
# }

PLAYER_STATE_VIS = {
    "p1": {
        "hp": 100,
        "action": 'none',
        "bullets": 6,
        "bullet_hit": "no", 
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
        "bullet_hit": "no",
        "grenades": 2,
        "shield_time": 0,
        "shield_health": 0,
        "num_shield": 3,
        "num_deaths": 0
        }
}

state_lock = threading.Lock()
# curr_state = PLAYER_STATE
curr_state_vis = PLAYER_STATE_VIS

# AI buffer
AI_buffer = []
# internal comm buffer
IMU_buffer = []
GUN_buffer = []
vest_buffer = []
# eval server buffer
eval_buffer = []
# send to visualizer buffer
vis_send_buffer = []
# receive from visualizer buffer
vis_recv_buffer = []

def read_state():
    state_lock.acquire()
    data = curr_state_vis
    state_lock.release()
    return data

def input_state(data):
    global curr_state_vis
    state_lock.acquire()
    curr_state_vis = data
    state_lock.release()

def read_data(buffer, lock):
    lock.acquire()
    data = buffer.pop(0)
    lock.release()
    return data

def input_data(buffer, lock, data):
    lock.acquire()
    buffer.append(data)
    lock.release()

def state_publish(mqtt_p):
    state = read_state()
    input_data(vis_send_buffer, state_lock, state)
    mqtt_p.publish()

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
        action = ""
        last_detected = ""
        
        # start game engine
        game_engine = GameEngine(PLAYER_STATE_VIS)
        game_engine.start()

        # sending to vis
        mqtt_p = MQTTClient('visualizer17', 'publish')
        mqtt_p.client.loop_start()
        state_publish(mqtt_p)

        # start ultra96 client to eval server thread
        my_client = Client(ip_addr, port_num, group_id, secret_key)
        my_client.start()
        
        while action != "logout":
            while len(IMU_buffer):
                data = read_data(IMU_buffer, state_lock)
                action = self.predict_action(data["V"])
                
                if (action != "idle"):
                    print("Predicted:\t", action, "\t\tPrev_detect:", last_detected)
                    last_detected = action
                    input_data(AI_buffer, state_lock, action)

            if len(AI_buffer):
                action = read_data(AI_buffer, state_lock)

                temp = read_state()

                if (action != "idle"):
                    temp = game_engine.performAction(action)

                    input_state(temp)
                    input_data(vis_send_buffer,state_lock, temp)
                    mqtt_p.publish()
                    # state_publish(mqtt_p)
                    state = read_state()
                    del state['p1']['bullet_hit']
                    del state['p2']['bullet_hit']
                    input_data(eval_buffer, state_lock, state)
                    state['p1']['bullet_hit'] = "no"
                    state['p2']['bullet_hit'] = "no"                  
                    

            if len(vis_recv_buffer):
                # Visualizer sends player that is hit by grenade
                read_data(vis_recv_buffer, state_lock)
                #print("[Game engine] Received from visualiser:", player_hit)
                temp = game_engine.performAction('yes1')
                input_state(temp)
                input_data(vis_send_buffer,state_lock, temp)
                mqtt_p.publish()

                #print("[Game engine] Sent to curr state and eval:", state)

            if len(GUN_buffer):
                
                read_data(GUN_buffer, state_lock)
                temp = game_engine.performAction('shoot')
                
                input_state(temp)
                input_data(vis_send_buffer,state_lock, temp)
                mqtt_p.publish()
                state = read_state()
                del state['p1']['bullet_hit']
                del state['p2']['bullet_hit']
                input_data(eval_buffer, state_lock, state)
                state['p1']['bullet_hit'] = "no"
                state['p2']['bullet_hit'] = "no"                  
                
                
                # input_state(temp)
                # state_publish(mqtt_p)

                # temp['p1']['action'] = 'none'
                # input_state(temp)
                # state_publish(mqtt_p)

            if len(vest_buffer):
                read_data(vest_buffer, state_lock)
                action = "yes"
                temp = game_engine.performAction(action)

                # input_state(temp)
                # state = read_state()
                # to_eval_state = state.copy()
                # print("!!!!! CHECK !!!!!", to_eval_state, "\n VS \n", state)
                # del to_eval_state['p1']['bullet_hit']
                # del to_eval_state['p2']['bullet_hit']
                # input_data(eval_buffer, state_lock, to_eval_state)
                # print("GHMMMMM...", eval_buffer, "\nVS\n", state)
                # del to_eval_state
                # state['p1']['bullet_hit'] = "no"
                # state['p2']['bullet_hit'] = "no"                  
                # state_publish(mqtt_p)

                # temp['p1']['action'] = 'none'
                # input_state(temp)
                # state_publish(mqtt_p)


                input_state(temp)
                input_data(vis_send_buffer,state_lock, temp)
                mqtt_p.publish()
                # state_publish(mqtt_p)

                temp["p2"]["bullet_hit"]="no"
                input_state(temp)
                input_data(vis_send_buffer,state_lock, temp)
                mqtt_p.publish()

            state = read_state()
            state["p1"]["shield_time"] = int(state["p1"]["shield_time"])

            if (state["p1"]["shield_time"] > 0):
                time.sleep(0.66)
                state["p1"]["shield_time"] -= 1
                if state["p1"]["shield_time"] == 0:
                    state["p1"]["shield_health"] = 0

                input_state(state)
                input_data(vis_send_buffer,state_lock, temp)
                mqtt_p.publish()
                # state_publish(mqtt_p)

# for visualizer
class MQTTClient(threading.Thread):
    def __init__(self, topic, client_name):
        super().__init__()
        self.topic = topic
        self.client = mqtt.Client(client_name)
        self.client.connect('test.mosquitto.org')
        self.client.subscribe(self.topic)

    # publish message to topic
    def publish(self):
        if len(vis_send_buffer):
            state = read_data(vis_send_buffer, threading.Lock())
            message = json.dumps(state)
            # publishing message to topic
            is_sent = self.client.publish(self.topic, message)

    def receive(self):
        def on_message(client, data, message):
            input_data(vis_recv_buffer, threading.Lock(), message.payload.decode())
            print("[MQTT] Received: ", message.payload.decode())
            print(vis_recv_buffer)

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
        self.socket.sendall(m.encode("utf-8"))
        self.socket.sendall(encrypted_text)
        # print("[Evaluation Client] Sent data")

    # receive from eval server
    def receive(self):
        data = self.socket.recv(1024)
        temp = data.decode("utf8")
        msg = temp.split('_')[1]
        return msg

    def run(self):
        print("[Eval Server]: RUNNING...")
        while len(eval_buffer):
            try:
                state = read_data(eval_buffer, threading.Lock())
                self.send_data(state)

                expected_state = self.receive()
                expected_state = json.loads(expected_state)
                expected_state['p1']['bullet_hit'] = 'no'
                expected_state['p2']['bullet_hit'] = 'no'
                input_state(expected_state)
                input_data(vis_send_buffer, threading.Lock(), expected_state)
                
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

                print(data)
                while j < len(data):
                    if data[i] != '{':
                        i += 1
                    if data[j] == '}':
                        json_data = json.loads(data[i:j+1])

                        if json_data["D"] == "IMU":
                            input_data(IMU_buffer, state_lock, json_data)
                        elif json_data["D"] == "GUN":
                            input_data(GUN_buffer, state_lock, json_data)
                        else:
                            input_data(vest_buffer, state_lock, json_data)
                        
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
    
    #mqtt_p.terminate()
    #mqtt_r.terminate()