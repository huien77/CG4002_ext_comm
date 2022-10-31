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

# internal comm buffer
IMU_buffer = queue.Queue()
IMU_buffer2 = queue.Queue()
GUN_buffer = queue.Queue()
GUN_buffer2 = queue.Queue()
ACTION_buffer = queue.Queue()
ACTION_buffer2 = queue.Queue()
vest_buffer = queue.Queue()

# internal_lock = threading.Lock()
# eval server buffer
eval_buffer = queue.Queue()
eval_lock = threading.Lock()

# eval_lock = threading.Lock()
# receive from visualizer buffer
vis_recv_buffer = queue.Queue()

# vis_recv_lock = threading.Lock()
# send to visualizer buffer
vis_send_buffer = queue.Queue()
# vis_send_lock = threading.Lock()

state_lock = threading.Lock()

def input_state(data):
    global curr_state
    state_lock.acquire()
    curr_state.update(data)
    state_lock.release()

# for AI
class AIDetector(threading.Thread):
    def __init__(self, player):
        super().__init__()
        # 2 Detectors, (1 per player) [1 Created as there are 2 threads]
        self.detector = Detector()
        self.player_num = player
        print("Initialised AI for player", self.player_num)

    def predict_action(self, data):
        actions = ["logout", "grenade", "idle", "reload", "shield"]
        
        useFunc = self.detector.eval_data

        # Sensitivity: Percentage certainty that prediction is correct
        # Threshold: Threshold of standard deviation of Accelerators combined
        r = useFunc(data, 3, sensitivity=0.6, threshold=0.060)
        
        return actions[r]

    def run(self):
        # Initiate Terminal Outputs
        action = "none"
        last_detected = "none"
                
        while action != "logout":
            # Update local game state from eval_server
            game_engine.updateFromEval(curr_state)

            # Read buffers and perform actions
            if self.player_num == 1:
                while IMU_buffer.qsize() > 0:
                    # print("\r", IMU_buffer.qsize())
                    try:
                        data = IMU_buffer.get_nowait()
                        if IMU_buffer.qsize() >= 20:
                            print("\r",IMU_buffer.qsize(), end="")
                            IMU_buffer.queue.clear()
                        action = self.predict_action(data["V"])
                        ACTION_buffer.put_nowait(action)
                    except Exception as e:
                        print(e)
                        pass

                if ACTION_buffer.qsize() > 0:
                    try:
                        action = ACTION_buffer.get_nowait()
                        if (action != "idle"):
                            print("\033[0;35m\n\n\nPredicted:\t", action, "from player\t", self.player_num, "\t\tPrev_detect:", last_detected)
                            last_detected = action

                            temp = game_engine.performAction(action, self.player_num)
                            input_state(temp)
                            eval_buffer.put_nowait([temp, self.player_num])
                    except Exception as e:
                        print(e)
                        pass
                
                if GUN_buffer.qsize() > 0:
                    try:
                        print()
                        player_num = GUN_buffer.get_nowait()
                        temp = game_engine.performAction('shoot', player_num)
                        
                        # Check bullet hit of opponent
                        if vest_buffer.qsize() > 0:
                            vest_buffer.get_nowait()
                            vest_buffer.queue.clear()
                            if player_num == 1:
                                game_engine.performAction('bullet1', 1)
                            else:
                                game_engine.performAction('bullet2', 2)
                        
                        # this output is needed by eval server
                        input_state(temp)
                        eval_buffer.put_nowait([temp, player_num])
                    except Exception as e:
                        print(e)
                        pass

            elif self.player_num == 2:
                while IMU_buffer2.qsize() > 0:
                    try:
                        data = IMU_buffer2.get_nowait()
                        if IMU_buffer2.qsize() >= 20:
                            print("\t\t\r",IMU_buffer.qsize(), end="")
                            IMU_buffer2.queue.clear()
                        action = self.predict_action(data["V"])
                        ACTION_buffer2.put_nowait(action)

                    except Exception as e:
                        print(e)
                        pass

                if ACTION_buffer2.qsize() > 0:
                    try:
                        action = ACTION_buffer2.get_nowait()
                        if (action != "idle"):
                            print("\033[0;33m\n\n\nPredicted:\t", action, "from player\t", self.player_num, "\t\tPrev_detect:", last_detected)
                            last_detected = action

                            temp = game_engine.performAction(action, self.player_num)
                            input_state(temp)
                            eval_buffer.put_nowait([temp, self.player_num])
                    except Exception as e:
                        print(e)
                        pass

                if GUN_buffer2.qsize() > 0:
                    try:
                        print()
                        player_num = GUN_buffer2.get_nowait()
                        temp = game_engine.performAction('shoot', player_num)
                        
                        # Check bullet hit of opponent
                        if vest_buffer.qsize() > 0:
                            vest_buffer.get_nowait()
                            vest_buffer.queue.clear()
                            if player_num == 1:
                                game_engine.performAction('bullet1', 1)
                            else:
                                game_engine.performAction('bullet2', 2)
                        
                        # this output is needed by eval server
                        input_state(temp)
                        eval_buffer.put_nowait([temp, player_num])
                    except Exception as e:
                        print(e)
                        pass
        
