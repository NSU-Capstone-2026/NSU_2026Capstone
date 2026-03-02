const serialPortEl = document.getElementById('serialPort');
const cam1El = document.getElementById('cam1');
const cam2El = document.getElementById('cam2');
const cam3El = document.getElementById('cam3');
const esp32IpEl = document.getElementById('esp32Ip');
const refreshBtn = document.getElementById('refreshBtn');
const applyBtn = document.getElementById('applyBtn');
const setupMessage = document.getElementById('setupMessage');
const cam1Preview = document.getElementById('cam1Preview');
const cam2Preview = document.getElementById('cam2Preview');
const cam3Preview = document.getElementById('cam3Preview');
const cam1PreviewMsg = document.getElementById('cam1PreviewMsg');
const cam2PreviewMsg = document.getElementById('cam2PreviewMsg');
const cam3PreviewMsg = document.getElementById('cam3PreviewMsg');
const esp32Preview = document.getElementById('esp32Preview');
const esp32PreviewMsg = document.getElementById('esp32PreviewMsg');

const DEMO_SERIAL = '__DEMO_SERIAL__';
const DEMO_CAMERA = '__DEMO_CAMERA__';
const DEMO_ESP32_IP = '0.0.0.0';
const FIXED_BAUD_RATE = 9600;

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

function buildEsp32StreamUrl(ip) {
  return `http://${ip}:81/stream`;
}

function setMessage(text, isError = false) {
  setupMessage.textContent = text;
  setupMessage.style.color = isError ? '#c62828' : 'var(--text-default)';
}

function buildPlaceholder(label) {
  const option = document.createElement('option');
  option.value = '';
  option.textContent = `${label} 선택`;
  return option;
}

function renderSelect(selectEl, items, valueKey, labelBuilder, placeholderLabel) {
  selectEl.innerHTML = '';
  selectEl.appendChild(buildPlaceholder(placeholderLabel));

  items.forEach(item => {
    const option = document.createElement('option');
    option.value = String(item[valueKey]);
    option.textContent = labelBuilder(item);
    selectEl.appendChild(option);
  });
}

function applySavedConfig(config) {
  if (config.serial_port) {
    const serialValue = String(config.serial_port);
    if ([...serialPortEl.options].some(o => o.value === serialValue)) {
      serialPortEl.value = serialValue;
    }
  }

  ['cam1', 'cam2', 'cam3'].forEach((key, idx) => {
    const select = [cam1El, cam2El, cam3El][idx];
    if (config[key] !== null && config[key] !== undefined) {
      const v = String(config[key]);
      if ([...select.options].some(o => o.value === v)) {
        select.value = v;
      }
    }
  });

  if (config.esp32_ip) {
    esp32IpEl.value = String(config.esp32_ip);
  }

  refreshAllPreviews();
}

function setPreviewState(imgEl, msgEl, message, showImage) {
  msgEl.textContent = message;
  msgEl.hidden = showImage;
  imgEl.hidden = !showImage;
}

function updatePreview(selectEl, imgEl, msgEl) {
  const cameraId = selectEl.value;

  if (!cameraId) {
    imgEl.removeAttribute('src');
    setPreviewState(imgEl, msgEl, '카메라를 선택하세요.', false);
    return;
  }

  if (cameraId === DEMO_CAMERA) {
    imgEl.removeAttribute('src');
    setPreviewState(imgEl, msgEl, 'DEMO 카메라', false);
    return;
  }

  imgEl.src = `/api/camera-stream?camera_id=${encodeURIComponent(cameraId)}&_ts=${Date.now()}`;
}

function refreshAllPreviews() {
  updatePreview(cam1El, cam1Preview, cam1PreviewMsg);
  updatePreview(cam2El, cam2Preview, cam2PreviewMsg);
  updatePreview(cam3El, cam3Preview, cam3PreviewMsg);
  updateEsp32Preview();
}

function updateEsp32Preview() {
  const normalizedIp = normalizeIp(esp32IpEl.value);

  if (!esp32IpEl.value.trim()) {
    esp32Preview.removeAttribute('src');
    setPreviewState(esp32Preview, esp32PreviewMsg, 'ESP32 IP를 입력하세요.', false);
    return;
  }

  if (!normalizedIp) {
    esp32Preview.removeAttribute('src');
    setPreviewState(esp32Preview, esp32PreviewMsg, 'IP 형식이 올바르지 않습니다.', false);
    return;
  }

  if (normalizedIp === DEMO_ESP32_IP) {
    esp32Preview.removeAttribute('src');
    setPreviewState(esp32Preview, esp32PreviewMsg, 'ESP32-DEMO', false);
    return;
  }

  setPreviewState(esp32Preview, esp32PreviewMsg, '스트림 연결 중...', false);
  esp32Preview.src = `${buildEsp32StreamUrl(normalizedIp)}?_ts=${Date.now()}`;
}

