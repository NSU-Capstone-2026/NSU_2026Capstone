from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, request
from flask_cors import CORS

try:
    import cv2
except Exception:
    cv2 = None

try:
    import serial
    from serial.tools import list_ports
except Exception:
    serial = None
    list_ports = None


DEMO_SERIAL = "__DEMO_SERIAL__"
DEMO_CAMERA = "__DEMO_CAMERA__"
DEMO_ESP32_IP = "0.0.0.0"
FIXED_BAUD_RATE = 9600
RUNTIME_STATUS_PATH = Path(__file__).resolve().parent / "data" / "runtime_status.json"

COMMAND_MAP = {
    "UP": "U",
    "DOWN": "D",
    "LEFT": "L",
    "RIGHT": "R",
    "UP_LEFT": "Q",
    "UP_RIGHT": "E",
    "DOWN_LEFT": "Z",
    "DOWN_RIGHT": "C",
    "HOLD": "X",
    "RESET": "S",
}

STREAM_BOUNDARY = "frame"


def is_demo_serial(value: str | None) -> bool:
    return value == DEMO_SERIAL


def is_demo_camera(value: str | None) -> bool:
    return value == DEMO_CAMERA


def is_demo_esp32_ip(value: str | None) -> bool:
    return value == DEMO_ESP32_IP


