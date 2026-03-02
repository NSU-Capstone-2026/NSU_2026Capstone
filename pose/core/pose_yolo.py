# pose_yolo.py
import torch
from ultralytics import YOLO
from .config import USE_HALF

class YoloPose:
    def __init__(self, model_path="yolov8n-pose.pt"):
        if torch.cuda.is_available():
            print("[YOLO] CUDA GPU 사용 가능")
            self.device = "cuda:0"
        else:
            print("[YOLO] 경고: CUDA를 찾을 수 없습니다. CPU로 실행합니다.")
            self.device = "cpu"
        
        # half 정밀도는 CUDA에서만 이점이 있고, CPU에서는 예외를 유발할 수 있어 비활성화
        self.use_half = bool(USE_HALF and self.device.startswith("cuda"))
        self.model = YOLO(model_path)

    def infer(self, frame):
        # verbose=False로 로그 출력 최소화
        try:
            results = self.model.predict(
                source=frame,
                device=self.device,
                verbose=False,
                half=self.use_half
            )[0]

            # 사람이 감지되지 않았을 때 안전하게 None 반환
            if results.keypoints is None or len(results.keypoints.xy) == 0:
                return None

            # 첫 번째 사람의 키포인트 반환 [17, 2] numpy array
            return results.keypoints.xy[0].cpu().numpy()
            
        except Exception:
            # 예기치 않은 오류 발생 시 무시하고 진행
            return None
