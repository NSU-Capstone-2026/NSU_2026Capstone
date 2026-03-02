# capture_3cam.py
import cv2
import time
import threading
import numpy as np
import yaml
import os
from .config import FRAME_WIDTH, FRAME_HEIGHT, CAPTURE_FPS

class MultiCamCapture:
    def __init__(self, mapping):
        # mapping: {'Cam_1': 0, 'Cam_2': 1, ...}
        self.mapping = mapping
        self.cam_keys = ['Cam_1', 'Cam_2', 'Cam_3']
        
        # 프레임 저장소
        self.frames = {key: None for key in self.cam_keys}
        
        # 캘리브레이션 데이터 저장소
        self.cam_matrices = {key: None for key in self.cam_keys}
        self.dist_coeffs = {key: None for key in self.cam_keys}
        
        self.lock = threading.Lock()
        self.stop = False
        self.threads = []

    def load_calibration(self, yaml_filename):
        """YAML 파일에서 캘리브레이션 데이터를 읽어옵니다."""
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            yaml_path = str(yaml_filename)
            if not os.path.isabs(yaml_path):
                yaml_path = os.path.join(base_path, yaml_path)
            
            with open(yaml_path, 'r') as f:
                data = yaml.load(f, Loader=yaml.FullLoader)
            
            for key in self.cam_keys:
                if key in data:
                    self.cam_matrices[key] = np.array(data[key]['Camera_Matrix'])
                    self.dist_coeffs[key] = np.array(data[key]['Dist_Coeffs'])
            
            print(f"[System] {yaml_filename} 로드 성공")
            return True
        except Exception as e:
            print(f"[Error] 캘리브레이션 로드 실패: {e}")
            return False

    def _setup_cam(self, idx):
        if os.name == "nt":
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(idx)
        else:
            cap = cv2.VideoCapture(idx)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, CAPTURE_FPS)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        return cap

    def _capture_loop(self, key, cam_idx):
        cap = self._setup_cam(cam_idx)
        print(f"[{key}] 카메라(Index {cam_idx}) 시작 ({FRAME_WIDTH}x{FRAME_HEIGHT})")
        
        while not self.stop:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.001)
                continue
            
            with self.lock:
                self.frames[key] = frame
        
        cap.release()
        print(f"[{key}] 종료")

    def start(self):
        self.threads = []
        for key, idx in self.mapping.items():
            t = threading.Thread(target=self._capture_loop, args=(key, idx))
            t.daemon = True
            t.start()
            self.threads.append(t)

    def get_frames(self):
        with self.lock:
            return self.frames.copy()

    def shutdown(self):
        self.stop = True
        for t in self.threads:
            t.join(timeout=1.0)
