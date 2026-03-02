# calibration_tool.py
import cv2
import numpy as np
import glob
import os
import yaml
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import CHECKERBOARD_DIMS, CHECKERBOARD_SIZE

DATA_DIR = ROOT_DIR / "data"

def run_calibration_from_images(save_file="calibration_results.yaml"):
    print("\n[캘리브레이션] 시작합니다...")
    
    # 3D 기준점 (0,0,0), (1,0,0), (2,0,0) ...
    objp = np.zeros((CHECKERBOARD_DIMS[0] * CHECKERBOARD_DIMS[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHECKERBOARD_DIMS[0], 0:CHECKERBOARD_DIMS[1]].T.reshape(-1, 2)
    objp = objp * CHECKERBOARD_SIZE

    calib_data = {}
    cam_names = ['Cam_1', 'Cam_2', 'Cam_3']
    
    cali_root = DATA_DIR / "cali"

    for i, cam_name in enumerate(cam_names):
        print(f" -> {cam_name} 이미지 분석 중...")
        
        # 이미지 경로: cali/cam1/*.jpg
        # 폴더명은 cam1, cam2, cam3 (소문자)로 가정
        folder_name = f"cam{i+1}"
        images = glob.glob(str(cali_root / folder_name / "*.jpg"))
        
        if not images:
            print(f"    [경고] {folder_name} 폴더에 이미지가 없습니다. 건너뜁니다.")
            continue

        objpoints = [] # 3D points
        imgpoints = [] # 2D points
        valid_img_count = 0
        img_shape = None

        for fname in images:
            img = cv2.imread(fname)
            if img is None: continue
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img_shape = gray.shape[::-1]

            # 체커보드 찾기
            ret, corners = cv2.findChessboardCorners(gray, CHECKERBOARD_DIMS, None)

            if ret:
                objpoints.append(objp)
                # 정확도 향상 (Subpixel)
                corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), 
                                            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
                imgpoints.append(corners2)
                valid_img_count += 1
        
        if valid_img_count > 0:
            print(f"    사용된 이미지: {valid_img_count}장. 계산 중...")
            ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, img_shape, None, None)
            
            if ret:
                calib_data[cam_name] = {
                    'Camera_Matrix': mtx.tolist(),
                    'Dist_Coeffs': dist.tolist(),
                    'RMS': ret
                }
                print(f"    [성공] RMS 오차: {ret:.4f}")
            else:
                print("    [실패] 수렴하지 않았습니다.")
        else:
            print("    [실패] 체커보드를 감지한 이미지가 없습니다.")

    # 결과 저장
    if calib_data:
        output_path = Path(save_file)
        if not output_path.is_absolute():
            output_path = DATA_DIR / output_path
        with open(output_path, 'w') as f:
            yaml.dump(calib_data, f)
        print(f"[완료] {save_file} 저장되었습니다.")
        return True
    else:
        print("[오류] 저장할 데이터가 없습니다.")
        return False