async function loadDevicesAndConfig() {
  setMessage('장치 목록을 불러오는 중...');
  try {
    const [devicesResp, configResp] = await Promise.all([
      fetch('/api/devices'),
      fetch('/api/config'),
    ]);

    if (!devicesResp.ok || !configResp.ok) {
      throw new Error('API 응답 오류');
    }

    const devices = await devicesResp.json();
    const config = await configResp.json();

    renderSelect(
      serialPortEl,
      devices.serial_ports || [],
      'device',
      p => `${p.device} (${p.description || 'Unknown'})`,
      'Arduino 포트'
    );

    renderSelect(
      cam1El,
      devices.cameras || [],
      'id',
      c => c.label,
      'Camera 1'
    );
    renderSelect(
      cam2El,
      devices.cameras || [],
      'id',
      c => c.label,
      'Camera 2'
    );
    renderSelect(
      cam3El,
      devices.cameras || [],
      'id',
      c => c.label,
      'Camera 3'
    );

    applySavedConfig(config);

    if (config.configured) {
      const mode = config.demo_mode ? 'DEMO' : 'LIVE';
      setMessage(`이전 설정이 있습니다. 현재 모드: ${mode}`);
    } else {
      setMessage('');
    }
  } catch (error) {
    setMessage(`장치 정보를 가져오지 못했습니다: ${error.message}`, true);
  }
}

applyBtn.addEventListener('click', async () => {
  const serialPort = serialPortEl.value;
  const baudRate = FIXED_BAUD_RATE;
  const cam1 = cam1El.value;
  const cam2 = cam2El.value;
  const cam3 = cam3El.value;
  const esp32Ip = normalizeIp(esp32IpEl.value);

  if (!serialPort) {
    setMessage('Arduino 포트를 선택하세요.', true);
    return;
  }

  if (!cam1 || !cam2 || !cam3) {
    setMessage('카메라 1, 2, 3을 모두 선택하세요.', true);
    return;
  }

  if (!esp32Ip) {
    setMessage('올바른 ESP32-CAM IP를 입력하세요. (예: 192.168.0.54)', true);
    return;
  }

  const isDemoCam = [cam1, cam2, cam3].includes(DEMO_CAMERA);
  if (!isDemoCam && new Set([cam1, cam2, cam3]).size !== 3) {
    setMessage('LIVE 모드에서는 카메라 1, 2, 3이 모두 달라야 합니다.', true);
    return;
  }

  const demoMode = serialPort === DEMO_SERIAL || isDemoCam;

  setMessage(demoMode ? 'DEMO 모드로 설정 적용 중...' : 'LIVE 모드로 설정 적용 중...');
  try {
    const resp = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        serial_port: serialPort,
        baud_rate: baudRate,
        cam1,
        cam2,
        cam3,
        esp32_ip: esp32Ip,
      }),
    });

    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.message || '설정 적용 실패');
    }

    window.location.href = '/app';
  } catch (error) {
    setMessage(`적용 실패: ${error.message}`, true);
  }
});

refreshBtn.addEventListener('click', () => {
  loadDevicesAndConfig();
  refreshAllPreviews();
});
cam1El.addEventListener('change', refreshAllPreviews);
cam2El.addEventListener('change', refreshAllPreviews);
cam3El.addEventListener('change', refreshAllPreviews);
esp32IpEl.addEventListener('input', () => {
  esp32IpEl.value = esp32IpEl.value.replace(/[^0-9.]/g, '');
  updateEsp32Preview();
});

cam1Preview.addEventListener('error', () => {
  setPreviewState(cam1Preview, cam1PreviewMsg, '스트림 연결 실패', false);
});
cam1Preview.addEventListener('load', () => {
  setPreviewState(cam1Preview, cam1PreviewMsg, '', true);
});
cam2Preview.addEventListener('error', () => {
  setPreviewState(cam2Preview, cam2PreviewMsg, '스트림 연결 실패', false);
});
cam2Preview.addEventListener('load', () => {
  setPreviewState(cam2Preview, cam2PreviewMsg, '', true);
});
cam3Preview.addEventListener('error', () => {
  setPreviewState(cam3Preview, cam3PreviewMsg, '스트림 연결 실패', false);
});
cam3Preview.addEventListener('load', () => {
  setPreviewState(cam3Preview, cam3PreviewMsg, '', true);
});
esp32Preview.addEventListener('load', () => {
  setPreviewState(esp32Preview, esp32PreviewMsg, '', true);
});
esp32Preview.addEventListener('error', () => {
  esp32Preview.removeAttribute('src');
  setPreviewState(esp32Preview, esp32PreviewMsg, 'ESP32 스트림 연결 실패', false);
});

loadDevicesAndConfig();
