const videoElement = document.getElementById('videoElement');
const demoWatermark = document.getElementById('demoWatermark');
const poseShoulderAngle = document.getElementById('poseShoulderAngle');
const poseElbowAngle = document.getElementById('poseElbowAngle');
const poseWristAngle = document.getElementById('poseWristAngle');
const poseTorsoAngle = document.getElementById('poseTorsoAngle');
const poseCam1 = document.getElementById('poseCam1');
const poseCam2 = document.getElementById('poseCam2');
const poseCam3 = document.getElementById('poseCam3');
const DEMO_ESP32_IP = '0.0.0.0';
const DEMO_CAMERA = '__DEMO_CAMERA__';

// ---------------- 로봇 제어 통신 함수 ----------------

// 1. 서버로 명령을 전송하는 함수 (HTTP POST 사용)
async function send_command(direction) {
    const serverUrl = '/control'; // 현재 웹서버 기준 상대 경로
    
    try {
        const response = await fetch(serverUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ command: direction })
        });
        
        if (!response.ok) {
            console.error(`서버 응답 오류: ${response.statusText}`);
        }
        
    } catch (error) {
        console.error('명령 전송 중 오류 발생: 서버가 실행 중인지 확인하세요.', error);
    }
}

// 2. 9개 방향 제어 버튼 이벤트 리스너 설정
function setupControlListeners() {
    const buttons = [
        { id: 'btn-up', command: 'UP' },
        { id: 'btn-down', command: 'DOWN' },
        { id: 'btn-left', command: 'LEFT' },
        { id: 'btn-right', command: 'RIGHT' },
        { id: 'btn-up-left', command: 'UP_LEFT' },
        { id: 'btn-up-right', command: 'UP_RIGHT' },
        { id: 'btn-down-left', command: 'DOWN_LEFT' },
        { id: 'btn-down-right', command: 'DOWN_RIGHT' },
        { id: 'btn-stop', command: 'RESET' } // <--- 수정: 중앙 버튼은 'RESET' 명령 전송
    ];

    buttons.forEach(btn => {
        const element = document.getElementById(btn.id);
        if (element) {
            // 마우스를 눌렀을 때 (mousedown): 해당 방향 또는 RESET 명령 전송
            element.addEventListener('mousedown', () => {
                send_command(btn.command);
            });

            // 마우스를 떼거나 (mouseup) 버튼이 RESET이 아닐 경우: HOLD 명령 전송
            if (btn.command !== 'RESET') { // 중앙 버튼이 아니면
                element.addEventListener('mouseup', () => {
                    send_command('HOLD'); // <--- 수정: 뗄 때 'HOLD' 명령 전송
                });
                // 버튼 영역을 벗어났을 때도 HOLD 명령 전송
                element.addEventListener('mouseleave', () => {
                    send_command('HOLD'); // <--- 수정: 뗄 때 'HOLD' 명령 전송
                });
            }
        }
    });
}

// ---------------- ESP32-CAM 스트림 로직 ----------------

function normalizeIp(inputValue) {
    const raw = (inputValue || '').trim();
    if (!raw) {
        return null;
    }

    const match = raw.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
    if (!match) {
        return null;
    }

    const parts = match.slice(1).map(Number);
    if (parts.some(part => Number.isNaN(part) || part < 0 || part > 255)) {
        return null;
    }

    return parts.join('.');
}

function buildStreamUrl(ip) {
    return `http://${ip}:81/stream`;
}

function connectCameraStream(inputValue) {
    const normalizedIp = normalizeIp(inputValue);
    if (!normalizedIp) {
        console.error('ESP32-CAM IP가 설정되지 않았습니다.');
        return;
    }

    if (normalizedIp === DEMO_ESP32_IP) {
        videoElement.removeAttribute('src');
        return;
    }

    const normalizedUrl = buildStreamUrl(normalizedIp);
    videoElement.src = `${normalizedUrl}${normalizedUrl.includes('?') ? '&' : '?'}_ts=${Date.now()}`;
}

function connectPoseCameraPreview(imgEl, cameraId) {
    if (!imgEl) {
        return;
    }

    if (!cameraId || cameraId === DEMO_CAMERA) {
        imgEl.removeAttribute('src');
        return;
    }

    imgEl.src = `/api/camera-stream?camera_id=${encodeURIComponent(cameraId)}&_ts=${Date.now()}`;
}

function applyPoseCameras(config) {
    connectPoseCameraPreview(poseCam1, config.cam1);
    connectPoseCameraPreview(poseCam2, config.cam2);
    connectPoseCameraPreview(poseCam3, config.cam3);
}

function renderAngle(el, value) {
    if (!el) {
        return;
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
        el.textContent = `${value.toFixed(1)}°`;
    } else {
        el.textContent = '--.-°';
    }
}

async function refreshPoseStatus() {
    if (!poseShoulderAngle || !poseElbowAngle || !poseWristAngle || !poseTorsoAngle) {
        return;
    }
    try {
        const response = await fetch('/api/pose-status');
        if (!response.ok) {
            return;
        }

        const status = await response.json();
        const angles = status.angles || {};
        renderAngle(poseShoulderAngle, angles.shoulder_angle);
        // For now, runtime arm_angle is mapped to elbow display until dedicated elbow output is added.
        renderAngle(poseElbowAngle, angles.elbow_angle ?? angles.arm_angle);
        renderAngle(poseWristAngle, angles.wrist_angle);
        renderAngle(poseTorsoAngle, angles.torso_rotation);
    } catch (error) {
        console.error('포즈 상태 로드 실패:', error);
    }
}

async function loadAppConfig() {
    try {
        const response = await fetch('/api/config');
        if (!response.ok) {
            return;
        }

        const config = await response.json();
        if (demoWatermark && config.demo_mode) {
            demoWatermark.hidden = false;
        }
        if (config.esp32_ip) {
            connectCameraStream(config.esp32_ip);
        }
        applyPoseCameras(config);
    } catch (error) {
        console.error('설정 로드 실패:', error);
    }
}

videoElement.addEventListener('error', () => {
    console.error('ESP32-CAM 스트림 연결에 실패했습니다.');
});

setupControlListeners();
loadAppConfig();
refreshPoseStatus();
setInterval(refreshPoseStatus, 500);
