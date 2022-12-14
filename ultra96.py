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
from multiprocessing import Process, Queue, Lock
# import queue

sp.append(path.join((Path.cwd()).parent,"jupyter_notebooks","capstoneml","scripts"))
from start_detector import Detector
from GameEngine import GameEngine

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes

def doNothing(*args, end="huh"):
    return

debugMode = True
if debugMode:
    dbprint = print
else:
    dbprint = doNothing

printLock = Lock()
def lockedPrinting(*args, end="\n"):
    printLock.acquire()
    print(args,end=end)
    printLock.release()


def fnTrack(trackid):
    return
    # print("\n\033[32m{}\033[0m\n".format(trackid))

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

connections = Queue()

# internal comm buffer
IMU_buffer = Queue()
IMU_buffer2 = Queue()
GUN_buffer = Queue()
GUN_buffer2 = Queue()
ACTION_buffer = Queue()
ACTION_buffer2 = Queue()
vest_buffer = Queue()
eval_damage = Queue()

eval_buffer = Queue()

eval_lock = Lock()
eval_store_q = Queue()

vis_recv_buffer = Queue()

vis_send_buffer = Queue()

# allQueue to initialise
allQueue = [IMU_buffer, IMU_buffer2,GUN_buffer2, ACTION_buffer,ACTION_buffer2, eval_damage, eval_buffer, eval_store_q, vis_send_buffer]

for qqq in allQueue:
    qqq.put("start")
    qqq.get()

state_lock = Lock()
game_engine_lock = Lock()

def input_state(data):
    global curr_state
    state_lock.acquire()
    curr_state.update(data)
    state_lock.release()

# for AI
class AIDetector(Process):
    def __init__(self, player):
        super().__init__()
        # 2 Detectors, (1 per player) [1 Created as there are 2 threads]
        self.detector = Detector()
        self.player_num = player
        print("Initialised AI for player", self.player_num)

    def predict_action(self, data):
        actions = ["logout", "grenade", "idle", "reload", "shield"]
        
        useFunc = self.detector.eval_data

        """
        ###############
        #NOTICE ME!!!#
        ###############
        """
        if self.player_num == 1:
            ideal_len = 3
        else:
            ideal_len = 3

        # Sensitivity: Percentage certainty that prediction is correct
        # Threshold: Threshold of standard deviation of Accelerators combined
        r = useFunc(data, 3, sensitivity=0.68, threshold=0.057, ideal_len=ideal_len)
        
        return actions[r]

    def run(self):
        # Initiate Terminal Outputs
        action = "none"
                
        while True:
            # Update local game state from eval_server

            # Read buffers and perform actions
            if self.player_num == 1:
                while not IMU_buffer.empty():
                    # print("\r", IMU_buffer.qsize())
                    try:
                        data = IMU_buffer.get()
                        action = self.predict_action(data["V"])
                        if (action != "idle"):
                            ACTION_buffer.put(action)
                    except Exception as e:
                        print(e)
                        pass
       
            elif self.player_num == 2:
                while not IMU_buffer2.empty():
                    try:
                        data = IMU_buffer2.get()
                        action = self.predict_action(data["V"])
                        if action != "idle":
                            ACTION_buffer2.put(action)

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
            state = vis_send_buffer.get()
            state["turn"] = self.uniqueCounter
            dbprint("\033[34mPUBLISHED TO MQTT:", state, end="\033[0m\n")
            message = json.dumps(state)
            # publishing message to topic
            self.client.publish(self.topic, message, qos = 1)

    def receive(self):
        def on_message(client, data, message):
            print("\033[0;34mVISRECV", end="")
            vis_recv_buffer.put(message.payload.decode())
            dbprint("\r[MQTT] Received: ", message.payload.decode(), end="\n")

        self.client.on_message = on_message
        self.client.subscribe(self.topic)

    def stop(self):
        self.client.unsubscribe()
        self.client.loop_stop()
        self.client.disconnect()