def normalize_ip(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    parts = raw.split(".")
    if len(parts) != 4:
        return None
    try:
        nums = [int(p) for p in parts]
    except Exception:
        return None
    if any(n < 0 or n > 255 for n in nums):
        return None
    normalized = ".".join(str(n) for n in nums)
    if is_demo_esp32_ip(normalized):
        return DEMO_ESP32_IP
    return normalized


class SerialController:
    def __init__(self) -> None:
        self.port: str | None = None
        self.baud_rate: int | None = None
        self._ser = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        self.disconnect()

        if self.port is None or is_demo_serial(self.port):
            print("[WEB] DEMO 시리얼 모드")
            return

        if serial is None:
            print("[WEB] pyserial 미설치: 시리얼 제어 비활성화")
            return

        try:
            self._ser = serial.Serial(self.port, int(self.baud_rate or 9600), timeout=0.1)
            time.sleep(2)
            print(f"[WEB] 시리얼 연결 성공: {self.port} @ {self.baud_rate}")
        except Exception as exc:
            self._ser = None
            print(f"[WEB] 시리얼 연결 실패: {exc}")

    def disconnect(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def reconfigure(self, port: str, baud_rate: int) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.connect()

    @property
    def connected(self) -> bool:
        if is_demo_serial(self.port):
            return True
        return self._ser is not None

    @property
    def demo_mode(self) -> bool:
        return is_demo_serial(self.port)

    def send(self, command: str) -> bool:
        if self.demo_mode:
            return True
        if not self._ser:
            return False

        serial_char = COMMAND_MAP[command]
        with self._lock:
            self._ser.write(serial_char.encode("utf-8"))
        return True


class AppState:
    def __init__(self, pose_entry: Path) -> None:
        self.pose_entry = pose_entry
        self.serial = SerialController()
        self.preview_lock = threading.Lock()

        self._lock = threading.Lock()
        self.pose_proc: subprocess.Popen | None = None
        self.config = {
            "serial_port": None,
            "baud_rate": FIXED_BAUD_RATE,
            "cam1": None,
            "cam2": None,
            "cam3": None,
            "esp32_ip": None,
            "demo_mode": False,
        }

    @property
    def configured(self) -> bool:
        return all(self.config[k] is not None for k in ("serial_port", "cam1", "cam2", "cam3"))

    @property
    def demo_mode(self) -> bool:
        return bool(self.config["demo_mode"])

    def update_config(
        self,
        serial_port: str,
        baud_rate: int,
        cam1: str,
        cam2: str,
        cam3: str,
        esp32_ip: str,
    ) -> None:
        demo_mode = is_demo_serial(serial_port) or any(is_demo_camera(v) for v in (cam1, cam2, cam3))
        with self._lock:
            self.config.update(
                {
                    "serial_port": serial_port,
                    "baud_rate": baud_rate,
                    "cam1": cam1,
                    "cam2": cam2,
                    "cam3": cam3,
                    "esp32_ip": esp32_ip,
                    "demo_mode": demo_mode,
                }
            )

    def stop_pose(self) -> None:
        with self._lock:
            if self.pose_proc is None:
                return
            if self.pose_proc.poll() is None:
                self.pose_proc.terminate()
                try:
                    self.pose_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.pose_proc.kill()
            self.pose_proc = None

    def start_pose_if_needed(self) -> None:
        with self._lock:
            cam1 = self.config["cam1"]
            cam2 = self.config["cam2"]
            cam3 = self.config["cam3"]
            demo_mode = bool(self.config["demo_mode"])

            if cam1 is None or cam2 is None or cam3 is None:
                raise ValueError("Camera config is incomplete")

            if demo_mode:
                if self.pose_proc is not None and self.pose_proc.poll() is None:
                    self.pose_proc.terminate()
                    try:
                        self.pose_proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.pose_proc.kill()
                self.pose_proc = None
                print("[POSE] DEMO 모드: pose 프로세스를 시작하지 않음")
                return

            cam1_i = int(cam1)
            cam2_i = int(cam2)
            cam3_i = int(cam3)

            if self.pose_proc is not None and self.pose_proc.poll() is None:
                self.pose_proc.terminate()
                try:
                    self.pose_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.pose_proc.kill()

            cmd = [
                sys.executable,
                str(self.pose_entry),
                "--cam1",
                str(cam1_i),
                "--cam2",
                str(cam2_i),
                "--cam3",
                str(cam3_i),
            ]
            self.pose_proc = subprocess.Popen(cmd)
            print(f"[POSE] started PID={self.pose_proc.pid} cams=({cam1_i},{cam2_i},{cam3_i})")

    @property
    def pose_running(self) -> bool:
        proc = self.pose_proc
        return proc is not None and proc.poll() is None


def _detect_serial_ports() -> list[dict]:
    ports = [{"device": DEMO_SERIAL, "description": "DEMO (No Arduino)"}]
    if list_ports is None:
        return ports

    for p in list_ports.comports():
        ports.append({"device": p.device, "description": p.description})
    return ports


def _open_camera(index: int):
    if cv2 is None:
        return None
    if os.name == "nt":
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(index)
    else:
        cap = cv2.VideoCapture(index)
    return cap


def _mjpeg_generator(camera_index: int, lock: threading.Lock):
    cap = None
    try:
        with lock:
            cap = _open_camera(camera_index)
            if cap is None or not cap.isOpened():
                return

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.03)
                continue

            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
            if not ok:
                continue

            yield (
                b"--" + STREAM_BOUNDARY.encode("utf-8") + b"\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + encoded.tobytes() + b"\r\n"
            )
            time.sleep(0.03)
    finally:
        if cap is not None:
            cap.release()


def _detect_cameras(max_index: int = 10) -> list[dict]:
    cameras = [{"id": DEMO_CAMERA, "label": "DEMO (No Camera)"}]

    if cv2 is None:
        return cameras

    for idx in range(max_index):
        cap = _open_camera(idx)
        if cap is not None and cap.isOpened():
            cameras.append({"id": str(idx), "label": f"Camera {idx}"})
        if cap is not None:
            cap.release()
    return cameras


def create_app(
    pose_entry: Path,
) -> Flask:
    project_root = Path(__file__).resolve().parents[1]
    web_root = project_root / "web"

    app = Flask(__name__, static_folder=str(web_root), static_url_path="")
    CORS(app, resources={r"/*": {"origins": "*"}})

    state = AppState(pose_entry=pose_entry)

    def _cleanup() -> None:
        state.stop_pose()
        state.serial.disconnect()

    atexit.register(_cleanup)

    @app.route("/")
    def setup_page():
        return app.send_static_file("setup.html")

    @app.route("/app")
    def app_page():
        if not state.configured:
            return redirect("/")
        return app.send_static_file("index.html")

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(
            {
                "status": "ok",
                "configured": state.configured,
                "demo_mode": state.demo_mode,
                "pose_running": state.pose_running,
                "serial_connected": state.serial.connected,
            }
        )

    @app.route("/api/devices", methods=["GET"])
    def get_devices():
        return jsonify({"serial_ports": _detect_serial_ports(), "cameras": _detect_cameras()})

    @app.route("/api/camera-preview", methods=["GET"])
    def camera_preview():
        camera_id = request.args.get("camera_id")
        if not camera_id:
            return jsonify({"status": "error", "message": "camera_id is required"}), 400

        if is_demo_camera(camera_id):
            return jsonify({"status": "error", "message": "DEMO camera has no live preview"}), 400

        if cv2 is None:
            return jsonify({"status": "error", "message": "OpenCV is not available"}), 503

        try:
            camera_index = int(camera_id)
        except Exception:
            return jsonify({"status": "error", "message": "camera_id must be integer-like"}), 400

        with state.preview_lock:
            cap = _open_camera(camera_index)
            if cap is None or not cap.isOpened():
                if cap is not None:
                    cap.release()
                return jsonify({"status": "error", "message": "Failed to open camera"}), 404

            ret, frame = cap.read()
            cap.release()

        if not ret or frame is None:
            return jsonify({"status": "error", "message": "Failed to read frame"}), 502

        # Preview is for quick identification only; downscale to reduce latency.
        h, w = frame.shape[:2]
        target_w = 480
        if w > target_w:
            target_h = int(h * (target_w / float(w)))
            frame = cv2.resize(frame, (target_w, max(1, target_h)), interpolation=cv2.INTER_AREA)

        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
        if not ok:
            return jsonify({"status": "error", "message": "Failed to encode frame"}), 500

        return Response(
            encoded.tobytes(),
            mimetype="image/jpeg",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @app.route("/api/camera-stream", methods=["GET"])
    def camera_stream():
        camera_id = request.args.get("camera_id")
        if not camera_id:
            return jsonify({"status": "error", "message": "camera_id is required"}), 400

        if is_demo_camera(camera_id):
            return jsonify({"status": "error", "message": "DEMO camera has no live stream"}), 400

        if cv2 is None:
            return jsonify({"status": "error", "message": "OpenCV is not available"}), 503

        try:
            camera_index = int(camera_id)
        except Exception:
            return jsonify({"status": "error", "message": "camera_id must be integer-like"}), 400

        return Response(
            _mjpeg_generator(camera_index, state.preview_lock),
            mimetype=f"multipart/x-mixed-replace; boundary={STREAM_BOUNDARY}",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @app.route("/api/config", methods=["GET"])
    def get_config():
        return jsonify({"configured": state.configured, **state.config})

    @app.route("/api/pose-status", methods=["GET"])
    def get_pose_status():
        status_data = {
            "angles": {
                "arm_angle": None,
                "shoulder_angle": None,
                "elbow_angle": None,
                "wrist_angle": None,
                "torso_rotation": None,
            },
            "cams": {
                "cam1": state.config.get("cam1"),
                "cam2": state.config.get("cam2"),
                "cam3": state.config.get("cam3"),
            },
            "timestamp": None,
            "pose_running": state.pose_running,
        }
        try:
            if RUNTIME_STATUS_PATH.exists():
                with open(RUNTIME_STATUS_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    angles = loaded.get("angles")
                    if isinstance(angles, dict):
                        status_data["angles"] = {
                            "arm_angle": angles.get("arm_angle"),
                            "shoulder_angle": angles.get("shoulder_angle"),
                            "elbow_angle": angles.get("elbow_angle"),
                            "wrist_angle": angles.get("wrist_angle"),
                            "torso_rotation": angles.get("torso_rotation"),
                        }
                    elif "angle" in loaded:
                        # Backward compatibility with old runtime_status shape.
                        status_data["angles"]["arm_angle"] = loaded.get("angle")
                    status_data["timestamp"] = loaded.get("timestamp")
                    cams = loaded.get("cams")
                    if isinstance(cams, dict):
                        status_data["cams"] = {
                            "cam1": cams.get("cam1"),
                            "cam2": cams.get("cam2"),
                            "cam3": cams.get("cam3"),
                        }
        except Exception:
            pass
        return jsonify(status_data)

    @app.route("/api/config", methods=["POST"])
    def apply_config():
        data = request.get_json(silent=True) or {}
        serial_port_in = data.get("serial_port")
        cam1 = data.get("cam1")
        cam2 = data.get("cam2")
        cam3 = data.get("cam3")
        esp32_ip = normalize_ip(data.get("esp32_ip"))

        if not serial_port_in:
            return jsonify({"status": "error", "message": "serial_port 선택이 필요합니다."}), 400
        if not cam1 or not cam2 or not cam3:
            return jsonify({"status": "error", "message": "cam1, cam2, cam3 선택이 필요합니다."}), 400
        if not esp32_ip:
            return jsonify({"status": "error", "message": "유효한 esp32_ip 입력이 필요합니다."}), 400

        baud_rate = FIXED_BAUD_RATE

        cam_values = [str(cam1), str(cam2), str(cam3)]
        if not any(is_demo_camera(v) for v in cam_values):
            if len(set(cam_values)) != 3:
                return jsonify({"status": "error", "message": "cam1, cam2, cam3는 서로 달라야 합니다."}), 400

        state.update_config(
            serial_port=str(serial_port_in),
            baud_rate=baud_rate,
            cam1=str(cam1),
            cam2=str(cam2),
            cam3=str(cam3),
            esp32_ip=esp32_ip,
        )

        state.serial.reconfigure(str(serial_port_in), baud_rate)

        try:
            state.start_pose_if_needed()
        except Exception as exc:
            return jsonify({"status": "error", "message": f"Failed to start pose: {exc}"}), 500

        return jsonify({"status": "success", "config": state.config})

    @app.route("/control", methods=["POST"])
    def control_robot():
        if not state.configured:
            return jsonify({"status": "error", "message": "Apply device config first."}), 400

        data = request.get_json(silent=True) or {}
        command = data.get("command")

        if command not in COMMAND_MAP:
            return jsonify({"status": "error", "message": "Invalid command."}), 400

        if state.serial.demo_mode:
            return jsonify({"status": "success", "command_sent": command, "demo": True}), 200

        if not state.serial.connected:
            return jsonify({"status": "error", "message": "Serial is not connected."}), 500

        try:
            state.serial.send(command)
            return jsonify({"status": "success", "command_sent": command, "demo": False}), 200
        except Exception as exc:
            return jsonify({"status": "error", "message": f"Serial write failed: {exc}"}), 500

    return app


def run_web_server(
    host: str = "0.0.0.0",
    port: int = 5000,
    pose_entry: Path | None = None,
    ssl_cert: str | None = None,
    ssl_key: str | None = None,
) -> None:
    if pose_entry is None:
        pose_entry = Path(__file__).resolve().parent / "main.py"

    app = create_app(pose_entry=pose_entry)
    ssl_context = None
    if ssl_cert or ssl_key:
        if not ssl_cert or not ssl_key:
            raise ValueError("HTTPS 사용 시 --ssl-cert와 --ssl-key를 모두 지정해야 합니다.")
        ssl_context = (ssl_cert, ssl_key)
        print(f"[WEB] https://{host}:{port}")
    else:
        print(f"[WEB] http://{host}:{port}")

    app.run(host=host, port=port, debug=False, ssl_context=ssl_context)


if __name__ == "__main__":
    run_web_server(
        host=os.getenv("HTTP_HOST", "0.0.0.0"),
        port=int(os.getenv("HTTP_PORT", "5000")),
        ssl_cert=os.getenv("SSL_CERT"),
        ssl_key=os.getenv("SSL_KEY"),
    )
