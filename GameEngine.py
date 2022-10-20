import json
import threading
import time
import queue
import paho.mqtt.client as mqtt
from Actions import Actions
from PlayerState import Player
from datetime import datetime
from datetime import timedelta

# send to visualizer buffer
vis_send_buffer = queue.Queue()
vis_send_lock = threading.Lock()

# class MQTTClient():
#     def __init__(self, topic, client_name):
#         self.topic = topic
#         self.client = mqtt.Client(client_name)
#         self.client.connect('test.mosquitto.org')
#         self.client.subscribe(self.topic)

#     # publish message to topic
#     def publish(self):
#         if vis_send_buffer.qsize() > 0:
#             state = vis_send_buffer.get_nowait()
#             message = json.dumps(state)
#             # publishing message to topic
#             self.client.publish(self.topic, message, qos = 1)

#     def stop(self):
#         self.client.unsubscribe()
#         self.client.loop_stop()
#         self.client.disconnect()

class GameEngine(threading.Thread):
    def __init__(self, player_state):
        super().__init__()
        self.player_state = player_state
        self.p1 = Player(self.player_state['p1'])
        self.p2 = Player(self.player_state['p2'])
        
        print('[Game Engine: STARTED \n\n')
    
    def updateFromEval(self, correctedState):
        self.player_state = correctedState
        self.p1 = Player(self.player_state['p1'])
        self.p2 = Player(self.player_state['p2'])

    def performAction(self, action, player_num):
        print('[Game Engine] Received action: ', action)

        if action == Actions.shoot:
            if player_num == 1:
                self.p1.shoot()
                self.p2.bulletDamage()
                self.p1.bullet_hit = 'yes'
            else:
                self.p2.shoot()
                self.p1.bulletDamage()
                self.p2.bullet_hit = 'yes'

        elif action == Actions.shield:
            if player_num == 1:
                self.p1.shield()
            else:
                self.p2.shield()

        elif action == Actions.grenade:
            if player_num == 1:
                self.p1.grenade()
                self.p2.grenadeDamage()
            else:
                self.p2.grenade()
                self.p1.grenadeDamage()

        elif action == Actions.reload:
            if player_num == 1:
                self.p1.reload()
            else:
                self.p2.reload()

        elif action == Actions.logout:
            if player_num == 1:
                self.p1.logoutOne()
            else:
                self.p2.logoutTwo()

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

        # self.mqtt_p.publish()

        # new_state = copy.deepcopy(self.player_state)
        # del new_state['p1']['bullet_hit']
        # del new_state['p2']['bullet_hit']

        return self.player_state

    # def run(self):
    #     # self.mqtt_p = MQTTClient('visualizer17', 'publish')
    #     # self.mqtt_p.client.loop_start()

    #     need to decrement the shield timer
    #     if (self.p1.shield_time > 0):
    #         delayed1_time = datetime.now() + timedelta(seconds = 1)
    #         delayed10_time = datetime.now() + timedelta(seconds = 10)
            
    #         if (datetime.now() == delayed1_time):
    #             self.p1.shield_time -= 1
    #         if self.p1.shield_time == 0:
    #             vis_send_buffer.put_nowait(self.player_state)
                
    #             if (datetime.now() == delayed10_time): 
    #                 self.mqtt_p.publish()
