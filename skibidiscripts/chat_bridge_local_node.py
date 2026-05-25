#!/usr/bin/env python3

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

        # Local Ollama Client Setup
        try:
            # Connects directly to the local server running on your machine
            self.local_client = OpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama"  # Required by the SDK framework, but ignored by Ollama
            )
            print("LOCAL OLLAMA CLIENT OK")
        except Exception as e:
            print("OLLAMA INIT FAILED:", repr(e))
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

        self.messages.append({
            "role": "user",
            "content": user_text
        })
        self.messages = self.messages[-10:]

        # --- STEP 1: QUERY LOCAL OLLAMA ---
        try:
            print("Attempting Local Ollama (llama3.2:1b)...")
            response = self.local_client.chat.completions.create(
                model="llama3.2:1b",
                messages=self.messages
            )
            reply = response.choices[0].message.content.strip()
            print("SUCCESS: Local Ollama Replied")
            
        except Exception as local_err:
            print("FATAL: Local model failed!", repr(local_err))
            rospy.logerr(f"Local LLM generation failed: {local_err}")
            reply = "Sorry, I could not process that."

        # --- STEP 2: CLEAN RESPONSE & PUBLISH ---
        try:
            reply = reply.replace("*", "")
            reply = reply.replace("#", "")
            reply = " ".join(reply.split()[:20])

            self.messages.append({
                "role": "assistant",
                "content": reply
            })

            print("FINAL REPLY:", reply)

            # ===== MUTING ENABLED HERE =====
            rospy.set_param("/robot_speaking", True)
            self.pub.publish(reply)

            # small delay so STT doesn't immediately re-capture tail of speech
            time.sleep(0.5)
            rospy.set_param("/robot_speaking", False)
            # ===============================

        except Exception as e:
            print("CRITICAL ERROR IN POST-PROCESSING:", repr(e))


if __name__ == "__main__":
    print("NODE BOOTING")
    try:
        ChatBridge()
        print("NODE RUNNING")
        rospy.spin()
    except Exception as e:
        print("FATAL CRASH:", repr(e))