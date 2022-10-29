import socket
import threading
import base64
import sys
import json
import traceback
import paho.mqtt.client as mqtt
from os import path
from pathlib import Path
from sys import path as sp
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

ONE_PLAYER_MODE = False  # Initialise as 1 player mode

# AI buffer
AI_buffer = queue.Queue()
AI_lock = threading.Lock()
# internal comm buffer
IMU_buffer = queue.Queue()
GUN_buffer = queue.Queue()
vest_buffer = queue.Queue()
internal_lock = threading.Lock()
# eval server buffer
eval_buffer = queue.Queue()
eval_lock = threading.Lock()
# receive from visualizer buffer
vis_recv_buffer = queue.Queue()
vis_recv_lock = threading.Lock()
# send to visualizer buffer
vis_send_buffer = queue.Queue()
vis_send_lock = threading.Lock()

state_lock = threading.Lock()

def input_state(data):
    global curr_state
    state_lock.acquire()
    curr_state.update(data)
    state_lock.release()

# for AI
class AIDetector(threading.Thread):
    def __init__(self):
        super().__init__()
        # 2 Detectors, (1 per player)
        self.detector1 = Detector()
        self.detector2 = Detector()

    def predict_action(self, data, player_num):
        actions = ["logout", "grenade", "idle", "reload", "shield"]
        
        # Detector based on player (CANNOT use same detector for multiple people)
        if player_num == 1:
            useFunc = self.detector1.eval_data
        else:
            useFunc = self.detector2.eval_data

        # Sensitivity: Percentage certainty that prediction is correct
        # Threshold: Threshold of standard deviation of Accelerators combined
        r = useFunc(data, 3, sensitivity=0.6, threshold=0.055)
        return actions[r]

    def run(self):
        # Initiate Terminal Outputs
        action = "none"
        last_detected = "none"
        
        # start game engine
        game_engine = GameEngine(curr_state)
        game_engine.start()

        # start ultra96 client to eval server thread
        my_client = Client(ip_addr, port_num, group_id, secret_key, game_engine)
        my_client.start()
        
        while action != "logout":
            # Update local game state from eval_server
            game_engine.updateFromEval(curr_state)

            # Read buffers and perform actions
            while IMU_buffer.qsize() > 0:
                data = IMU_buffer.get_nowait()
                player_num = data["P"]
                action = self.predict_action(data["V"], player_num)
                if (action != "idle"):
                    print("Predicted:\t", action, "\t\tPrev_detect:", last_detected)
                    last_detected = action

                    AI_buffer.put_nowait([action, player_num])
                    AI_buffer.put_nowait(player_num)

            if AI_buffer.qsize() > 0:
                data = AI_buffer.get_nowait()
                action = data[0]
                player_num = data[1]

                # Player_num performs actions
                temp = game_engine.performAction(action, player_num)
                input_state(temp)
                eval_buffer.put_nowait([temp, player_num])

            if GUN_buffer.qsize() > 0:
                player_num = GUN_buffer.get_nowait()
                temp = game_engine.performAction('shoot', player_num)
                
                # Check bullet hit of opponent
                if vest_buffer.qsize() > 0:
                    vest_buffer.get_nowait()
                    if player_num == 1:
                        game_engine.performAction('bullet1')
                    else:
                        game_engine.performAction('bullet2')
                
                # this output is needed by eval server
                input_state(temp)
                eval_buffer.put_nowait([temp, player_num])
        
# for visualizer
class MQTTClient():
    def __init__(self, topic, client_name):
        self.topic = topic
        self.client = mqtt.Client(client_name)
        self.client.connect('test.mosquitto.org')
        self.client.subscribe(self.topic)

    # publish message to topic
    def publish(self):
        if vis_send_buffer.qsize() > 0:
            state = vis_send_buffer.get_nowait()
            message = json.dumps(state)
            # publishing message to topic
            self.client.publish(self.topic, message, qos = 1)

    def receive(self):
        def on_message(client, data, message):
            vis_recv_buffer.put_nowait(message.payload.decode())
            print("[MQTT] Received: ", message.payload.decode())

        self.client.on_message = on_message
        self.client.subscribe(self.topic)

    def stop(self):
        self.client.unsubscribe()
        self.client.loop_stop()
        self.client.disconnect()

