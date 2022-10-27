import json
import threading
import time
import queue
import paho.mqtt.client as mqtt
from Actions import Actions
from PlayerState import Player
from datetime import datetime
from datetime import timedelta

# # send to visualizer buffer
# vis_send_buffer = queue.Queue()
# vis_send_lock = threading.Lock()

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

        self.end_time = datetime.now()
        
        print('[Game Engine: STARTED \n\n')
    
    def updateFromEval(self, correctedState):
        self.player_state = correctedState
        self.p1 = Player(self.player_state['p1'])
        self.p2 = Player(self.player_state['p2'])

    def performAction(self, action, player_num):
        print('[Game Engine] Received action: ', action)

        # Version 0: Assume DEFINITE HITS
        if action == Actions.shoot:
            if player_num == 1:
                self.p1.shoot()
                self.p2.bulletDamage()
                self.p1.bullet_hit = 'yes'
            else:
                self.p2.shoot()
                self.p1.bulletDamage()
                self.p2.bullet_hit = 'yes'

        if action == Actions.vest2:
            self.p2.bulletDamage()
            self.p1.bullet_hit='yes'

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
    
    def runLogic(self, state):
        print("SHOTS? ", state.get('p1').get('bullet_hit'))
        stored_bh = [state.get('p1').get('bullet_hit'),state.get('p2').get('bullet_hit')]

        del state['p1']['bullet_hit']
        del state['p2']['bullet_hit']

        freshchg = False
        unrelated_actions = ["logout", "reload"]
        if state['p1']['action'] == "shield":
            if state['p1']['num_shield'] > 0 and not (state['p1']['shield_time'] > 0 and state['p1']['shield_time'] <= 10):
                state['p1']['num_shield'] -= 1
                state['p1']['shield_time'] = 10
                freshchg = True
                self.end_time = datetime.now()+timedelta(seconds=10)
                # state['p1']['action'] = "none"
        elif (state['p1']['shield_time'] > 0):                        
            # if (datetime.now().second == start_time):
            time_diff = self.end_time - datetime.now()
            if time_diff.total_seconds() <= 0:
                state['p1']['shield_time'] = 0
                state['p1']['shield_health'] = 0
            elif time_diff.total_seconds() > 0:
                state['p1']['shield_time'] = float(time_diff.total_seconds())

        if state['p1']['action'] == "shoot":
            if state['p1']['bullets'] > 0:
                state['p1']['bullets'] -= 1
                freshchg = True
                # state['p1']['action'] = "none"
        elif state['p1']['action'] == "grenade":
            if state['p1']['grenades'] > 0:
                state['p1']['grenades'] -= 1
                freshchg = True
                # state['p1']['action'] = "none"

        elif state['p1']['action'] in unrelated_actions:
            freshchg = True

        return state, freshchg, stored_bh

    def checkShieldTimer(self, expected_state):
        if expected_state['p1']['action']=="shield":
            if expected_state['p1']['num_shield'] > 0 and not (state['p1']['shield_time'] > 0 and state['p1']['shield_time'] <= 10):
                self.end_time = datetime.now()+timedelta(seconds=10)

    def restoreValues(self, state, freshchg, stored_bh):
        ### AFTER SEND DATA LOGIC!!!
        state['p1']['bullet_hit'] = stored_bh[0]
        state['p2']['bullet_hit'] = stored_bh[1]

        if not freshchg:
            state['p1']['action'] = "none"
        return state
    
    def resetValues(self, state):
        state['p1']['bullet_hit'] = "no"
        state['p2']['bullet_hit'] = "no"
        return state

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
