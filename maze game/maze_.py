import turtle
import math
import random

wn = turtle.Screen()
wn.bgcolor("black")
wn.title('a maze game')
wn.setup(700,700)
wn.tracer(0)
#register shapes
#turtle.register_shape("wizzr.gif")
#turtle.register_shape("wizzl.gif")
#turtle.register_shape("loot.gif")
#turtle.register_shape("wall.gif")
images = ["wizzr.gif","wizzl.gif","loot.gif","enemy.gif","wall.gif"]
for image in images:
    turtle.register_shape(image)

#create pen
class Pen(turtle.Turtle):
    def __init__(self):
        turtle.Turtle.__init__(self)
        self.shape("square")
        self.color("white")
        self.penup()
        self.speed(0)

class Player(turtle.Turtle):
    def __init__(self):
        turtle.Turtle.__init__(self)
        self.shape("wizzr.gif")
        self.color('blue')
        self.penup()
        self.speed(0)
        self.gold = 0

    def go_up(self):
        #calc the spot to move to
        move_to_x = player.xcor()
        move_to_y = player.ycor() + 24
    
        #check if the space has a wall
        if (move_to_x,move_to_y) not in walls:
            self.goto(move_to_x,move_to_y)
                        
    def go_down(self):
        #calc the spot to move to
        move_to_x = player.xcor()
        move_to_y = player.ycor() - 24
    
        #check if the space has a wall
        if (move_to_x,move_to_y) not in walls:
            self.goto(move_to_x,move_to_y)
                     
    def go_left(self):
        #calc the spot to move to
        move_to_x = player.xcor() - 24
        move_to_y = player.ycor() 

        self.shape("wizzl.gif")
    
        #check if the space has a wall
        if (move_to_x,move_to_y) not in walls:
            self.goto(move_to_x,move_to_y)
    def go_right(self):
        #calc the spot to move to
        move_to_x = player.xcor() + 24
        move_to_y = player.ycor() 
        
        self.shape("wizzr.gif")

        #check if the space has a wall
        if (move_to_x,move_to_y) not in walls:
            self.goto(move_to_x,move_to_y)

    def is_collision(self,other):
        a = self.xcor() - other.xcor()
        b = self.ycor() - other.ycor()
        distance = math.sqrt((a**2) + (b**2))
        if distance < 5:
            return True
        else:
            return False    

class Treasure(turtle.Turtle):
    def __init__(self,x,y):
        turtle.Turtle.__init__(self)
        self.shape("loot.gif")
        self.color('gold')
        self.penup()
        self.speed(0)
        self.gold = 100
        self.goto(x,y)

    def destroy(self):
        self.goto(2000,2000)
        self.hideturtle()    


class Enemy(turtle.Turtle):
    def __init__(self,x,y):
        turtle.Turtle.__init__(self)
        self.shape("enemy.gif")
        self.color('red')
        self.penup()
        self.speed(0)
        self.gold = 25
        self.goto(x,y)
        self.direction = random.choice(["up","down","left","right"])

    def move(self):
        if self.direction == "up":
            dx = 0
            dy = 24
        elif self.direction == "down":
            dx = 0
            dy = -24
        elif self.direction == "left":
            dx = -24
            dy = 0
            self.shape("enemy.gif")
        elif self.direction == "right":
            dx = 24
            dy = 0
            self.shape("enemy.gif")
        else:
             dx = 0
             dy = 0

        if self.is_close(player):
            if player.xcor() < self.xcor():
                self.direction = "left"
            elif player.xcor() > self.xcor():
                self.direction = "right"
            elif player.ycor() > self.ycor():
                self.direction = "up"
            elif player.ycor() < self.ycor():
                self.direction = "down"         




        #calc the spot to move to
        move_to_x = self.xcor() + dx
        move_to_y = self.ycor() + dy
 
        #check if the space has a wall
        if (move_to_x,move_to_y) not in walls:
            self.goto(move_to_x,move_to_y)
        else:
            self.direction = random.choice(["up","down","left","right"]) 

        #set timer to move next time
        turtle.ontimer(self.move,t=random.randint(100,300))

    def is_close(self,other):
        a = self.xcor() - other.xcor()
        b = self.ycor() - other.ycor()
        distance = math.sqrt((a**2) + (b**2))

        if distance <75:
            return True
        else:
            return False    

    def destroy(self):
        self.goto(2000,2000)
        self.hideturtle()

