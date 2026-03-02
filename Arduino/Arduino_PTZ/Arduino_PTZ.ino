#include <Servo.h>
#include <SoftwareSerial.h>

// ----------------- 1. 핀 및 통신 정의 -----------------
const long BAUD_RATE = 9600; 

// 서보 모터 핀 정의 (기존 코드 유지)
#define PAN_SERVO_PIN 5
#define TILT_SERVO_PIN 6

// Raspberry Pi <-> Arduino SoftwareSerial 핀
// RPI TX -> ARDUINO RX_PIN, RPI RX -> ARDUINO TX_PIN
#define SOFTSERIAL_RX_PIN 10
#define SOFTSERIAL_TX_PIN 11

// ************************ 제어 변수 설정 ************************
const int MOVE_STEP = 1; // 이동 단위
// ******************************************************************

// 각도 상수 정의 (기존 코드 유지)
const int PAN_MIN = 0;
const int PAN_MAX = 180;
const int TILT_MIN = 15;
const int TILT_MAX = 180;
const int PAN_HOME = 95;
const int TILT_HOME = 90;

Servo pan_servo;
Servo tilt_servo;
SoftwareSerial piSerial(SOFTSERIAL_RX_PIN, SOFTSERIAL_TX_PIN);

// pan_deg, tilt_deg: 현재 서보의 각도(위치)를 추적하는 변수입니다.
int pan_deg = 0;
int tilt_deg = 0;

// 현재 명령 상태를 저장하는 변수 (초기 명령을 'X'로 설정하여 시작 시 움직이지 않도록 함)
char currentCommand = 'X'; 


void setup() {
  Serial.begin(BAUD_RATE);
  piSerial.begin(BAUD_RATE);
  pan_servo.attach(PAN_SERVO_PIN);
  tilt_servo.attach(TILT_SERVO_PIN);
  
  // 초기 위치 설정
  pan_deg = PAN_HOME;
  tilt_deg = TILT_HOME;
  pan_servo.write(pan_deg);
  tilt_servo.write(tilt_deg);
  
  Serial.println("Robot-Arm CAM Control Ready. Waiting for Pi Commands (U, D, X, S, etc.).");
}

void loop() {
  // 1. 새로운 시리얼 명령 수신
  if (piSerial.available() > 0) {
    char incomingChar = piSerial.read();
    
    // 유효한 명령만 업데이트
    if (incomingChar != '\r' && incomingChar != '\n') {
        currentCommand = incomingChar;
    }
    
    // 디버깅 출력 (선택 사항)
    // Serial.print("Current Command (Pi): ");
    // Serial.println(currentCommand);
  } else if (Serial.available() > 0) {
    // USB 시리얼도 백업 입력으로 허용 (테스트/디버깅 용도)
    char incomingChar = Serial.read();
    if (incomingChar != '\r' && incomingChar != '\n') {
        currentCommand = incomingChar;
    }
  }
  
  // 2. 현재 명령에 따라 서보 각도 계산
  calculateNewPosition(currentCommand);
  
  // 3. 각도 경계 검사
  if (pan_deg < PAN_MIN) pan_deg = PAN_MIN;
  if (pan_deg > PAN_MAX) pan_deg = PAN_MAX;
  if (tilt_deg < TILT_MIN) tilt_deg = TILT_MIN; 
  if (tilt_deg > TILT_MAX) tilt_deg = TILT_MAX;
  
  // 4. 서보 모터 업데이트
  pan_servo.write(pan_deg);
  tilt_servo.write(tilt_deg);
  
  delay(10); // 제어 주기 (10ms)
}

// ----------------- 명령 기반 위치 계산 함수 -----------------
void calculateNewPosition(char cmd) {
  
  // 'S' 명령 (RESET): 홈 위치로 이동
  if (cmd == 'S') {
    // 홈 위치에 도달할 때까지 연속적으로 이동
    if (pan_deg < PAN_HOME) {
        pan_deg += MOVE_STEP;
    } else if (pan_deg > PAN_HOME) {
        pan_deg -= MOVE_STEP;
    }
    
    if (tilt_deg < TILT_HOME) {
        tilt_deg += MOVE_STEP;
    } else if (tilt_deg > TILT_HOME) {
        tilt_deg -= MOVE_STEP;
    }
    
    // 오차 범위 내에서는 정확히 홈 위치로 고정
    if (abs(pan_deg - PAN_HOME) <= MOVE_STEP) pan_deg = PAN_HOME;
    if (abs(tilt_deg - TILT_HOME) <= MOVE_STEP) tilt_deg = TILT_HOME;
    
    return; // 연속 이동 명령은 실행하지 않음
  } 
  
  // 'X' 명령 (HOLD): 정지
  if (cmd == 'X') {
    // 아무것도 하지 않아 현재 pan_deg와 tilt_deg를 유지합니다.
    return;
  }
  
  // 그 외 명령: 연속 이동 처리 (MOVE_STEP만큼 변경)
  switch (cmd) {
    case 'U': // UP
      tilt_deg += MOVE_STEP;
      break;
    
    case 'D': // DOWN
      tilt_deg -= MOVE_STEP;
      break;
      
    case 'L': // LEFT
      pan_deg -= MOVE_STEP;
      break;

    case 'R': // RIGHT
      pan_deg += MOVE_STEP;
      break;

    case 'Q': // UP_LEFT 
      tilt_deg += MOVE_STEP;
      pan_deg -= MOVE_STEP;
      break;
      
    case 'E': // UP_RIGHT 
      tilt_deg += MOVE_STEP;
      pan_deg += MOVE_STEP;
      break;

    case 'Z': // DOWN_LEFT 
      tilt_deg -= MOVE_STEP;
      pan_deg -= MOVE_STEP;
      break;

    case 'C': // DOWN_RIGHT 
      tilt_deg -= MOVE_STEP;
      pan_deg += MOVE_STEP;
      break;
      
    default:
      // 알 수 없는 문자는 무시
      break;
  }
}
