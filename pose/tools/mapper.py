# mapper.py
import cv2
import numpy as np
import yaml
import os
import cv2.aruco as aruco
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.capture_3cam import MultiCamCapture
from core.config import MARKER_SIZE, WORLD_ORIGIN_ID

DATA_DIR = ROOT_DIR / "data"

def get_transform_matrix(rvec, tvec):
    """rvec, tvec를 4x4 변환 행렬로 변환"""
    R, _ = cv2.Rodrigues(rvec)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = tvec.flatten()
    return T

def inverse_transform_matrix(T):
    """4x4 행렬의 역행렬 (위치 관계 반전)"""
    R = T[:3, :3]
    t = T[:3, 3]
    T_inv = np.eye(4)
    T_inv[:3, :3] = R.T
    T_inv[:3, 3] = -R.T @ t
    return T_inv

def main():
    # 맵핑을 위해 카메라 1대만 있어도 충분하지만, 시스템에 연결된 걸 씁니다.
    # 편의상 Cam_1(인덱스 0번 가정)을 메인으로 사용하거나 전체를 돕니다.
    # 사용자는 "0번과 N번이 동시에 보이는 각도"로 카메라를 잠시 움직이거나
    # 마커를 배치해야 합니다.
    
    mapping = {'Cam_1': 0, 'Cam_2': 1, 'Cam_3': 2} 
    cams = MultiCamCapture(mapping)
    if not cams.load_calibration(str(DATA_DIR / "calibration_results.yaml")):
        print("[오류] 캘리브레이션 파일이 필요합니다.")
        return

    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    detector = aruco.ArucoDetector(aruco_dict, aruco.DetectorParameters())
    
    # 마커 맵 데이터 저장소
    # 구조: { ID : 4x4_Transform_Matrix_from_Origin }
    # 0번은 단위행렬(자기 자신)
    marker_map = {WORLD_ORIGIN_ID: np.eye(4).tolist()}
    
    cams.start()
    print("\n=== 마커 맵핑 모드 ===")
    print(" 1. 카메라에 '기준 마커(0)'와 '새로운 마커(1~4)'가 동시에 보이게 하세요.")
    print(" 2. [Space] 키를 누르면 관계를 계산하여 저장합니다.")
    print(" 3. 모든 마커 등록이 끝나면 [Q]를 눌러 저장하고 종료하세요.")

    while True:
        frames = cams.get_frames()
        if any(f is None for f in frames.values()): continue

        for key in cams.cam_keys:
            frame = frames[key]
            disp = frame.copy()
            
            corners, ids, _ = detector.detectMarkers(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
            
            current_transforms = {} # 현재 프레임에서 발견된 마커들의 카메라 기준 T

            if ids is not None:
                aruco.drawDetectedMarkers(disp, corners, ids)
                for i, mid in enumerate(ids.flatten()):
                    # PnP로 카메라 기준 좌표 계산
                    obj_pts = np.array([[0,0,0], [MARKER_SIZE,0,0], [MARKER_SIZE,MARKER_SIZE,0], [0,MARKER_SIZE,0]], dtype=np.float32)
                    _, rvec, tvec = cv2.solvePnP(obj_pts, corners[i], cams.cam_matrices[key], cams.dist_coeffs[key])
                    
                    # 4x4 행렬로 변환 (T_camera_to_marker)
                    current_transforms[mid] = get_transform_matrix(rvec, tvec)
                    
                    # 축 그리기
                    cv2.drawFrameAxes(disp, cams.cam_matrices[key], cams.dist_coeffs[key], rvec, tvec, 0.1)

            # 화면에 등록된 마커 표시
            status_text = f"Mapped IDs: {list(marker_map.keys())}"
            cv2.putText(disp, status_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow(key, disp)

            # [로직] 기준 마커(0)와 미등록 마커(N)가 동시에 보이면 관계 계산 가능
            if WORLD_ORIGIN_ID in current_transforms:
                T_cam_to_0 = current_transforms[WORLD_ORIGIN_ID]
                T_0_to_cam = inverse_transform_matrix(T_cam_to_0)
                
                # Space바를 눌렀을 때만 저장 (오차 방지)
                if cv2.waitKey(1) & 0xFF == 32: # Space
                    for mid, T_cam_to_N in current_transforms.items():
                        if mid != WORLD_ORIGIN_ID and mid not in marker_map:
                            # 공식: T_0_to_N = T_0_to_Cam * T_Cam_to_N
                            T_0_to_N = T_0_to_cam @ T_cam_to_N
                            marker_map[mid] = T_0_to_N.tolist()
                            print(f"[등록] 마커 {mid}번이 0번 기준으로 등록되었습니다!")

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cams.shutdown()
    cv2.destroyAllWindows()
    
    # 파일 저장
    if len(marker_map) > 1:
        with open(DATA_DIR / "marker_map.yaml", 'w') as f:
            yaml.dump(marker_map, f)
        print(f"[완료] 총 {len(marker_map)}개의 마커 관계가 {DATA_DIR / 'marker_map.yaml'}에 저장되었습니다.")
    else:
        print("[취소] 등록된 추가 마커가 없어 저장하지 않았습니다.")

if __name__ == "__main__":
    main()
