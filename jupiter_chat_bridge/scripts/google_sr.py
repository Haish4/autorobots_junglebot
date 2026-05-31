#!/usr/bin/env python
import rospy
from std_msgs.msg import String
import speech_recognition as sr
import time


class GoogleSpeechNode:
    def __init__(self):
        rospy.init_node("googlesr", anonymous=True)

        self.pub = rospy.Publisher("google_sr", String, queue_size=10)

        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

        self.last_result = ""
        self.last_publish_time = 0

        self.min_publish_interval = 1.5  # seconds

        rospy.loginfo("Google SR node started")

    def run(self):
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)

        while not rospy.is_shutdown():
            try:

                # ==========================
                # MUTING GATE (IMPORTANT)
                # ==========================
                if rospy.get_param("/robot_speaking", False):
                    rospy.loginfo("Muted: robot is speaking")
                    time.sleep(0.2)
                    continue

                with self.microphone as source:
                    rospy.loginfo("Listening...")
                    audio = self.recognizer.listen(
                        source,
                        timeout=5,
                        phrase_time_limit=5
                    )

                try:
                    result = self.recognizer.recognize_google(audio)
                    result = result.strip()

                    rospy.loginfo("SR result: %s", result)

                    now = time.time()

                    if (
                        result
                        and result != self.last_result
                        and (now - self.last_publish_time) > self.min_publish_interval
                    ):
                        self.pub.publish(result)
                        self.last_result = result
                        self.last_publish_time = now

                except sr.UnknownValueError:
                    rospy.loginfo("Speech not understood")

                except sr.RequestError as e:
                    rospy.logerr("Google SR error: %s", e)

            except rospy.ROSInterruptException:
                break

            except Exception as e:
                rospy.logerr("Unexpected error: %s", e)
                time.sleep(0.5)


if __name__ == "__main__":
    node = GoogleSpeechNode()
    node.run()