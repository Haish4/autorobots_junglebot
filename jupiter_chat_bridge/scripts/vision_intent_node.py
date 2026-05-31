#!/usr/bin/env python3
import os
import time
import base64
import threading
from typing import Optional

import cv2
import rospy
from std_msgs.msg import String
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from openai import OpenAI
from transformers import pipeline

VISUAL_KEYWORDS = [
    "what is this", "what's this", "what are these",
    "what do you see", "what can you see", "look at this",
    "describe this", "describe what you see",
    "identify this", "what kind of", "what type of",
    "what plant", "what animal", "what insect", "what bird",
    "show me", "tell me what", "can you see",
]

ZS_LABELS = ["visual question about camera", "general conversation"]
VISUAL_LABEL = ZS_LABELS[0]
ZS_THRESHOLD = 0.70
CAMERA_TOPIC = "/usb_cam/image_raw"


class VisionIntentNode:
    def __init__(self):
        rospy.init_node("vision_intent_node")
        rospy.loginfo("[VisionIntent] Initialising...")

        self.chat_pub     = rospy.Publisher("/chat_input",       String, queue_size=5)
        self.tts_pub      = rospy.Publisher("/gtts_input",       String, queue_size=5)
        self.snapshot_pub = rospy.Publisher("/vision_snapshot",  Image,  queue_size=1)

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set in environment")
        self.client = OpenAI(api_key=api_key)

        self.bridge       = CvBridge()
        self.latest_frame = None
        self._frame_lock  = threading.Lock()
        rospy.Subscriber(CAMERA_TOPIC, Image, self._image_callback)
        rospy.loginfo("[VisionIntent] Subscribed to %s", CAMERA_TOPIC)

        self.classifier = None
        self.clf_ready  = False
        self._clf_lock  = threading.Lock()
        threading.Thread(target=self._load_classifier, daemon=True).start()

        self.last_text  = ""
        self.processing = False
        self._proc_lock = threading.Lock()

        rospy.Subscriber("/google_sr", String, self.callback)
        rospy.loginfo("[VisionIntent] Ready.")

    def _image_callback(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            with self._frame_lock:
                self.latest_frame = frame
        except Exception as exc:
            rospy.logwarn("[VisionIntent] Frame receive error: %s", exc)

    def _capture_frame_b64(self):
        # type: () -> Optional[str]
        with self._frame_lock:
            frame = self.latest_frame.copy() if self.latest_frame is not None else None
        if frame is None:
            rospy.logwarn("[VisionIntent] No frame received from camera yet")
            return None, None
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buf).decode("utf-8")
        return b64, frame

    def _publish_snapshot(self, frame):
        try:
            msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
            self.snapshot_pub.publish(msg)
            rospy.loginfo("[VisionIntent] Snapshot published to /vision_snapshot")
        except Exception as exc:
            rospy.logwarn("[VisionIntent] Snapshot publish error: %s", exc)

    def _load_classifier(self):
        rospy.loginfo("[VisionIntent] Loading DistilBERT classifier...")
        try:
            clf = pipeline(
                "zero-shot-classification",
                model="typeform/distilbert-base-uncased-mnli",
                device=-1,
            )
            with self._clf_lock:
                self.classifier = clf
                self.clf_ready  = True
            rospy.loginfo("[VisionIntent] Classifier ready.")
        except Exception as exc:
            rospy.logerr("[VisionIntent] Classifier load failed: %s", exc)
            rospy.logwarn("[VisionIntent] Keyword-only mode active.")

    def _is_visual_query(self, text):
        lowered = text.lower()
        for kw in VISUAL_KEYWORDS:
            if kw in lowered:
                rospy.loginfo("[VisionIntent] Keyword match -> visual")
                return True

        with self._clf_lock:
            ready = self.clf_ready
            clf   = self.classifier

        if not ready or clf is None:
            return False

        try:
            result    = clf(text, candidate_labels=ZS_LABELS)
            top_label = result["labels"][0]
            top_score = result["scores"][0]
            rospy.loginfo("[VisionIntent] ZS top=%s (%.2f)", top_label, top_score)
            return top_label == VISUAL_LABEL and top_score >= ZS_THRESHOLD
        except Exception as exc:
            rospy.logwarn("[VisionIntent] Classifier error: %s", exc)
            return False

    def _ask_vision(self, user_text, image_b64):
        system_prompt = (
            "You are JungleBot, a friendly jungle guide. "
            "Your output is spoken by a text-to-speech system. "
            "Do NOT use markdown, asterisks, symbols, or formatting. "
            "Speak only in natural plain sentences. "
            "Keep responses under 25 words. "
            "The user is pointing a camera at something in the jungle. "
            "Describe or identify what you see simply and clearly."
        )
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=80,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/jpeg;base64," + image_b64,
                                "detail": "low",
                            },
                        },
                        {"type": "text", "text": user_text},
                    ],
                },
            ],
        )
        reply = response.choices[0].message.content.strip()
        reply = reply.replace("*", "").replace("#", "")
        reply = " ".join(reply.split()[:25])
        return reply

    def _vision_pipeline(self, user_text):
        rospy.loginfo("[VisionIntent] Vision pipeline start")
        rospy.set_param("/robot_speaking", True)
        try:
            image_b64, frame = self._capture_frame_b64()
            if image_b64 is None:
                reply = "I could not see anything right now. Try again."
            else:
                # Publish snapshot to dashboard BEFORE API call
                self._publish_snapshot(frame)
                reply = self._ask_vision(user_text, image_b64)
            rospy.loginfo("[VisionIntent] Vision reply: %s", reply)
            self.tts_pub.publish(reply)
            time.sleep(0.5)
        except Exception as exc:
            rospy.logerr("[VisionIntent] Vision pipeline error: %s", exc)
            self.tts_pub.publish("Sorry, I could not identify that.")
            time.sleep(0.5)
        finally:
            rospy.set_param("/robot_speaking", False)
            with self._proc_lock:
                self.processing = False
            rospy.loginfo("[VisionIntent] Vision pipeline done, STT unmuted")

    def callback(self, msg):
        if rospy.get_param("/robot_speaking", False):
            return

        with self._proc_lock:
            if self.processing:
                rospy.loginfo("[VisionIntent] Ignored: vision pipeline busy")
                return

        user_text = msg.data.strip()
        if not user_text or user_text == self.last_text:
            return
        self.last_text = user_text

        rospy.loginfo("[VisionIntent] Received: '%s'", user_text)

        if self._is_visual_query(user_text):
            with self._proc_lock:
                self.processing = True
            threading.Thread(
                target=self._vision_pipeline,
                args=(user_text,),
                daemon=True,
            ).start()
        else:
            rospy.loginfo("[VisionIntent] -> chat_bridge")
            self.chat_pub.publish(user_text)


if __name__ == "__main__":
    rospy.loginfo("[VisionIntent] Booting...")
    node = None
    try:
        node = VisionIntentNode()
        rospy.spin()
    except Exception as exc:
        rospy.logfatal("[VisionIntent] Fatal: %s", repr(exc))
