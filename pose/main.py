# main.py

# [1] 경고 메시지 차단 (가장 먼저 실행)
import os
import argparse
import json
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
import cv2
# OpenCV 내부 로깅 레벨을 '에러'만 표시하도록 변경 (경고 무시)
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except:
    pass

import time
import numpy as np
import yaml
import cv2.aruco as aruco
from pathlib import Path

from core.capture_3cam import MultiCamCapture
from core.pose_yolo import YoloPose
from core.config import MARKER_SIZE, WORLD_ORIGIN_ID, INFER_EVERY_N_FRAMES
from core.utils_3d import get_projection_matrix, triangulate_points, calculate_angle_3d

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
RUNTIME_STATUS_PATH = DATA_DIR / "runtime_status.json"

# --- 행렬 유틸 ---
def get_transform_matrix(rvec, tvec):
    R, _ = cv2.Rodrigues(rvec)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = tvec.flatten()
    return T

def inverse_transform_matrix(T):
    return np.linalg.inv(T)

# --- 카메라 선택 ---
def open_camera(index):
    if os.name == "nt":
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(index)
    else:
        cap = cv2.VideoCapture(index)
    return cap

def interactive_mapping():
    available = []
    print("\n[시스템] 사용 가능한 카메라 포트를 검색합니다...")
    for i in range(6):
        cap = open_camera(i)
        if cap.isOpened():
            available.append(i)
        cap.release()
    
    mapping = {}
    print(f"[설정] 감지된 카메라 인덱스: {available}")
    print(">> 화면을 클릭하고 키보드 '1', '2', '3'을 눌러 카메라를 할당하세요. (건너뛰기: 's')")

    for idx in available:
        cap = open_camera(idx)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            disp = cv2.resize(frame, (640, 480))
            cv2.putText(disp, f"Hardware Index: {idx}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            cv2.putText(disp, "Press [1], [2], [3] to Assign / [S] to Skip", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            cv2.imshow("Camera Mapping Tool", disp)
            key = cv2.waitKey(1) & 0xFF
            
            if key in [ord('1'), ord('2'), ord('3')]:
                cam_key = f"Cam_{chr(key)}"
                if cam_key in mapping:
                    print(f"[경고] {cam_key}는 이미 할당되었습니다. 덮어씁니다.")
                mapping[cam_key] = idx
                print(f" -> Index {idx}가 {cam_key}로 설정됨")
                break
            elif key == ord('s'):
                print(f" -> Index {idx} 스킵")
                break
        cap.release()
        if len(mapping) == 3:
            print("[완료] 3대 설정 끝")
            break
    cv2.destroyAllWindows()
    return mapping


def parse_args():
    parser = argparse.ArgumentParser(description="Pose runtime")
    parser.add_argument("--cam1", type=int, default=None)
    parser.add_argument("--cam2", type=int, default=None)
    parser.add_argument("--cam3", type=int, default=None)
    return parser.parse_args()


def mapping_from_args(args):
    values = [args.cam1, args.cam2, args.cam3]
    if all(v is not None for v in values):
        return {
            "Cam_1": int(args.cam1),
            "Cam_2": int(args.cam2),
            "Cam_3": int(args.cam3),
        }
    return None


def write_runtime_status(mapping, angle=None):
    payload = {
        "timestamp": time.time(),
        "cams": {
            "cam1": mapping.get("Cam_1"),
            "cam2": mapping.get("Cam_2"),
            "cam3": mapping.get("Cam_3"),
        },
        "angles": {
            "arm_angle": angle,
            "shoulder_angle": None,
            "elbow_angle": None,
            "wrist_angle": None,
            "torso_rotation": None,
        },
    }
    try:
        RUNTIME_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(RUNTIME_STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass

# --- 맵 로드/저장 ---
def load_marker_map(filename="marker_map.yaml"):
    if not os.path.exists(filename):
        print("[정보] marker_map.yaml 없음. 0번 마커만 사용합니다.")
        return {WORLD_ORIGIN_ID: np.eye(4)}
    try:
        with open(filename, 'r') as f:
            data = yaml.load(f, Loader=yaml.FullLoader)
        print(f"[시스템] {filename} 로드 성공. ID 목록: {list(data.keys())}")
        return {k: np.array(v) for k, v in data.items()}
    except Exception as e:
        print(f"[오류] 맵 로드 실패: {e}")
        return {WORLD_ORIGIN_ID: np.eye(4)}

def save_marker_map(marker_map, filename="marker_map.yaml"):
    data = {k: v.tolist() for k, v in marker_map.items()}
    with open(filename, 'w') as f:
        yaml.dump(data, f)
    print(f"[저장] {filename}에 마커 지도가 저장되었습니다.")

# --- 카메라 위치 추적 ---
def get_camera_pose_from_markers(corners, ids, cam_mtx, dist, marker_map):
    if ids is None: return None, None
    rvecs_list, tvecs_list = [], []

    obj_pts = np.array([[0,0,0], [MARKER_SIZE,0,0], [MARKER_SIZE,MARKER_SIZE,0], [0,MARKER_SIZE,0]], dtype=np.float32)

    for i, mid in enumerate(ids.flatten()):
        if mid in marker_map:
            _, rvec, tvec = cv2.solvePnP(obj_pts, corners[i], cam_mtx, dist)
            
            T_cam_to_marker = get_transform_matrix(rvec, tvec)
            T_0_to_marker = marker_map[mid]
            T_marker_to_0 = np.linalg.inv(T_0_to_marker)
            T_cam_to_0 = T_cam_to_marker @ T_marker_to_0
            
            t_final = T_cam_to_0[:3, 3]
            r_final, _ = cv2.Rodrigues(T_cam_to_0[:3, :3])
            rvecs_list.append(r_final)
            tvecs_list.append(t_final)

    if not rvecs_list: return None, None
    return rvecs_list[0], tvecs_list[0]

# --- 메인 실행 ---
def main(camera_mapping=None):
    mapping = camera_mapping if camera_mapping is not None else interactive_mapping()
    if len(mapping) < 3: return
    write_runtime_status(mapping, angle=None)

    cams = MultiCamCapture(mapping)
    pose = YoloPose(model_path=str(MODELS_DIR / "yolov8n-pose.pt"))
    
    if not cams.load_calibration(str(DATA_DIR / "calibration_results.yaml")):
        print("[경고] 캘리브레이션 데이터가 없습니다.")

    marker_map = load_marker_map(DATA_DIR / "marker_map.yaml")
    marker_map[WORLD_ORIGIN_ID] = np.eye(4)

    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    detector = aruco.ArucoDetector(aruco_dict, aruco.DetectorParameters())

    cams.start()
    
    is_mapping_mode = False 
    print("\n=== [시스템 시작] ===")
    print(" [M] 키: '맵핑 모드' <-> '추적 모드' 전환")
    print(" [ESC]: 종료")

    # [수정] 축 길이를 3cm로 줄여서 화면 밖으로 나가는 현상 최소화
    AXIS_LENGTH = 0.03 
    obj_pts = np.array([[0,0,0], [MARKER_SIZE,0,0], [MARKER_SIZE,MARKER_SIZE,0], [0,MARKER_SIZE,0]], dtype=np.float32)
    frame_idx = 0
    last_kpts_by_cam = {key: None for key in cams.cam_keys}
    n_infer = max(1, int(INFER_EVERY_N_FRAMES))
    last_status_write = 0.0

    while True:
        frame_idx += 1
        frames = cams.get_frames()
        if any(f is None for f in frames.values()):
            time.sleep(0.001)
            continue

        active_proj_mats = [] 
        detected_kpts = []    
        mapping_candidates = []

        mode_color = (0, 0, 255) if is_mapping_mode else (0, 255, 0)
        mode_str = "[MAPPING MODE] (Space: Add, M: Save&Exit)" if is_mapping_mode else "[TRACKING MODE] (M: Map)"

        for key in cams.cam_keys:
            frame = frames[key]
            disp = frame.copy()
            cam_mtx = cams.cam_matrices[key]
            dist = cams.dist_coeffs[key]
            calibrated = (cam_mtx is not None) and (dist is not None)
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = detector.detectMarkers(gray)
            
            if ids is not None:
                aruco.drawDetectedMarkers(disp, corners, ids)

            # [CASE 1] 맵핑 모드
            if is_mapping_mode:
                visible_markers_T = {}
                if ids is not None and calibrated:
                    for i, mid in enumerate(ids.flatten()):
                        _, rvec, tvec = cv2.solvePnP(obj_pts, corners[i], cam_mtx, dist)
                        
                        try:
                            cv2.drawFrameAxes(disp, cam_mtx, dist, rvec, tvec, AXIS_LENGTH)
                        except: pass # 그리기 실패해도 무시
                        
                        visible_markers_T[mid] = get_transform_matrix(rvec, tvec)

                if WORLD_ORIGIN_ID in visible_markers_T:
                    mapping_candidates.append((key, visible_markers_T))

                cv2.putText(disp, f"Mapped IDs: {list(marker_map.keys())}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                if not calibrated:
                    cv2.putText(disp, "No calibration", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # [CASE 2] 추적 모드
            else:
                if not calibrated:
                    cv2.putText(disp, "No calibration", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                else:
                    rvec, tvec = get_camera_pose_from_markers(corners, ids, cam_mtx, dist, marker_map)

                    if rvec is not None:
                        try:
                            cv2.drawFrameAxes(disp, cam_mtx, dist, rvec, tvec, AXIS_LENGTH)
                        except: pass

                        if frame_idx % n_infer == 0 or last_kpts_by_cam[key] is None:
                            last_kpts_by_cam[key] = pose.infer(frame)

                        kpts = last_kpts_by_cam[key]
                        if kpts is not None and len(kpts) > 10:
                            sh, el, wr = kpts[6], kpts[8], kpts[10]
                            if sh[0] > 0 and el[0] > 0 and wr[0] > 0:
                                cv2.circle(disp, (int(sh[0]), int(sh[1])), 5, (255,0,0), -1)
                                cv2.circle(disp, (int(el[0]), int(el[1])), 5, (0,255,0), -1)
                                cv2.circle(disp, (int(wr[0]), int(wr[1])), 5, (0,0,255), -1)
                                
                                try:
                                    P = get_projection_matrix(cam_mtx, rvec, tvec)
                                    active_proj_mats.append(P)
                                    detected_kpts.append([sh, el, wr])
                                except: pass

            cv2.putText(disp, mode_str, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, mode_color, 2)
            cv2.imshow(key, disp)

        # [3D 계산]
        if not is_mapping_mode and len(active_proj_mats) >= 2:
            try:
                pts_sh = triangulate_points(active_proj_mats, np.array([d[0] for d in detected_kpts]).T)
                pts_el = triangulate_points(active_proj_mats, np.array([d[1] for d in detected_kpts]).T)
                pts_wr = triangulate_points(active_proj_mats, np.array([d[2] for d in detected_kpts]).T)
                angle = calculate_angle_3d(pts_sh, pts_el, pts_wr)
                print(f"[3D] 팔 각도: {angle:.1f}도")
                now = time.monotonic()
                if now - last_status_write >= 0.2:
                    write_runtime_status(mapping, angle=float(angle))
                    last_status_write = now
            except: pass

        # 키 입력 (프레임당 1회 처리)
        key = cv2.waitKey(1) & 0xFF
        if is_mapping_mode and key == 32:  # Space
            for _, visible_markers_T in mapping_candidates:
                T_cam_to_0 = visible_markers_T[WORLD_ORIGIN_ID]
                T_0_to_cam = inverse_transform_matrix(T_cam_to_0)
                for mid, T_cam_to_N in visible_markers_T.items():
                    if mid != WORLD_ORIGIN_ID:
                        T_0_to_N = T_0_to_cam @ T_cam_to_N
                        marker_map[mid] = T_0_to_N
                        print(f"✅ [등록] 마커 {mid}번이 0번 기준으로 등록되었습니다.")

        if key == 27: 
            break
        elif key == ord('m'): 
            is_mapping_mode = not is_mapping_mode
            if not is_mapping_mode:
                save_marker_map(marker_map, DATA_DIR / "marker_map.yaml")
                print("\n[시스템] 추적 모드로 전환됨.")
            else:
                print("\n=== [맵핑 모드 진입] ===")

    cams.shutdown()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    cli_args = parse_args()
    main(mapping_from_args(cli_args))
