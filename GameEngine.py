import json
import threading
import time
from Actions import Actions
from PlayerState import Player

class GameEngine(threading.Thread):
    def __init__(self, player_state):
        super().__init__()
        self.p1 = Player(player_state['p1'])
        self.p2 = Player(player_state['p2'])
        self.player_state = player_state
        self.player_state['p1'] = self.p1.__dict__
        self.player_state['p2'] = self.p2.__dict__

    def performAction(self, action):
        print('[Game Engine] Received action: ', action)

        if action == Actions.shoot:
            self.p1.shoot()
        # elif action == Actions.shoot:
        #     self.p2.shoot()
        

        elif action == Actions.shield:
            self.p1.shield()
        # elif action == Actions.shield:
        #     self.p2.shield
       

        elif action == Actions.grenade:
            self.p1.grenade()
        # elif action == Actions.grenade:
        #     self.p2.grenade()


        elif action == Actions.grenade1:
            self.p2.grenadeDamage()
        # elif action == Actions.grenade2:
        #     self.p1.grenadeDamage()


        #Check if player 1's bullet hit player 2
        elif action == Actions.vest2:
            self.p2.bulletDamage()
            self.p1.bullet_hit = 'yes'
        #Check if player 2's bullet hit player 1
        elif action == Actions.vest1:
            self.p1.bulletDamage()
            self.p2.bullet_hit = 'yes'

        elif action == Actions.reload:
            self.p1.reload()
        # elif action == Actions.reload:
        #     self.p2.reload()

        return self.player_state
