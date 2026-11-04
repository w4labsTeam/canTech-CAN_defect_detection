# -----------------------------------------------------
# Mindvision Camera Configuration
# -----------------------------------------------------

# Exposure time in microseconds 
EXPOSURE_TIME_US = 700

# MindVision Trigger modes:

# 0 - Continuous acquisition 
# 1 - Software trigger 
# 2 - Hardware trigger
TRIGGER_MODE = 2

# External trigger edge 

# 0 = rising edge 
# 1 = falling edge 
# 2 = high level 
# 3 = low level 
# 4 = double edge 
TRIGGER_EDGE = 0

# Name of the OpenCV display window 
DISPLAY_WINDOW_NAME = "Mindvision - Hardware Trigger"

# In actual production area - 11000 us
# Home setup - 15000 us
TRIGGER_DELAY_US = 11000    