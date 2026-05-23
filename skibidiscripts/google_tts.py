#!/usr/bin/env python
import rospy
from std_msgs.msg import String
from gtts import gTTS
import os

def callback(data):
    # Display received inpout
    rospy.loginfo("Input: %s", data.data)

    # Pass to Google TTS 
    text = data.data
    tts = gTTS(text, lang='en')
    
    # Save audio and play
    tts.save("speech.mp3")
    os.system("mpg321 speech.mp3")
    os.remove("speech.mp3")
    
def googletts():
    rospy.init_node('googletts', anonymous=True)

    rospy.Subscriber("gtts_input", String, callback)

    rospy.spin()

if __name__ == '__main__':
    googletts()