# eval_client
class Client(threading.Thread):
    # ONE Player -> FALSE TRUE
    # TWO PLAYER -> FALSE FALSE
    # NOTE v v v v v v v v Possible bug point!!! 
    global ONE_PLAYER_MODE
    # global ONE_PLAYER_MODE = True
    received_actions = [False, ONE_PLAYER_MODE]     # TO wait for 2 player to complete before sending to eval server

    # Initialise a storage to store state to send to eval server
    evalStore = {}
    evalStore.update(curr_state)
    
    def __init__(self, ip_addr, port_num, group_id, secret_key, game_engine):
        super().__init__()
        # set up a TCP/IP socket to the port number
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_address = (ip_addr, port_num)
        self.secret_key = secret_key
        self.group_id = group_id
        self.game_engine = game_engine

        try:
            # start connection
            self.socket.connect(self.server_address)
            self.accepted = True
            print("[Evaluation Client] Connected: ", self.server_address)
        except Exception as e:
            self.accepted = False
            print("[Evaluation Client] Error: ", e)
            print("[Evaluation Client] Skipped")

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
            print('no more data from eval server')
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
            print('no more data from eval server')
            self.stop()

        msg = data.decode("utf8")

        return msg

    def run(self):
        while True:
            while eval_buffer.qsize() > 0:
                try:
                    state, player_num = eval_buffer.get_nowait()
                    state, actionSucess = self.game_engine.runLogic(state, player_num)

                    vis_send_buffer.put_nowait(state)
                    mqtt_p.publish()

                    print("Checking Player: ", player_num)
                    print("RECEIVED BOTH: ", self.received_actions)

                    if state['p1']['action'] == 'grenade' or state['p2']['action'] == 'grenade':
                        if vis_recv_buffer.qsize() > 0:
                            # visualizer sends player that is hit by grenade
                            data = vis_recv_buffer.get_nowait()
                            if data != 'no':
                                state = self.game_engine.performAction(data)
                                state = self.game_engine.resetValues(state)
                                vis_send_buffer.put_nowait(state)
                                mqtt_p.publish()
                    
                    if self.accepted:
                        if not self.received_actions[player_num - 1]:
                            self.received_actions[player_num-1] = True
                            state = self.game_engine.prepForEval(state, player_num, actionSucess)
                            #Store other player action
                            enemy_player = ['p1', 'p2']
                            if player_num == 1:
                                enemy = 1       # Enemy in 2nd index
                            else:
                                enemy = 0       # Enemy in 1st index

                            preserved_action = self.evalStore.get(enemy_player[enemy]).get('action')
                            self.evalStore.update(state)
                            # RESTORE other players action
                            self.evalStore[enemy_player[enemy]]['action'] = preserved_action
                            

                            if self.received_actions[0] and self.received_actions[1]:
                                self.send_data(self.evalStore)

                                # receive expected state from eval server
                                expected_state = self.receive()
                                print("\n\treceived from eval:\n", expected_state,"\n")
                                expected_state = json.loads(expected_state)

                                # Game State timer check in case of wrong detection of shield
                                self.game_engine.checkShieldTimer(expected_state, state)

                                self.evalStore.update(expected_state)
                                expected_state = self.game_engine.resetValues(expected_state)
                                input_state(expected_state)

                                # Reset of player eval server receivers
                                self.received_actions=[False, ONE_PLAYER_MODE]

                            else: 
                                print("\n\t\tSKIPPED Evals: ", state)
                                state = self.game_engine.resetValues(state)
                                input_state(state)


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
        self.connection1 = None
        self.connection2 = None

        print("[Ultra96 Server] Starting on %s" % port_num)

        self.server_socket.bind(self.server_address)

    # listens for a connection from the laptop
    def setup_connection(self):
        print('[Ultra96 Server] Waiting for laptop')
        
        self.server_socket.listen(2)
        self.connection1, client_address = self.server_socket.accept()
        print("[Ultra96 Server] Connected Laptop 1")
        self.connection2, client_address = self.server_socket.accept()
        print("[Ultra96 Server] Connected Laptop 2")

    # receive from the laptop client
    def receive(self):
        msg = ''

        try:
            data = b''
            data2 = b''
            while not data.endswith(b'_'):
                _d = self.connection1.recv(1)
                _d2 = self.connection2.recv(1)
                if not _d:
                    data = b''
                    break
                if not _d2:
                    data2 = b''
                data += _d
                data2 += _d2

            if len(data) == 0:
                print('no more data from laptop')
                self.stop()

            if len(data2) == 0:
                self.stop()

            data = data.decode("utf-8")
            length = int(data[:-1])
            data2 = data2.decode("utf-8")
            length2 = int(data2[:-1])

            data = b''
            data2 = b''
            while len(data) < length:
                _d = self.connection1.recv(length - len(data))
                if not _d:
                    data = b''
                    break
                data += _d
            
            if len(data) == 0:
                print('no more data from laptop')
                self.stop()

            msg = data.decode("utf8")

            while len(data2) < length2:
                _d = self.connection2.recv(length2 - len(data2))
                if not _d:
                    data2 = b''
                    break
                data2 += _d
            
            if len(data2) == 0:
                print('no more data from laptop')
                self.stop()

            msg = data.decode("utf8")
            msg2 = data2.decode("utf8")

        except Exception as _:
            traceback.print_exc()
            self.stop()
        
        return msg, msg2

    def run(self):
        self.setup_connection()
        AI_detector = AIDetector()
        AI_detector.start()

        while True:
            try:
                msg, msg2 = self.receive()
                if msg:
                    data = json.loads(msg)

                    if data["D"] == "IMU":
                        IMU_buffer.put_nowait(data)
                    elif data["D"] == "GUN":
                        GUN_buffer.put_nowait(data["P"])
                        print("Printing ", data["P"])
                    else:
                        vest_buffer.put_nowait(data)
                if msg2:
                    data = json.loads(msg2)

                    if data["D"] == "IMU":
                        IMU_buffer.put_nowait(data)
                    elif data["D"] == "GUN":
                        GUN_buffer.put_nowait(data["P"])
                        print("Printing ", data["P"])
                    else:
                        vest_buffer.put_nowait(data)

                # print("msg: ", msg)
                # print("msg2: ", msg2)
                
                
                
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
        print('python ultra96.py [Eval IP address] [Group ID] [Play_MODE] [Eval Port] [Local Port]')
        sys.exit()
    secret_key = "qwerqwerqwerqwer"

    ip_addr = sys.argv[1]
    group_id = sys.argv[2]
    if int(sys.argv[3]) == 1:
        ONE_PLAYER_MODE = True
    else:
        ONE_PLAYER_MODE = False
    port_num = int(sys.argv[4])
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