#create levels list
levels = [""]
level_1 = [
    "XXXXXXXXXXXXXXXXXXXXXXXXX",
    "XP XXXXXXX     E    XXXXX",
    "X  XXXXXXX  XXXXXX  XXXXX",
    "X       XX  XXXXXX  XXXXX",
    "X       XX  XXX        XX",
    "XXXXXX  XX  XXX        XX",
    "XXXXXX  XX  XXXXXX  XXXXX",
    "XXXXXX  XX    XXXX  XXXXX",
    "X  XXX        XXXX TXXXXX",
    "X  XXX  XXXXXXXXXXXXXXXXX",
    "X         XXXXXXXXXXXXXXX",
    "X                XXXXXXXX",
    "XXXXXXXXXXXX     XXXXX  X",
    "XXXXXXXXXXXXXXX  XXXXX  X",
    "XXX  XXXXXXXXXX         X",
    "XXX          E          X",
    "XXX         XXXXXXXXXXXXX",
    "XXXXXXXXXX  XXXXXXXXXXXXX",
    "XXXXXXXXXX              X",
    "XX   XXXXX          E   X",
    "XX   XXXXXXXXXXXXX  XXXXX",
    "XX    XXXXXXXXXXXX  XXXXX",
    "XX   E      XXXX        X",
    "XXXX                    X",
    "XXXXXXXXXXXXXXXXXXXXXXXXX"

]        

#add a treasure list
treasures = []

#add enemies list
enemies = []

#add maze to maze list
levels.append(level_1)

#create level setup function
def setup_maze(level):
    for y in range(len(level)):
        for x in range(len(level[y])):
            #get thec character at each x,y coordinate
            #note the order of y and x in next line
            character = level[y][x]
            #calculate the screen x,y coordinates;
            screen_x = -288 + (x*24)
            screen_y =  288 - (y*24)

            #check if its a X
            if character =='X':
                pen.goto(screen_x,screen_y)
                pen.shape('wall.gif')
                pen.stamp()
                #add coordinates to wall list
                walls.append((screen_x,screen_y))

            if character == 'P':
                player.goto(screen_x,screen_y)
                  
            if character == 'T':
                treasures.append(Treasure(screen_x,screen_y))

            if character == 'E':
                enemies.append(Enemy(screen_x,screen_y))


#create class instance
pen = Pen()
player = Player()

#create wall coordinate list
walls = []

#setup level
setup_maze(levels[1])

#print(walls)
#ketboard bindings
turtle.listen()
turtle.onkey(player.go_left,'Left')
turtle.onkey(player.go_right,'Right')
turtle.onkey(player.go_up,'Up')
turtle.onkey(player.go_down,'Down')

#turn off screen updates
wn.tracer(0)

#start moving enemies
for enemy in enemies:
    turtle.ontimer(enemy.move,t=250)
    
canvas = turtle.getcanvas()
root = canvas.winfo_toplevel()
running = True

def on_close():
    global running
    running = False

root.protocol("WM_DELETE_WINDOW", on_close)



while True:
    #check for player collision with treasure:
    #iterate through treasure list

    
    
    for treasure in treasures:
        if player.is_collision(treasure):
            #add trasure gold to player gold
            player.gold += treasure.gold
            print("player Gold:{}".format(player.gold))
            treasure.destroy()
            #remove the treasure from treasure list
            treasures.remove(treasure)

    for enemy in enemies:
        if player.is_collision(enemy):
            print("player dies!")

    #update screen
          
    wn.update()
