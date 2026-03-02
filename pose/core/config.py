# config.py

# 카메라 설정
CAMERA_INDEX = [0, 1, 2]
FRAME_WIDTH  = 640
FRAME_HEIGHT = 480
CAPTURE_FPS  = 30

# ArUco 마커 설정
MARKER_SIZE = 0.17      # 0.17m (17cm)
WORLD_ORIGIN_ID = 0     # 기준이 될 마커 ID (중앙)

# 캘리브레이션 체커보드 설정
CHECKERBOARD_DIMS = (9, 6) 
CHECKERBOARD_SIZE = 0.025

# 추론 설정
INFER_EVERY_N_FRAMES = 1
USE_HALF = True