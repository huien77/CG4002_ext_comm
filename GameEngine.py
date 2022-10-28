import json
import threading
import time
import queue
import paho.mqtt.client as mqtt
from Actions import Actions
from PlayerState import Player
from datetime import datetime
from datetime import timedelta

class GameEngine(threading.Thread):
    # KEYS we dont need to send to Eval Server
    non_eval_keys = ['bullet_hit']
    default_non_eval_pairs = [('bullet_hit', 'no'), ('action','none')]
    def __init__(self, player_state):
        super().__init__()
        self.player_state = player_state
        self.p1 = Player(self.player_state['p1'])
        self.p2 = Player(self.player_state['p2'])

        self.end_time = datetime.now()
        
        print('[Game Engine: STARTED \n\n')
    
    def updateFromEval(self, correctedState):
        self.player_state.update(correctedState)
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

        elif action == Actions.vest2:
            self.p2.bulletDamage()
            self.p1.bullet_hit='yes'
        
        elif action == Actions.vest1:
            self.p1.bulletDamage()
            self.p2.bullet_hit='yes'

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
            print("RELOADING???")
            if player_num == 1:
                self.p1.reload()
            else:
                self.p2.reload()

        elif action == Actions.logout:
            if player_num == 1:
                self.p1.logout()
            else:
                self.p2.logout()

        self.player_state['p1'] = self.p1.__dict__
        self.player_state['p2'] = self.p2.__dict__

        return self.player_state
    
    def runLogic(self, state, player_num):
        if player_num == 1:
            player = 'p1'
        elif player_num == 2:
            player = 'p2'
        # stored_bh = [state.get('p1').get('bullet_hit'),state.get('p2').get('bullet_hit')]

        # del state['p1']['bullet_hit']
        # del state['p2']['bullet_hit']
        actionSucess = False
        unrelated_actions = ["logout"]

        watchState = state[player]
        watchedAction = watchState['action']

        if watchedAction == "shield":
            if watchState['num_shield'] > 0 and not (watchState['shield_time'] > 0 and watchState['shield_time'] <= 10):
                watchState['num_shield'] -= 1
                watchState['shield_time'] = 10
                actionSucess = True
                self.end_time = datetime.now()+timedelta(seconds=10)
        elif (watchState['shield_time'] > 0):                        
            time_diff = self.end_time - datetime.now()
            if time_diff.total_seconds() <= 0:
                watchState['shield_time'] = 0
                watchState['shield_health'] = 0
            elif time_diff.total_seconds() > 0:
                watchState['shield_time'] = float(time_diff.total_seconds())

        # If because shield timer will eat the elif up there, and we need to time
        if watchedAction == "shoot":
            if watchState['bullets'] > 0:
                watchState['bullets'] -= 1
                actionSucess = True
        elif watchedAction == "grenade":
            if watchState['grenades'] > 0:
                watchState['grenades'] -= 1
                actionSucess = True
        elif watchedAction == "reload":
            if watchState['bullets'] == 0:
                watchState['bullets'] = 6
                actionSucess = True

        elif watchedAction in unrelated_actions:
            actionSucess = True

        if not actionSucess:
            fail = "fail_"
            watchedAction = fail+watchedAction
            watchState['action'] = watchedAction

        return state, actionSucess

    def checkShieldTimer(self, expected_state, state):
        if expected_state['p1']['action']=="shield":
            if expected_state['p1']['num_shield'] > 0 and not (state['p1']['shield_time'] > 0 and state['p1']['shield_time'] <= 10):
                self.end_time = datetime.now()+timedelta(seconds=10)
    
    def getKey_Values(self, state, playerNum, sKey):
        if playerNum == 0:
            return 'p1', state.get('p1').get(sKey)
        else:
            return 'p2', state.get('p2').get(sKey)

    def saveState(self, state):
        savedKV_pair = []
        for i in range(2):
            player_key_value_pairs = []
            for k in self.non_eval_keys:
                player_key_value_pairs.append(self.getKey_Values(state, i, k))
            savedKV_pair.append(player_key_value_pairs)
        return savedKV_pair
    
    def updateStates(self, savedKV_pair):
        players = [self.p1, self.p2]
        for i in range(len(savedKV_pair)):
            players[i].update(savedKV_pair[i])

        self.player_state['p1'] = self.p1.__dict__
        self.player_state['p2'] = self.p2.__dict__
    
    def prepForEval(self, state, player_num, actionSucess):
        for k in self.non_eval_keys:
            for p in ['p1', 'p2']:
                state[p].pop(k)
        if not actionSucess:
            if player_num == 1:
                state['p1']['action'] = state['p1']['action'][5:]
            elif player_num == 2:
                state['p2']['action'] = state['p1']['action'][5:]

        # self.player_state['p1'] = self.p1.__dict__
        # self.player_state['p2'] = self.p2.__dict__
        return state
    
    def resetValues(self, state):
        # for k in self.non_eval_keys:
        state['p1'].update(self.default_non_eval_pairs)
        state['p2'].update(self.default_non_eval_pairs)
        return state
