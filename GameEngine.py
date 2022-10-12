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
##        elif action == Actions.shoot:
##            self.p1.shoot()
##
##            if json["p2"]["bullet_hit"]:
##                self.p1.bulletDamage()
##        
        elif action == Actions.shield:
            self.p1.shield()
##        elif action == Actions.shield:
##            self.p2.shield
##        
        elif action == Actions.grenade:
            self.p1.grenade()
##        elif p2_action == Actions.grenade:
##            self.p2.grenade
##            if json["p2"]["grenade_hit"]:
##                self.p1.grenadeDamage()

        elif action == Actions.grenade1:
            self.p2.grenadeDamage()

        elif action == Actions.reload:
            self.p1.reload()

        return self.player_state
