class Player:
    def __init__(self, state, player):
        self.fullstate = state
        selfstate = state[player]
        self.player = player
        self.hp = selfstate['hp']
        self.action = selfstate['action']
        self.bullets = selfstate['bullets']
        self.grenades = selfstate['grenades']
        self.shield_time = selfstate['shield_time']
        self.shield_health = selfstate['shield_health']
        self.num_shield = selfstate['num_shield']
        self.num_deaths = selfstate['num_deaths']
        self.bullet_hit = selfstate['bullet_hit']
            
    def shoot(self,enemy):
        if self.bullets > 0:
            self.action = "shoot"
            self.bullets -= 1
            if self.fullstate[enemy.player]['bullet_hit']=="yes":
                return True
            else: return False
                # NOTE for now Self too for them resets

        else:
            self.action = ''

    def grenade(self):
        if self.grenades > 0:
            self.action = "grenade"
            self.grenades -= 1
        else:
            self.action = ''

    
    def shield(self):
        if self.num_shield > 0:
            self.action = "shield"
            self.shield_health = 30
            self.num_shield -= 1
            self.shield_time = 10
    
    def reload(self):
        self.action = "reload"
        self.bullets = 6

    def takeDamage(self, damage):
        if self.shield_health > 0:
            self.shield_health -= damage
            if self.shield_health < 0:
                self.hp += self.shield_health
        else:
            self.hp -= damage

        if self.hp <= 0:
            self.reset()

    def bulletDamage(self):
        self.takeDamage(10)

    def grenadeDamage(self):
        self.takeDamage(30)

    def reset(self):
        self.hp = 100
        self.bullets = 6
        self.grenades = 2
        self.num_shield = 3
        self.num_deaths += 1
