# NSU Project

3대 카메라 기반 3D 포즈 추정(`pose`)과 웹 제어 UI(`web`)를 하나의 프로젝트로 통합한 버전입니다.

## 프로젝트 구조

```text
nsu_project/
  run.py                    # 통합 실행 진입점 (한 번에 실행)
  requirements.txt
  README.md
  web/                      # 웹 UI 정적 파일
    setup.html
    index.html
    src/
      robot_cam.js
      setup.js
      style.css
      theme_handler.js
      img/nsu_logo.png
      img/favicon.png
  pose/
    main.py                 # 포즈 추정 런타임
    web_server.py           # Flask + Serial 제어 서버
    core/
    tools/
    data/
    models/
```

## 빠른 시작

1. 프로젝트 폴더 이동
```bash
cd nsu_project
```

2. 가상환경 생성/활성화
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

3. 의존성 설치
```bash
pip install -r requirements.txt
```

4. 통합 실행
```bash
python run.py
```

기본 웹 주소: `http://localhost:5000`  
상태 확인: `http://localhost:5000/health`

5. 첫 화면에서 장치 선택 후 `확인(적용)`
- Arduino 포트
- Baud Rate: `9600` 고정
- Camera 1, Camera 2, Camera 3
- ESP32-CAM IP
- 기본값은 없고, 반드시 화면에서 직접 선택해야 합니다.
- 오프라인 테스트는 `DEMO (No Arduino)` 또는 `DEMO (No Camera)` 선택
- ESP32 데모는 IP에 `0.0.0.0` 입력
- 적용하면 `/app` 메인 UI로 이동하며 선택한 카메라로 pose 런타임이 시작됩니다.

## 실행 모드

- 전체 실행(기본): 장치 선택 UI + 적용 후 pose 시작
```bash
python run.py --mode all
```

- 포즈만 실행:
```bash
python run.py --mode pose
```

- 웹 서버만 실행: 장치 선택/웹 제어만 실행 (설정 적용 시 pose도 시작 가능)
```bash
python run.py --mode web --host 0.0.0.0 --port 5000
```

## HTTPS 실행

- 기본은 HTTP입니다.
- 로컬 HTTPS는 `mkcert` 방식을 기본으로 권장합니다.

```bash
mkcert -install
python run.py --https
```

- 첫 실행 시 `certs/localhost.pem`, `certs/localhost-key.pem`가 자동 생성됩니다.
- 실행 후 접속 주소: `https://localhost:5000`
- 커스텀 인증서 경로를 쓰려면 기존처럼 `--ssl-cert`, `--ssl-key`를 직접 지정할 수 있습니다.

## 장치 설정 정책

- COM 포트/카메라는 코드 내부 기본값을 사용하지 않습니다.
- ESP32 IP도 설정 화면에서 입력해야 합니다.
- 실행 후 반드시 설정 화면에서 장치를 선택하고 적용해야 동작합니다.
- `DEMO` 선택 시 하드웨어 없이 UI/제어 흐름 테스트가 가능합니다.

## 상태/모니터링 API

- 상태 확인: `GET /health`
- 설정 확인: `GET /api/config`
- 포즈 상태(각도/카메라): `GET /api/pose-status`
