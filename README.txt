# ================================
# Jupiter Tour Guide Robot STARTUP
# ================================

# 0. Setup environment (always do this first)
source /opt/ros/noetic/setup.bash
source ~/catkin_ws/devel/setup.bash

# ================================
# 1. Start ROS master
# ================================
roscore 

# ================================
# 2. Start Speech Recognition
# ================================
rosrun jupiter_chat_bridge google_sr.py 

# ================================
# 3. Start ChatGPT Bridge
# ================================
export OPENAI_API_KEY="api here"
rosrun jupiter_chat_bridge chat_bridge_node.py

# ================================
# 4. Start Text-to-Speech
# ================================
rosrun jupiter_chat_bridge google_tts.py

# ================================
# DONE
# ================================
echo "Jupiter robot system started 🚀"