# eval_client
class Client(Process):
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
        dbprint("data to eval", m)
        self.socket.sendall(m.encode("utf-8"))
        self.socket.sendall(encrypted_text)
        dbprint("[Evaluation Client] Sent data")

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
        evalStore = game_engine.readGameState(True)
        _players = ['p1', 'p2']
        recved_dmg = False
        mqtt_p = MQTTClient('visualizer17', 'publish')
        mqtt_p.client.loop_start()
        last_detected1 = "none"
        last_detected2 = "none"


        while True:
            if ACTION_buffer.qsize() > 0:
                try:
                    fnTrack("ACTION BUFFER 1")
                    game_engine.updatePlayerState(curr_state)
                    action1 = ACTION_buffer.get()
                    print("\033[0;35m\n\n\nPredicted:\t", action1, "from player\t", 1, "\t\tPrev_detect:", last_detected1)
                    last_detected1 = action1

                    # temp = game_engine.performAction(action, 1, False)
                    # input_state(temp)
                    eval_buffer.put([action1, 1, 'imu'])
                except Exception as e:
                    print(e)
                    
            
            if GUN_buffer.qsize() > 0:
                try:
                    fnTrack("GUN BUFFER 1")
                    game_engine.updatePlayerState(curr_state)
                    player_1 = GUN_buffer.get()
                    # temp = game_engine.performAction('shoot', 1, False)
                    
                    # Check bullet hit of opponent
                    if vest_buffer.qsize() > 0:
                        vest_buffer.get()
                        # vest_buffer.queue.clear()
                        # temp = game_engine.performAction('bullet1', 1, False)
                        subact = 'bullet1'
                        eval_damage.put(['bullet1', 1])
                    else:
                        subact = 'missed'
                    
                    # this output is needed by eval server
                    # input_state(temp)
                    eval_buffer.put(['shoot', 1, subact])
                except Exception as e:
                    print(e)
                    pass
            
            if ACTION_buffer2.qsize() > 0:
                try:
                    fnTrack("ACTION BUFFER 2")
                    game_engine.updatePlayerState(curr_state)
                    action2 = ACTION_buffer2.get()
                    print("\033[0;33m\n\n\nPredicted:\t", action2, "from player\t", 2, "\t\tPrev_detect:", last_detected2)
                    last_detected2 = action2

                    # temp = game_engine.performAction(action2, 2, False)
                    # input_state(temp)
                    eval_buffer.put([action2, 2, 'imu'])
                except Exception as e:
                    print(e)
                    pass

            if GUN_buffer2.qsize() > 0:
                try:
                    game_engine.updatePlayerState(curr_state)
                    player_2 = GUN_buffer2.get()
                    # temp = game_engine.performAction('shoot', 2, False)
                    
                    # Check bullet hit of opponent
                    if vest_buffer.qsize() > 0:
                        vest_buffer.get()
                        # vest_buffer.queue.clear()
                        # temp = game_engine.performAction('bullet2', 2, False)
                        subact = 'bullet2'
                        eval_damage.put(['bullet2', 2])
                    else:
                        subact = 'missed'
                    
                    # this output is needed by eval server
                    # input_state(temp)
                    eval_buffer.put(['shoot', 2, subact])
                except Exception as e:
                    print(e)
                    pass

            while eval_buffer.qsize() > 0:
                try:
                    fnTrack(1)
                    # state_read, player_num = eval_buffer.get()
                    action, player_num, sub_action = eval_buffer.get()
                    state_read = game_engine.performAction(action, player_num, False)

                    if not (sub_action in ['imu', 'missed']):
                        state_read = game_engine.performAction(sub_action, player_num, False)

                    # if state_read[_players[player_num-1]]['action'] == 'none':
                    #     break
                    if action == 'none':
                        break

                    game_engine.printWatch()

                    dbprint("State:", state_read)
                    dbprint("Player:", player_num)
                    input_state(state_read)
                    state_pubs = game_engine.runLogic(player_num, eval=False)
                    fnTrack(2)
                    game_engine.printWatch()
                    vis_send_buffer.put(state_pubs)
                    fnTrack(3)
                    mqtt_p.publish()

                    # NOTE BUG Performing Uncollected
                    # if state_pubs['p1']['action'] == 'grenade' or state_pubs['p2']['action'] == 'grenade':
                    if action == 'grenade':
                        fnTrack(4)
                        vizData = "uncollected"
                        trying = 0
                        while vizData == "uncollected":
                            # visualizer sends player that is hit by grenade
                            if vis_recv_buffer.qsize() > 0:
                                fnTrack(5)
                                vizData = vis_recv_buffer.get()
                                if vizData != 'no':
                                    dbprint("\rPointed at Picture!! Should HIT! Tried {} times".format(trying), end="\033[0m\n")
                                    game_engine.performAction(vizData, eval=False)
                                    state_pubs = game_engine.resetValues(eval=False)
                                    vis_send_buffer.put(state_pubs)
                                    mqtt_p.publish()

                                    state_pubs[_players[player_num-1]]['action']="grenade"
                                    game_engine.updatePlayerState(state_pubs)
                                    eval_damage.put([vizData, player_num])
                            trying += 1
                            if trying > 1000000:
                                fnTrack(222)
                                vizData='no'
                                eval_damage.put([vizData, player_num])
                    fnTrack(6)
                    dbprint("", end="\033[0m\n")

                    eval_store_q.put("start")
                    fnTrack(7)
                    if self.accepted:
                        fnTrack(8)
                        game_engine.printWatch()
                        statedmgCheck = game_engine.readGameState(False)
                        if statedmgCheck[_players[player_num-1]]['action'] in ['grenade', 'shoot']:
                            if eval_damage.qsize() > 0:
                                atacktype, attacker = eval_damage.get()
                                recved_dmg = True
                            else:
                                recved_dmg = False
                        fnTrack(9)
                        game_engine.printWatch()
                        if (eval_store_q.qsize() > 0):
                            fnTrack(10)
                            eval_store_q.get()
                            if not self.received_actions[player_num - 1]:
                                eval_lock.acquire()
                                
                                #Store other player action
                                if player_num == 1:
                                    enemy=1
                                else:
                                    enemy=0
                                game_engine.printWatch()
                                evalStore = game_engine.readGameState(True)
                                preserved_action = evalStore.get(_players[enemy]).get('action')
                                
                                for p in _players:
                                    if state_read[p]['action'][:5] == "fail_":
                                        evalAction = state_read[p].get('action')[5:]
                                    else:
                                        evalAction = state_read[p].get('action')
                                    evalStore[p]['action'] = evalAction
                                game_engine.printWatch()
                                game_engine.updateFromEval(evalStore)
                                dbprint("####################################################################" * 4)
                                game_engine.printWatch()

                                # Gamestate to send (First Action of each player after each Eval)
                                evalStore = game_engine.runLogic(player_num, eval=True)
                                game_engine.printWatch()
                                game_engine.updateFromEval(evalStore)
                                game_engine.printWatch()
                                # Correcting HP based on action that matter
                                if evalStore[_players[player_num-1]]['action'] in ['grenade', 'shoot']:
                                    if recved_dmg:
                                        evalStore = game_engine.performAction(atacktype, attacker, eval=True)

                                game_engine.printWatch()

                                evalStore[_players[enemy]]['action'] = preserved_action

                                game_engine.printWatch()
                                game_engine.updateFromEval(evalStore)
                                game_engine.printWatch()
                                eval_to_send = game_engine.prepForEval()

                                evalStore.update(eval_to_send)
                                self.received_actions[player_num - 1] = True

                                if self.received_actions[0] and self.received_actions[1]:
                                    dbprint("\033[36m Sending to eval:", evalStore)
                                    try:
                                        self.send_data(eval_to_send)
                                    except BrokenPipeError as e:
                                        self.accepted = False
                                        break
                                    try:
                                        # receive expected state from eval server
                                        expected_state = self.receive()
                                        dbprint("\n\tReceived from eval:\n", expected_state, end="\033[0m\n")
                                        expected_state = json.loads(expected_state)
                                        game_engine.sendRecvDiff([expected_state['p1']['action'], expected_state['p2']['action']])

                                        # Game State timer check in case of wrong detection of shield
                                        game_engine.checkShieldTimer(expected_state)

                                        evalStore.update(expected_state)
                                        game_engine.updateFromEval(expected_state)
                                        expected_state = game_engine.resetValues(True)
                                        while eval_damage.qsize() > 0:
                                            eval_damage.get()

                                        input_state(expected_state)
                                    except Exception as e:
                                        print("RECEIVE PROBLEMO? MSG: {}".format(e))

                                    dbprint("\n\t\tLatest EvalsStore: ", game_engine.readGameState(True))

                                    # Reset of player eval server receivers
                                    while eval_store_q.qsize() > 0:
                                        eval_store_q.get()
                                    self.received_actions = [False, ONE_PLAYER_MODE]
                                eval_lock.release()
                            
                            else:
                                if eval_damage.qsize() > 0 :
                                    __, __ = eval_damage.get()

                            dbprint(end="\033[0m\n")
                    fnTrack(11)
                    state_pubs = game_engine.resetValues(eval=False)
                    input_state(state_pubs)
                    fnTrack(12)


                except Exception as e:
                    print("\n\n\033[31mSomething went Terribly Wrong:\n", e, end="\033[0m\n\n\n")
                    pass

    def stop(self):
        self.socket.close()
        print('[Evaluation Client] Closed')

