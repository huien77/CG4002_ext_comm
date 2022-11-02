import threading
from Actions import Actions
from PlayerState import Player
from datetime import datetime
from datetime import timedelta

class GameEngine():
    # KEYS we dont need to send to Eval Server
    default_non_eval_pairs = [('action','none')]
    def __init__(self, player_state):
        super().__init__()
        self.player_state = {}
        self.player_state.update(player_state)
        self.p1 = Player(self.player_state['p1'])
        self.p2 = Player(self.player_state['p2'])

        self.eval_state = {}
        self.eval_state.update(player_state)
        self.e1 = Player(self.player_state['p1'])
        self.e2 = Player(self.player_state['p2'])

        self.end_time1 = datetime.now()
        self.end_time2 = datetime.now()
        
        print('[Game Engine: STARTED]')
    
    def updateFromEval(self, correctedState):
        self.player_state.update(correctedState)
        self.eval_state.update(correctedState)

        self.p1 = Player(self.player_state['p1'])
        self.p2 = Player(self.player_state['p2'])

        self.e1 = Player(self.eval_state['p1'])
        self.e2 = Player(self.eval_state['p2'])

        print("[GAME ENGINE]: UPDATED", self.eval_state)

    def updatePlayerState(self, curr_state):
        self.player_state.update(curr_state)

        self.p1 = Player(self.player_state['p1'])
        self.p2 = Player(self.player_state['p2'])

    def performAction(self, action, player_num=1, eval=False):
        if eval:
            main1 = self.e1
            main2 = self.e2
        else:
            main1 = self.p1
            main2 = self.p2

        if player_num == 1:
            print("\033[35m", end="")
        else:
            print("\033[33m", end="")
        
        # Version 0: Assume DEFINITE HITS
        if action == Actions.shoot:
            if player_num == 1:
                main1.shoot()
            else:
                main2.shoot()

        elif action == Actions.vest2:
            print("\033[35m", end="")
            main2.bulletDamage()
        
        elif action == Actions.vest1:
            print("\033[33m", end="")
            main1.bulletDamage()

        elif action == Actions.grenade1:
            print("\033[35m", end="")
            main2.grenadeDamage()
        
        elif action == Actions.grenade2:
            print("\033[33m", end="")
            main1.grenadeDamage()

        elif action == Actions.shield:
            if player_num == 1:
                main1.shield()
            else:
                main2.shield()

        elif action == Actions.grenade:
            if player_num == 1:
                main1.grenade()
            else:
                main2.grenade()

        elif action == Actions.reload:
            if player_num == 1:
                main1.reload()
            else:
                main2.reload()

        elif action == Actions.logout:
            if player_num == 1:
                main1.logout()
            else:
                main2.logout()
        print('[Game Engine] Performed action:', action, 'by player', player_num, end="\033[0m\n")
        if eval:
            self.e1 = main1
            self.e2 = main2
            self.eval_state['p1'] = main1.__dict__
            self.eval_state['p2'] = main2.__dict__
            return self.eval_state
        else:
            self.p1 = main1
            self.p2 = main2
            self.player_state['p1'] = main1.__dict__
            self.player_state['p2'] = main2.__dict__
            return self.player_state

    def runLogic(self, player_num, eval=False):
        if eval:
            state = self.eval_state
        else:
            state = self.player_state
        
        print("[GameEngine]: State is {}".format(state))

        if player_num == 1:
            player = 'p1'
        elif player_num == 2:
            player = 'p2'
        actionSucess = False

        # Logout does not have fail case
        unrelated_actions = ["logout"]

        watchState = state[player]
        watchedAction = watchState['action']

        if watchedAction == "shield":
            # Check that there are shields and no shields are active
            if watchState['num_shield'] > 0 and not (watchState['shield_time'] > 0 and watchState['shield_time'] <= 10):
                watchState['num_shield'] -= 1
                watchState['shield_time'] = 10
                watchState['shield_health'] = 30
                actionSucess = True
                if player_num == 1:
                    self.end_time1 = datetime.now()+timedelta(seconds=10)
                else:
                    self.end_time2 = datetime.now()+timedelta(seconds=10)

        # This function checks whenever action is not shield for the shield TIMER
        # Not called when shield is instantiated for eval server
        elif (watchState['shield_time'] > 0):
            if player_num == 1:
                time_diff = self.end_time1 - datetime.now()
            else:
                time_diff = self.end_time2 - datetime.now()
            if time_diff.total_seconds() <= 0:
                watchState['shield_time'] = 0
                watchState['shield_health'] = 0
            elif time_diff.total_seconds() > 0:
                watchState['shield_time'] = float(time_diff.total_seconds())

        # Not elif > TIMER check used elif and we still want to check actions
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
            actionSucess = True     # Set to True as will not fail

        if not actionSucess:
            fail = "fail_"
            watchedAction = fail+watchedAction
            watchState['action'] = watchedAction
        
        print("[GAME ENGINE]: END LOGIC STATE: ", state)
        print(self.eval_state)
        return state

    def checkShieldTimer(self, expected_state):
        for p in ['p1', 'p2']:
            if expected_state[p]['action']=="shield":
                if expected_state[p]['num_shield'] > 0 and not (self.eval_state[p]['shield_time'] > 0 and self.eval_state[p]['shield_time'] <= 10):
                    if ['p1', 'p2'].index(p) == 1:
                        self.end_time1 = datetime.now()+timedelta(seconds=10)
                    else:
                        self.end_time2 = datetime.now()+timedelta(seconds=10)
    
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
    
    def prepForEval(self):
        for p in ['p1', 'p2']:
            if self.eval_state[p]['action'][:5] == "fail_":
                print("REMOVING FAIL from ", p, self.eval_state[p]['action'])
                self.eval_state[p]['action'] = self.eval_state[p]['action'][5:]
                print("NEW action of ", p, self.eval_state[p]['action'])

        print("[GAME_ENGINE] State After Prep: \n", self.eval_state)
        return self.eval_state
    
    def resetValues(self, eval=False):
        if eval:
            self.eval_state['p1'].update(self.default_non_eval_pairs)
            self.eval_state['p2'].update(self.default_non_eval_pairs)
            return self.eval_state
        else:
            self.player_state['p1'].update(self.default_non_eval_pairs)
            self.player_state['p2'].update(self.default_non_eval_pairs)
            return self.player_state
    
    def readGameState(self, eval=False):
        if eval:
            return self.eval_state
        else:
            return self.player_state
