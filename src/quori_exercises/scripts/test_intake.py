#This is the file to run to start the intake proccess

#!/usr/bin/env python3
# import rospy
# import rosbag
#from config import *
#from ExerciseController import ExerciseController
from datetime import datetime
#from pytz import timezone
from intake_messages import *
import logging
import time
import terminal_input as ti
import os
from gtts import gTTS
import speech as sp
from pynput import keyboard

def on_press(key):
    try:
        logger2.info(f'Key {key.char} pressed')
        return
        
    except AttributeError:
        logger2.info(f'Special key {key} pressed')
        return


def get_message():
    key=ti.get_key()
    logger.info('Key, {}'.format(key))

    key_specific=ti.get_terminal_input(key)
    if key_specific=="back":
        logger.info('Key Specific, {}'.format(key_specific))
        return get_message()
    elif key_specific=="quit":
        logger.info('Quit')
        return "quit"
       
    logger.info('Key Specific, {}'.format(key_specific))

        
    return INTAKE_MESSAGES[key][key_specific]

#Change at the beginning of each session
PARTICIPANT_ID = '1'

folder_path = '/Users/raynahata/Desktop/Github/quori_ros_rayna/src/quori_exercises/intake_logs/' 
if not os.path.exists(folder_path): 
    os.makedirs(folder_path) 

#Start log file
intake_log_filename= 'Intake_{}.csv'.format(datetime.now().strftime("%Y-%m-%d--%H-%M-%S"))
log_fname = os.path.join(folder_path, intake_log_filename)

keylog_filename= 'keypress_{}.csv'.format(datetime.now().strftime("%Y-%m-%d--%H-%M-%S"))
key_log_fname = os.path.join(folder_path, keylog_filename)


#Initialize logging
logger = logging.getLogger('logging')
logger2 = logging.getLogger('keypress')
logger.setLevel(logging.DEBUG)
logger2.setLevel(logging.DEBUG)
fh = logging.FileHandler(format(log_fname))
fh2 = logging.FileHandler(format(key_log_fname))
fh.setLevel(logging.DEBUG)
fh2.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter=logging.Formatter(
    fmt='%(asctime)s.%(msecs)03d,%(message)s',
    datefmt='%Y-%m-%d,%H:%M:%S'
)

fh.setFormatter(formatter)
fh2.setFormatter(formatter)
ch.setFormatter(formatter)
logger.addHandler(fh)
logger2.addHandler(fh2)

             
done_intake = False

#accessing the terminal input 
logger.info('Begin, {}'.format('Starting intake'))
logger2.info('Begin, {}'.format('Starting intake'))
print("starting intake")

#start the keyboard
listener = keyboard.Listener(on_press=on_press)
listener.start()


while not done_intake:
    message=get_message()

    if message == "quit":
        done_intake=True
        logger.info('Quit')
        break
    print(message)
    speak=input("Press enter to speak, else type b to go back")
    if speak == "":
        print("Begin speaking")
        logger.info('Begin speaking,{}'.format(message))
        sp.text_to_speech(message)
        logger.info('End speaking')
        print("End speaking")
        
    elif speak=="b":
        continue


    
    cont=input("Quit or Continue?")
    if cont=="q":
        done_intake=True
        logger.info('Quit')
    elif cont=="":
        logger.info('Continue')
        continue
   

listener.stop()
logger.handlers.clear()
logging.shutdown()
print('Done!')