# for visualizer
class MQTTClient():
    def __init__(self, topic, client_name):
        self.topic = topic
        self.client = mqtt.Client(client_name)
        self.client.connect('test.mosquitto.org')
        self.client.subscribe(self.topic)
        self.uniqueCounter = 0

    # publish message to topic
    def publish(self):
        if vis_send_buffer.qsize() > 0:
            self.uniqueCounter += 1
            state = vis_send_buffer.get_nowait()
            state["turn"] = self.uniqueCounter
            print("PUBLISHED TO MQTT:", state, end="\n")
            message = json.dumps(state)
            # publishing message to topic
            self.client.publish(self.topic, message, qos = 1)

    def receive(self):
        def on_message(client, data, message):
            print("\033[0;34mPutting VISRECV!!!", end="")
            vis_recv_buffer.put_nowait(message.payload.decode())
            print("\r[MQTT] Received: ", message.payload.decode(), end="")

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
    
    def __init__(self, ip_addr, port_num, group_id, secret_key):
        super().__init__()
        # set up a TCP/IP socket to the port number
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_address = (ip_addr, port_num)
        self.secret_key = secret_key
        self.group_id = group_id

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
        # preserved_action1 = 'none'
        # preserved_action2 = 'none'
        enemy_player = ['p1', 'p2']
        player_hp = {'p1': 100, 'p2':100}
        while True:
            while eval_buffer.qsize() > 0:
                try:
                    state_read, player_num = eval_buffer.get_nowait()

                    print("State:", state_read)
                    print("Player:", player_num)

                    state, actionSucess = game_engine.runLogic(state_read, player_num)

                    vis_send_buffer.put_nowait(state)
                    mqtt_p.publish()

                    if state['p1']['action'] == 'grenade' or state['p2']['action'] == 'grenade':
                        vizData = "uncollected"
                        trying = 0
                        while vizData == "uncollected":
                            # visualizer sends player that is hit by grenade
                            if vis_recv_buffer.qsize() > 0:
                                vizData = vis_recv_buffer.get_nowait()
                                if vizData != 'no':
                                    print("\rPointed at Picture!! Should HIT!          Trying {} times".format(trying), end="\033[0m\n")
                                    state = game_engine.performAction(vizData)
                                    state = game_engine.resetValues(state)
                                    vis_send_buffer.put_nowait(state)
                                    mqtt_p.publish()
                            trying += 1
                            if trying > 200000:
                                vizData='no'
                        for p in enemy_player:
                            player_hp[p]=state[p]['hp']
                    print("", end="\033[0m\n")
                                    
                    # if not self.accepted:
                    #     state = game_engine.resetValues(state)
                    # input_state(state)
                    if self.accepted:
                        eval_lock.acquire()
                        print("\033[38mReceived Buffer: ", self.received_actions, "\nEvalStore: \n", self.evalStore)
                        if not self.received_actions[player_num - 1]:
                            #Store other player action
                            if player_num == 1:
                                enemy=1
                            else:
                                enemy=0
                            preserved_action = self.evalStore.get(enemy_player[enemy]).get('action')
                            print("PRESERVED ACTION: Player: ", enemy_player[enemy], preserved_action, "playerHP:", player_hp)
                            
                            for p in enemy_player:
                                if state_read[p]['action'][:5] == "fail_":
                                    self.evalStore[p]['action'] = state_read[p]['action'][5:]
                                else:
                                    self.evalStore[p]['action'] = state_read[p]['action']
                                self.evalStore[p]['hp']=player_hp[p]

                            print("####################################################################" * 4)
                            print("EVAL Pre Logic: ", self.evalStore)

                            self.evalStore, actionSucess = game_engine.runLogic(self.evalStore, player_num)

                            print()
                            print("Eval Post Logic: ", self.evalStore)

                            self.evalStore[enemy_player[enemy]]['action'] = preserved_action

                            print("\nPost Preservation: ", self.evalStore)
                            temp = game_engine.prepForEval(self.evalStore, player_num, actionSucess)

                            self.evalStore.update(temp)
                            self.received_actions[player_num - 1] = True

                            print("RECEIVED ACTIONS:", self.received_actions)
                            if self.received_actions[0] and self.received_actions[1]:
                                print("\033[36m Sending to eval:", self.evalStore)
                                self.send_data(self.evalStore)

                                # receive expected state from eval server
                                expected_state = self.receive()
                                print("\n\tReceived from eval:\n", expected_state, end="\033[0m\n")
                                expected_state = json.loads(expected_state)

                                # Game State timer check in case of wrong detection of shield
                                game_engine.checkShieldTimer(expected_state, state)

                                self.evalStore.update(expected_state)
                                player_hp['p1'] = expected_state['p1']['hp']
                                player_hp['p2'] = expected_state['p2']['hp']
                                expected_state = game_engine.resetValues(expected_state)
                                input_state(expected_state)

                                print("\n\t\tLatest EvalsStore: ", self.evalStore)

                                # Reset of player eval server receivers
                                self.received_actions = [False, ONE_PLAYER_MODE]
                        print(end="\033[0m")
                        eval_lock.release()
                    state = game_engine.resetValues(state)
                    input_state(state)

                except Exception as e:
                    print("\033[31mSomething went Terribly Wrong:\n", e, end="\033[0m\n\n\n")
                    pass

    def stop(self):
        self.socket.close()
        print('[Evaluation Client] Closed')

