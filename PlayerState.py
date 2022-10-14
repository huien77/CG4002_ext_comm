class Player:
    def __init__(self, state):
        self.hp = state['hp']
        self.action = state['action']
        self.bullets = state['bullets']
        self.grenades = state['grenades']
        self.shield_time = state['shield_time']
        self.shield_health = state['shield_health']
        self.num_shield = state['num_shield']
        self.num_deaths = state['num_deaths']
        self.bullet_hit = 'no'

#NOTE ammo needs fixing

    def shoot(self):
        # if self.bullets > 0:
        self.action = "shoot"
        # if self.bullets > 0:
        #     self.bullets -= 1
        # else:
        #     self.action = 'none'

    def grenade(self):
        # if self.grenades > 0:
        self.action = "grenade"
        # if self.grenades > 0:
        #     self.grenades -= 1
        # else:
        #     self.action = 'none'

    def shield(self):
        # if self.num_shield > 0:
        self.action = "shield"
        self.shield_health = 30
        # if self.num_shield > 0:
        #     self.num_shield -= 1
        #     self.shield_time = 10
    
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

    def logoutOne(self):
        self.action = "logout"
    
    def logoutTwo(self):
        self.action = "logout"

    def reset(self):
        self.hp = 100
        self.bullets = 6
        self.grenades = 2
        self.num_shield = 3
        self.num_deaths += 1
