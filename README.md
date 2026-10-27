# Earth Wallpaper 🌍

실시간 위성 구름 오버레이 및 주야간 조명을 반영하여 아름다운 실시간 지구 렌더링 이미지를 Windows 바탕화면으로 자동 설정해 주는 PyQt6 데스크톱 애플리케이션입니다.

## ✨ 주요 기능
- **실시간 위성 구름 합성**: 실시간 위성 클라우드 데이터를 다운로드하여 지구 표면에 오버레이
- **주야간(Day/Night) 조명 렌더링**: 태양 위치 계산을 통한 주간/야간 조명 및 도시 불빛 반영
- **달/태양/ISS 천체 렌더링**: 지구 주변 천체 및 ISS 위치 표시 지원
- **커스터마이징 UI**:
  - 중심 좌표 (위도/경도) 지정
  - 지구 기울기(Tilt) 및 줌(Zoom) 설정
  - 구름 투명도(Opacity) 및 대비(Contrast) 조절
- **Windows 시스템 트레이 및 바탕화면 자동 갱신**
- **단일 인스턴스 보장 (`QLockFile`)**

## 🚀 시작하기

### 요구 사항
- Windows OS
- Python 3.10+

### 설치 및 실행

1. 저장소 복제:
```bash
git clone https://github.com/byword77/earthwallpaper.git
cd earthwallpaper
```

2. 가상환경 생성 및 활성화:
```bash
python -m venv venv
venv\Scripts\activate
```

3. 필요 패키지 설치:
```bash
pip install PyQt6 Pillow requests numpy ephem
```

4. 애플리케이션 실행:
```bash
python desktop_v0.2.py
```

### 실행 파일 빌드 (PyInstaller)
```bash
pyinstaller --noconfirm EarthWallpaper.spec
```
빌드 완료 후 `dist/EarthWallpaper/` 디렉토리에 실행 파일이 생성됩니다.

## ⚙️ 설정 (`config.json`)
UI 또는 `config.json` 파일을 통해 다음 항목을 설정할 수 있습니다:
- `mode`: 구름 데이터 수집 방식 (`url` 또는 `api`)
- `lat`, `lon`: 지구 중심 위도/경도
- `tilt`: 지구 자전축 기울기 각도
- `zoom`: 줌 레벨 (40~100)
- `opa`: 구름 불투명도 (0~100)
- `cont`: 구름 대비 배율 (100~200)

## 📄 라이선스
MIT License (또는 프로젝트에 맞는 라이선스 참조)