# receive from relay laptop
class Server(threading.Thread):
    def __init__(self, port_num, player):
        super().__init__()
        # TCP/IP socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_address = ('', port_num)
        self.connection1 = None

        print("[Ultra96 Server] Starting on %s" % port_num)

        self.server_socket.bind(self.server_address)
        self.player_num = player

    # listens for a connection from the laptop
    def setup_connection(self):
        print('[Ultra96 Server] Waiting for laptop')
        
        self.server_socket.listen(1)
        self.connection1, client_address = self.server_socket.accept()
        print("[Ultra96 Server] Connected Laptop Player {} \n\n".format(self.player_num))

    # receive from the laptop client
    def receive(self):
        msg = ''

        try:
            data = b''
            while not data.endswith(b'_'):
                _d = self.connection1.recv(1)
                if not _d:
                    data = b''
                    break
                data += _d

            if len(data) == 0:
                print('no more data from laptop')
                self.stop()

            data = data.decode("utf-8")
            length = int(data[:-1])

            data = b''
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

        except Exception as _:
            traceback.print_exc()
            self.stop()
        
        return msg

    def run(self):
        self.setup_connection()
        # AI_detector = AIDetector(self.player_num, game_engine)
        # AI_detector.start()

        while True:
            try:
                msg = self.receive()
                if msg:
                    data = json.loads(msg)

                    if data["D"] == "IMU":
                        if data["P"] == 1:
                            IMU_buffer.put_nowait(data)
                        else:
                            IMU_buffer2.put_nowait(data)
                    elif data["D"] == "GUN":
                        if data["P"] == 1:
                            GUN_buffer.put_nowait(data["P"])
                        else:
                            GUN_buffer2.put_nowait(data["P"])
                    else:
                        vest_buffer.put_nowait(data)

            except Exception as _:
                traceback.print_exc()
                self.stop()

    # closes
    def stop(self):
        self.server_socket.close()

        print('[Ultra96 Server] Closed')

if __name__ == "__main__":
    if len(sys.argv) != 7:
        print('[Ultra96] Invalid number of arguments')
        print('python ultra96.py [Eval IP address] [Group ID] [Play_MODE] [Eval Port] [Local Port1] [Local Port2]')
        sys.exit()
    secret_key = "qwerqwerqwerqwer"

    ip_addr = sys.argv[1]
    group_id = sys.argv[2]
    if int(sys.argv[3]) == 1:
        ONE_PLAYER_MODE = True
    else:
        ONE_PLAYER_MODE = False
    port_num = int(sys.argv[4])
    port_server1 = sys.argv[5]
    port_server2 = sys.argv[6]

    # start ultra96 client to eval server thread
    my_client = Client(ip_addr, port_num, group_id, secret_key)
    my_client.start()

    # Game Engine
    game_engine = GameEngine(curr_state)
    game_engine.start()

    AI_detector1 = AIDetector(1)
    AI_detector1.start()
    AI_detector2 = AIDetector(2)
    AI_detector2.start()

    # start thread for receiving from laptop
    u_server1 = Server(int(port_server1),1)
    u_server1.start()
    u_server2 = Server(int(port_server2),2)
    u_server2.start()

    # receiving from vis
    mqtt_r = MQTTClient('grenade17', 'receive')
    mqtt_r.receive()
    mqtt_r.client.loop_start()

    mqtt_p = MQTTClient('visualizer17', 'publish')
    mqtt_p.client.loop_start()
