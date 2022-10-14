import json
import threading
import time
import queue
from Actions import Actions
from PlayerState import Player
from ultra96 import MQTTClient
from datetime import datetime
from datetime import timedelta

# send to visualizer buffer
vis_send_buffer = queue.Queue()
vis_send_lock = threading.Lock()

def input_data(buffer, lock, data):
    lock.acquire()
    buffer.put(data)
    lock.release()

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
        return self.player_state

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
