import json
import threading
import time
import queue
import paho.mqtt.client as mqtt
import copy
from Actions import Actions
from PlayerState import Player
from datetime import datetime
from datetime import timedelta

# send to visualizer buffer
vis_send_buffer = []
vis_send_lock = threading.Lock()

def read_data(buffer, lock):
    lock.acquire()
    data = buffer.pop(0)
    lock.release()
    return data

def input_data(buffer, lock, data):
    lock.acquire()
    buffer.append(data)
    lock.release()

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

    def stop(self):
        self.client.unsubscribe()
        self.client.loop_stop()
        self.client.disconnect()

class GameEngine(threading.Thread):
    def __init__(self, player_state):
        super().__init__()
        self.player_state = player_state
        self.p1 = Player(self.player_state['p1'])
        self.p2 = Player(self.player_state['p2'])
        
        self.mqtt_p = MQTTClient('visualizer17', 'publish')
        self.mqtt_p.client.loop_start()

    def performAction(self, action):
        print('[Game Engine] Received action: ', action)

        if action == Actions.shoot:
            self.p1.shoot()
            self.p2.bulletDamage()
            self.p1.bullet_hit = 'yes'

        elif action == Actions.shield:
            self.p1.shield()

        elif action == Actions.grenade:
            self.p1.grenade()
            self.p2.grenadeDamage()

        elif action == Actions.reload:
            self.p1.reload()

        # check if player 1' grenade hit player 2
        # elif action == Actions.grenade1:
        #     self.p2.grenadeDamage()

        # check if player 1's bullet hit player 2
        # elif action == Actions.vest2:
        #     self.p2.bulletDamage()
        #     self.p1.bullet_hit = 'yes'

        # check if player 2's bullet hit player 1
        # elif action == Actions.vest1:
        #     self.p1.bulletDamage()
        #     self.p2.bullet_hit = 'yes'

        self.player_state['p1'] = self.p1.__dict__
        self.player_state['p2'] = self.p2.__dict__

        new_state = copy.deepcopy(self.player_state)
        del new_state['p1']['bullet_hit']
        del new_state['p2']['bullet_hit']

        return new_state

    def run(self):
        # need to decrement the shield timer
        if (self.p1.shield_time > 0):
            delayed1_time = datetime.now() + timedelta(seconds = 1)
            delayed10_time = datetime.now() + timedelta(seconds = 10)
            
            if (datetime.now() == delayed1_time):
                self.p1.shield_time -= 1
            if self.p1.shield_time == 0:
                input_data(vis_send_buffer, vis_send_lock, self.player_state)
                
                if (datetime.now() == delayed10_time): 
                    self.mqtt_p.publish()