# receive from relay laptop
class Server(Process):
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
        connections.put(self.player_num)

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
        while True:
            try:
                msg = self.receive()
                if msg:
                    data = json.loads(msg)

                    if data["D"] == "IMU":
                        if data["P"] == 1:
                            IMU_buffer.put(data)
                        else:
                            IMU_buffer2.put(data)
                    elif data["D"] == "GUN":
                        if data["P"] == 1:
                            GUN_buffer.put(data["P"])
                        else:
                            GUN_buffer2.put(data["P"])
                    else:
                        vest_buffer.put(data)

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

    # Game Engine
    game_engine = GameEngine(curr_state, game_engine_lock)
    # game_engine.start()

    AI_detector1 = AIDetector(1)
    AI_detector2 = AIDetector(2)

    AI_detector1.start()
    AI_detector2.start()

    # start thread for receiving from laptop
    u_server1 = Server(int(port_server1),1)
    u_server2 = Server(int(port_server2),2)

    u_server1.start()
    u_server2.start()

    servers = 0
    while servers < 2:
        while connections.qsize() > 0:
            connections.get()
            servers+=1

    ready = input("Enter when ready to Connect to Eval: ")
    # start ultra96 client to eval server thread
    my_client = Client(ip_addr, port_num, group_id, secret_key)
    my_client.start()



    # receiving from vis
    mqtt_r = MQTTClient('grenade17', 'receive')
    mqtt_r.receive()
    mqtt_r.client.loop_start()
