#!/usr/bin/env python3

import os
import time
import rospy
from std_msgs.msg import String
from openai import OpenAI

print("SCRIPT STARTED")


class ChatBridge:

    def __init__(self):

        print("INIT START")

        rospy.init_node("chat_bridge")
        print("ROS INIT OK")

        # Topic setup
        self.speech_topic = "/google_sr"
        self.tts_topic = "/gtts_input"

        self.pub = rospy.Publisher(self.tts_topic, String, queue_size=10)
        rospy.Subscriber(self.speech_topic, String, self.callback)

        # Duplicate prevention
        self.last_text = ""

        # Conversation memory
        self.messages = [
            {
                "role": "system",
                "content": (
                    "You are JungleBot, a friendly jungle guide. "
                    "Your output is spoken by a text-to-speech system. "
                    "Do NOT use markdown, asterisks, symbols, or formatting. "
                    "Speak only in natural plain sentences. "
                    "Keep responses under 20 words."
                )
            }
        ]

        # OpenAI init with full error capture
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            print("API KEY LOADED:", bool(api_key))

            self.client = OpenAI(api_key=api_key)

            print("OPENAI CLIENT OK")

        except Exception as e:
            print("OPENAI INIT FAILED:", repr(e))
            raise

        print("INIT COMPLETE")

    def callback(self, msg):

        print("CALLBACK TRIGGERED")

        # Ignore robot self speech
        if rospy.get_param("/robot_speaking", False):
            print("IGNORED: robot currently speaking")
            return

        user_text = msg.data.strip()

        if not user_text:
            print("EMPTY INPUT IGNORED")
            return

        if user_text == self.last_text:
            print("DUPLICATE IGNORED:", user_text)
            return

        self.last_text = user_text

        print("USER TEXT:", user_text)

        try:
            self.messages.append({
                "role": "user",
                "content": user_text
            })

            self.messages = self.messages[-10:]

            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=self.messages
            )

            reply = response.choices[0].message.content.strip()

            reply = reply.replace("*", "")
            reply = reply.replace("#", "")
            reply = " ".join(reply.split()[:20])

            self.messages.append({
                "role": "assistant",
                "content": reply
            })

            print("GPT REPLY:", reply)

            # ===== MUTING ENABLED HERE =====
            rospy.set_param("/robot_speaking", True)

            self.pub.publish(reply)

            # small delay so STT doesn't immediately re-capture tail of speech
            time.sleep(0.5)

            rospy.set_param("/robot_speaking", False)
            # ===============================

        except Exception as e:
            print("OPENAI CALLBACK ERROR:", repr(e))
            rospy.logerr(f"OpenAI error: {e}")

            fallback = "Sorry, I could not process that."

            rospy.set_param("/robot_speaking", True)
            self.pub.publish(fallback)
            time.sleep(0.5)
            rospy.set_param("/robot_speaking", False)


if __name__ == "__main__":

    print("NODE BOOTING")

    try:
        ChatBridge()
        print("NODE RUNNING")
        rospy.spin()

    except Exception as e:
        print("FATAL CRASH:", repr(e))