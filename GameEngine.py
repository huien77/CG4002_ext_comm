import json
import threading
from Actions import Actions

class GameEngine(threading.Thread):
    def __init__(self, player_state, action1, grenade1, bullet1):
        self.p1 = Player(player_state['p1'])
        self.p2 = Player(player_state['p2'])
        self.action1 = action1
        self.bullet1 = bullet1
        self.grenade1 = grenade1
        print('[Game Engine] Received from AI and relay node')

    def performAction(self, action, grenade, bullet):    
        if action == Actions.shoot:
            self.p1.shoot()
##        elif action == Actions.shoot:
##            self.p1.shoot()
##
##            if json["p2"]["bullet_hit"]:
##                self.p1.bulletDamage()
##        
        elif action == Actions.shield:
            self.p1.shield
##        elif action == Actions.shield:
##            self.p2.shield
##        
        elif action == Actions.grenade:
            self.p1.grenade
            if json["p1"]["grenade_hit"]:
                self.p2.grenadeDamage()
##        elif p2_action == Actions.grenade:
##            self.p2.grenade
##            if json["p2"]["grenade_hit"]:
##                self.p1.grenadeDamage()
##        
        elif p1_action == Actions.logout:
            self.data["p1"]["action"] = "logout"
            self.data["p2"]["action"] = "logout"
    
    
    def write_to_Json(self):
        return json.dumps(self.data)

    def run(self):
        while len(self.action):
            performAction(self.action)
            self.action = ''
            
        
