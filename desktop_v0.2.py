import sys
import os
import ctypes
import datetime
import json
import requests
import winreg
import math
import random
import numpy as np
import gc  # 메모리 관리를 위해 추가됨
from PIL import Image, ImageEnhance, ImageDraw

# 천문 계산 라이브러리 로드
try:
    import ephem
    HAS_EPHEM = True
except ImportError:
    HAS_EPHEM = False
    print("알림: 'ephem' 라이브러리가 없습니다. 태양 위치가 정확하지 않을 수 있습니다. (pip install ephem)")

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QSlider, QComboBox, QFormLayout, 
                             QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox, QProgressBar,
                             QGroupBox, QRadioButton, QLineEdit, QButtonGroup,
                             QSystemTrayIcon, QMenu, QStyle, QAbstractSpinBox)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QLockFile, QDir
from PyQt6.QtGui import QPixmap, QResizeEvent, QPainter, QIcon

SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDWININICHANGE = 0x02
CONFIG_FILE = "config.json"

# ==========================================
# 창 크기 변경 감지 라벨
# ==========================================
class ResizeLabel(QLabel):
    resized = pyqtSignal()
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: #000;")
        self._pixmap = None
    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()
    def paintEvent(self, event):
        if self._pixmap and not self._pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            target_size = self.size()
            scaled_pix = self._pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x = (target_size.width() - scaled_pix.width()) // 2
            y = (target_size.height() - scaled_pix.height()) // 2
            painter.drawPixmap(x, y, scaled_pix)
            del scaled_pix
        else:
            super().paintEvent(event)
    def resizeEvent(self, event: QResizeEvent):
        self.resized.emit()
        super().resizeEvent(event)
    def clear_pixmap(self):
        if self._pixmap:
            self._pixmap = None
        self.update()

# ==========================================
# 천체 위치 계산기
# ==========================================
class CelestialCalculator:
    @staticmethod
    def get_sun_pos():
        if not HAS_EPHEM:
            now = datetime.datetime.now(datetime.timezone.utc)
            seconds = now.hour * 3600 + now.minute * 60 + now.second
            lon = math.radians(180 - (seconds / 86400.0) * 360)
            return 0.0, lon
        observer = ephem.Observer()
        observer.date = datetime.datetime.now(datetime.timezone.utc)
        observer.elevation = 0
        body = ephem.Sun(observer)
        gst = observer.sidereal_time()
        ra = body.g_ra; dec = body.g_dec
        geo_lon = ra - gst; geo_lat = dec
        geo_lon = (geo_lon + np.pi) % (2 * np.pi) - np.pi
        return float(geo_lat), float(geo_lon)

    @staticmethod
    def get_iss_pos():
        try:
            response = requests.get("http://api.open-notify.org/iss-now.json", timeout=1.0)
            if response.status_code == 200:
                data = response.json()
                lat = float(data['iss_position']['latitude'])
                lon = float(data['iss_position']['longitude'])
                return math.radians(lat), math.radians(lon)
        except:
            pass
        return None, None

# ==========================================
# 3D 지구 렌더러 (메모리 최적화 버전)
# ==========================================
class EarthRenderer:
    _texture_cache = {}

    @classmethod
    def _get_texture(cls, path, mode="RGB", contrast=1.0, resize_shape=None):
        """이미지를 캐싱하여 동일한 파일을 매번 디스크에서 읽는 것을 방지합니다."""
        if not path or not os.path.exists(path):
            return None
            
        mtime = os.path.getmtime(path)
        cache_key = (path, mode, contrast)
        
        if cache_key in cls._texture_cache and cls._texture_cache[cache_key]['mtime'] == mtime:
            tex = cls._texture_cache[cache_key]['data']
            if resize_shape and tex.shape[:2] != resize_shape:
                return np.array(Image.fromarray(tex).resize((resize_shape[1], resize_shape[0])))
            return tex

        try:
            img = Image.open(path).convert(mode)
            if contrast != 1.0 and mode == "L":
                img = ImageEnhance.Contrast(img).enhance(contrast)
                
            if resize_shape:
                img = img.resize((resize_shape[1], resize_shape[0]))
                
            data = np.array(img)
            cls._texture_cache[cache_key] = {'mtime': mtime, 'data': data}
            return data
        except Exception as e:
            print(f"Texture load error ({path}): {e}")
            return None

    @staticmethod
    def render_globe(width, height, lat, lon, zoom, tilt, earth_dir, assets_dir, cloud_path=None, opacity=90, contrast=1.0):
        try:
            if width <= 0 or height <= 0: return None

            # --- 1. 리소스 로드 (캐시 사용) ---
            month = datetime.datetime.now().month
            day_map_path = os.path.join(earth_dir, f"m{month:02d}.jpg")
            night_map_path = os.path.join(earth_dir, "night.jpg")
            specular_map_path = os.path.join(earth_dir, "specular.jpg")
            
            tex_day = EarthRenderer._get_texture(day_map_path, "RGB")
            tex_night = EarthRenderer._get_texture(night_map_path, "RGB")
            if tex_day is None or tex_night is None: return None

            base_shape = tex_day.shape[:2]
            tex_spec = EarthRenderer._get_texture(specular_map_path, "L", resize_shape=base_shape)
            if tex_spec is None: tex_spec = np.zeros(base_shape, dtype=np.uint8)

            tex_cloud = EarthRenderer._get_texture(cloud_path, "L", contrast=contrast, resize_shape=base_shape)

            star_path = os.path.join(assets_dir, "stars.jpg")
            iss_path = os.path.join(assets_dir, "ISS.png")

            img_stars = Image.open(star_path).convert("RGB") if os.path.exists(star_path) else None
            img_iss = Image.open(iss_path).convert("RGBA") if os.path.exists(iss_path) else None
            if not img_iss:
                img_iss = Image.new("RGBA", (30, 30), (0,0,0,0))
                ImageDraw.Draw(img_iss).rectangle((0,0,30,30), fill=(255, 0, 0, 255))

            # --- 2. 캔버스 및 배경 그리기 ---
            canvas_img = Image.new("RGB", (width, height), (0, 0, 0))
            if img_stars:
                bg_w, bg_h = img_stars.size
                shift_x = int((lon / 360.0) * bg_w) % bg_w
                shift_y = int((lat / 180.0) * (bg_h / 2))
                
                bg_shifted = Image.new("RGB", (bg_w, bg_h))
                bg_shifted.paste(img_stars.crop((bg_w - shift_x, 0, bg_w, bg_h)), (0, 0))
                bg_shifted.paste(img_stars.crop((0, 0, bg_w - shift_x, bg_h)), (shift_x, 0))

                bg_zoom = max(width/bg_w, height/bg_h) * 1.2
                crop_w = int(width / bg_zoom)
                crop_h = int(height / bg_zoom)
                cy, cx = bg_h // 2 - shift_y, bg_w // 2 
                box = (max(0, cx - crop_w//2), max(0, cy - crop_h//2), min(bg_w, cx + crop_w//2), min(bg_h, cy + crop_h//2))
                
                if box[2] > box[0] and box[3] > box[1]:
                    canvas_img.paste(bg_shifted.crop(box).resize((width, height), Image.Resampling.LANCZOS), (0, 0))
                del bg_shifted, img_stars

            # --- 3. 지오메트리 계산 ---
            radius = int((min(width, height) / 2) * (zoom / 50.0))
            if radius <= 0: radius = 1
            cx, cy = width // 2, height // 2
            
            # --- 4. 투영 헬퍼 함수 ---
            def project_orthographic(target_lat, target_lon):
                phi0, lam0 = np.radians(lat), np.radians(lon)
                cos_c = np.sin(phi0)*np.sin(target_lat) + np.cos(phi0)*np.cos(target_lat)*np.cos(target_lon - lam0)
                if cos_c < 0: return None, None 
                x = radius * np.cos(target_lat) * np.sin(target_lon - lam0)
                y = radius * (np.cos(phi0)*np.sin(target_lat) - np.sin(phi0)*np.cos(target_lat)*np.cos(target_lon - lam0))
                tilt_rad = np.radians(tilt)
                rot_x = x * np.cos(tilt_rad) - y * np.sin(tilt_rad)
                rot_y = x * np.sin(tilt_rad) + y * np.cos(tilt_rad)
                return int(cx + rot_x), int(cy - rot_y)

            # --- 5. 지구 렌더링 (NumPy Float32 강제 및 메모리 즉시 해제) ---
            y_idx, x_idx = np.ogrid[-radius:radius, -radius:radius]
            tilt_rad = np.radians(tilt)
            cos_t, sin_t = np.cos(tilt_rad), np.sin(tilt_rad)
            
            x_rot = (x_idx * cos_t - y_idx * sin_t).astype(np.float32)
            y_rot = (x_idx * sin_t + y_idx * cos_t).astype(np.float32)
            
            mask = x_idx**2 + y_idx**2 <= radius**2
            z = np.sqrt(np.maximum(0, radius**2 - x_rot**2 - y_rot**2), dtype=np.float32)
            z[~mask] = 0.0

            x_norm = x_rot / radius; y_norm = -y_rot / radius; z_norm = z / radius
            del x_rot, y_rot, z
            
            lat_rad, lon_rad = np.radians(lat), np.radians(lon)
            sin_c, cos_c = np.sin(lat_rad), np.cos(lat_rad)
            
            P_lat = np.arcsin(np.clip(sin_c * z_norm + cos_c * y_norm, -1.0, 1.0), where=mask, out=np.zeros_like(z_norm))
            denom = cos_c * z_norm - sin_c * y_norm
            P_lon = np.arctan2(x_norm, denom, where=mask, out=np.zeros_like(z_norm)) + lon_rad
            P_lon = (P_lon + np.pi) % (2 * np.pi) - np.pi
            
            tex_h, tex_w = base_shape
            u = np.clip(((P_lon + np.pi) / (2 * np.pi) * (tex_w - 1)).astype(int), 0, tex_w - 1)
            v = np.clip(((np.pi / 2 - P_lat) / np.pi * (tex_h - 1)).astype(int), 0, tex_h - 1)

            # 쉐이딩용 태양 위치
            sun_lat, sun_lon = CelestialCalculator.get_sun_pos()
            lon_diff = np.abs(P_lon - sun_lon)
            lon_diff = np.minimum(lon_diff, 2*np.pi - lon_diff)
            day_mask = np.clip((np.cos(P_lat) * np.cos(lon_diff)) * 5, 0, 1)[:, :, np.newaxis].astype(np.float32)
            del P_lat, P_lon, lon_diff

            base_earth = (tex_day[v, u] * day_mask + tex_night[v, u] * (1.0 - day_mask)).astype(np.float32)
            
            if tex_cloud is not None:
                cloud_val = tex_cloud[v, u]
                alpha = ((opacity / 100.0) * (cloud_val / 255.0))[:, :, np.newaxis].astype(np.float32)
                cloud_rgb = np.stack([cloud_val]*3, axis=-1).astype(np.float32)
                base_earth = base_earth * (1.0 - alpha) + cloud_rgb * alpha
                del cloud_val, alpha, cloud_rgb

            N = np.stack([x_norm, y_norm, z_norm], axis=-1)
            del x_norm, y_norm, z_norm
            
            L_lon, L_lat = sun_lon - lon_rad, sun_lat - lat_rad
            L = np.array([np.sin(L_lon) * np.cos(L_lat), np.sin(L_lat), np.cos(L_lon) * np.cos(L_lat)], dtype=np.float32)
            L /= np.linalg.norm(L)
            
            V_vec = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            H = (L + V_vec) / np.linalg.norm(L + V_vec)
            
            NdH = np.clip(np.einsum('ijk,k->ij', N, H), 0.0, 1.0)
            specular_rgb = (np.power(NdH, 30.0)[:, :, np.newaxis] * (tex_spec[v, u] / 255.0)[:, :, np.newaxis] * np.array([255, 255, 220], dtype=np.float32))
            del NdH, u, v

            VdN = np.clip(np.einsum('ijk,k->ij', N, V_vec), 0.0, 1.0)
            atmosphere_rgb = (np.power(1.0 - VdN, 2.5)[:, :, np.newaxis] * np.array([80, 120, 204], dtype=np.float32))
            del N, VdN

            final_composite = np.clip(base_earth + specular_rgb + atmosphere_rgb, 0, 255).astype(np.uint8)
            del base_earth, specular_rgb, atmosphere_rgb

            earth_arr = np.zeros((2*radius, 2*radius, 4), dtype=np.uint8)
            earth_arr[:, :, :3] = final_composite
            earth_arr[:, :, 3:] = (mask * 255).astype(np.uint8)[:, :, np.newaxis]
            del final_composite, mask

            img_earth = Image.fromarray(earth_arr, "RGBA")
            del earth_arr
            
            # --- 6. 대기 후광 & 지구 합성 ---
            halo_radius = radius + 3
            ImageDraw.Draw(canvas_img).ellipse((cx - halo_radius, cy - halo_radius, cx + halo_radius, cy + halo_radius), fill=(80, 120, 204))
            canvas_img.paste(img_earth, (cx - radius, cy - radius), img_earth)

            # --- 7. ISS 그리기 ---
            iss_lat, iss_lon = CelestialCalculator.get_iss_pos()
            if iss_lat is not None:
                sx, sy = project_orthographic(iss_lat, iss_lon)
                if sx is not None:
                    s_img = img_iss.resize((30, 30), Image.Resampling.BILINEAR)
                    canvas_img.paste(s_img, (sx - 15, sy - 15), s_img)

            # 렌더링 끝난 후 명시적 가비지 컬렉터 호출
            gc.collect() 

            return canvas_img
            
        except Exception as e:
            print(f"Rendering Error: {e}")
            import traceback; traceback.print_exc()
            return None

# ==========================================
# 구름 업데이트 워커
# ==========================================
class CloudUpdateWorker(QThread):
    finished = pyqtSignal(str); progress = pyqtSignal(int)
    def __init__(self, save_path):
        super().__init__(); self.save_path = save_path
        self.mode = 'url'; self.api_key = ''; self.target_url = ''
        self.PRODUCT = 'globalir'; self.API_BASE = 'http://re.ssec.wisc.edu/api'; self.ZOOM = 3
    def set_config(self, mode, api_key, url): self.mode = mode; self.api_key = api_key; self.target_url = url
    def run(self):
        try:
            self.progress.emit(10)
            if self.mode == 'api':
                if not self.api_key: self.finished.emit("Error: Key 없음"); return
                date_req = requests.get(f'{self.API_BASE}/time?products={self.PRODUCT}', timeout=10)
                if date_req.status_code != 200: self.finished.emit("API Error"); return
                date_json = json.loads(date_req.content)[self.PRODUCT]
                base_url = (f"{self.API_BASE}/image?products={self.PRODUCT}_{date_json[0]}_{date_json[1]}"
                            f"&equirectangular=true&z={self.ZOOM}&accesskey={self.api_key}")
                width = (2 ** self.ZOOM) * 2 * 256; height = (2 ** self.ZOOM) * 256
                output_image = Image.new('RGB', (width, height))
                total = ((2 ** self.ZOOM) * 2) * (2 ** self.ZOOM); curr = 0
                for x in range((2 ** self.ZOOM) * 2):
                    for y in range((2 ** self.ZOOM)):
                        tile = requests.get(f"{base_url}&x={x}&y={y}", stream=True, timeout=10)
                        if tile.status_code == 200: output_image.paste(Image.open(tile.raw), (x*256, y*256))
                        curr += 1; self.progress.emit(10 + int((curr/total)*70))
            else:
                if not self.target_url: self.finished.emit("Error: URL 없음"); return
                self.progress.emit(30)
                res = requests.get(self.target_url, stream=True, timeout=30)
                if res.status_code == 200: res.raw.decode_content = True; output_image = Image.open(res.raw)
                else: self.finished.emit("URL Error"); return
                self.progress.emit(80)
            if output_image.mode != 'RGB': output_image = output_image.convert('RGB')
            output_image.save(self.save_path, "JPEG")
            self.progress.emit(100); self.finished.emit("구름 완료")
        except Exception as e: self.finished.emit(f"Err: {e}")

# ==========================================
# 메인 앱
# ==========================================
class EarthWallpaperApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # [수정] 절대 경로 계산 (System32 문제 해결)
        if getattr(sys, 'frozen', False):
            self.base_path = os.path.dirname(sys.executable)
        else:
            self.base_path = os.path.dirname(os.path.abspath(__file__))

        # 모든 경로를 self.base_path 기준으로 재설정
        self.earth_dir = os.path.join(self.base_path, "earth")
        self.assets_dir = os.path.join(self.base_path, "assets")
        self.config_file = os.path.join(self.base_path, CONFIG_FILE)
        self.cloud_file = os.path.join(self.assets_dir, "clouds.jpg")
        self.output_file = os.path.join(self.base_path, "current_earth.png")
        self.preview_file = os.path.join(self.base_path, "preview_earth.png")
        
        # 아이콘 로드
        self.app_icon = None
        icon_path = os.path.join(self.base_path, "icon.ico")
        if os.path.exists(icon_path):
            self.app_icon = QIcon(icon_path)
            self.setWindowIcon(self.app_icon)
        
        self.load_config()
        self.setWindowTitle("Earth Wallpaper Manager")
        self.setGeometry(100, 100, 1100, 650)
        self.debounce_timer = QTimer(); self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self.update_preview)

        # 폴더 생성
        if not os.path.exists(self.assets_dir): os.makedirs(self.assets_dir)
        if not os.path.exists(self.earth_dir): os.makedirs(self.earth_dir)
        
        self.init_ui(); self.init_tray()
        self.check_and_create_assets()
        self.cloud_worker = CloudUpdateWorker(self.cloud_file)
        self.cloud_worker.progress.connect(self.update_progress_bar)
        self.cloud_worker.finished.connect(self.on_cloud_update_finished)
        self.restore_ui_state(); self.setup_timer()
        QTimer.singleShot(1000, self.update_wallpaper_process)

    def check_and_create_assets(self):
        missing_files = []
        
        # earth 폴더 확인
        month = datetime.datetime.now().month
        month_map = os.path.join(self.earth_dir, f"m{month:02d}.jpg")
        night_map = os.path.join(self.earth_dir, "night.jpg")
        
        if not os.path.exists(month_map):
            missing_files.append(f"earth/m{month:02d}.jpg (현재 월 지형)")
        if not os.path.exists(night_map):
            missing_files.append("earth/night.jpg (야간 지형)")
        
        # assets 폴더 확인
        star_path = os.path.join(self.assets_dir, "stars.jpg")
        if not os.path.exists(star_path):
            print("Generating stars.jpg...")
            img = Image.new('RGB', (2048, 1024), (0, 0, 0))
            draw = ImageDraw.Draw(img)
            for _ in range(2000):
                x = random.randint(0, 2048); y = random.randint(0, 1024); b = random.randint(50, 255); size = random.choice([1, 1, 1, 2])
                draw.rectangle((x, y, x+size-1, y+size-1), fill=(b, b, b))
            img.save(star_path)
        
        # 누락된 파일 경고
        if missing_files:
            msg = "❗ 필수 파일이 부족합니다:\n\n"
            msg += "\n".join(f"• {f}" for f in missing_files)
            msg += "\n\n경고: 지구 렌더링이 정상적으로 작동하지 않을 수 있습니다.\n\n설정 → earth 폴더에 이미지 파일들을 복사하세요."
            self.show_warning_message(msg)
    
    def show_warning_message(self, msg):
        from PyQt6.QtWidgets import QMessageBox
        dlg = QMessageBox(self)
        dlg.setIcon(QMessageBox.Icon.Warning)
        dlg.setWindowTitle("경고")
        dlg.setText(msg)
        dlg.exec()

    def init_ui(self):
        main_widget = QWidget(); self.setCentralWidget(main_widget); main_layout = QHBoxLayout(main_widget)
        
        left_layout = QVBoxLayout()
        self.preview_label = ResizeLabel("Preview")
        self.preview_label.resized.connect(self.trigger_preview)
        left_layout.addWidget(self.preview_label)
        self.progress_bar = QProgressBar(); self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("QProgressBar { border: 0px; background-color: #f0f0f0; height: 5px; } QProgressBar::chunk { background-color: transparent; }")
        left_layout.addWidget(self.progress_bar)
        main_layout.addLayout(left_layout, stretch=1)

        opts = QWidget(); opts.setFixedWidth(320); opt_layout = QVBoxLayout(opts)
        
        grp = QGroupBox("구름 소스"); gl = QVBoxLayout()
        self.radio_api = QRadioButton("SSEC API"); self.radio_url = QRadioButton("Direct URL")
        bg = QButtonGroup(self); bg.addButton(self.radio_api); bg.addButton(self.radio_url)
        gl.addWidget(self.radio_api)
        self.input_api_key = QLineEdit(); self.input_api_key.setPlaceholderText("Key 입력")
        gl.addWidget(self.input_api_key)
        gl.addWidget(self.radio_url)
        self.input_url = QLineEdit(); self.input_url.setText("http://jikji.duckdns.org:8085/cloud/clouds.jpg")
        gl.addWidget(self.input_url)
        grp.setLayout(gl); opt_layout.addWidget(grp)
        bg.buttonToggled.connect(self.toggle_inputs)

        form = QFormLayout(); form.setContentsMargins(0, 10, 0, 10)
        self.lat_slider, self.lat_spin = self.create_slider_spin(-90, 90, 37, form, "위도:")
        self.lon_slider, self.lon_spin = self.create_slider_spin(-180, 180, 127, form, "경도:")
        self.zoom_slider, self.zoom_spin = self.create_slider_spin(10, 150, 80, form, "Zoom (%):")
        self.opacity_slider, self.opacity_spin = self.create_slider_spin(0, 100, 90, form, "구름 투명도:")
        self.contrast_slider, self.contrast_spin = self.create_slider_spin(50, 250, 160, form, "구름 선명도:")
        
        # [신규] 배경화면 배치 옵션 추가
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["채우기", "맞춤", "확대", "바둑판", "가운데", "스팬"])
        self.layout_combo.setCurrentIndex(2) # Default 확대
        # 배치 변경 시 바로 적용
        self.layout_combo.currentIndexChanged.connect(self.apply_wallpaper)
        form.addRow("배경화면 배치:", self.layout_combo)

        self.interval_combo = QComboBox(); self.interval_combo.addItems(["10분", "30분", "1시간"])
        self.interval_combo.currentIndexChanged.connect(self.setup_timer)
        form.addRow("주기:", self.interval_combo)
        self.check_autorun = QCheckBox("시작 시 실행"); self.check_autorun.stateChanged.connect(self.toggle_autorun)
        form.addRow(self.check_autorun)
        opt_layout.addLayout(form)

        tilt_box = QHBoxLayout(); tilt_box.addWidget(QLabel("자전축:"))
        self.tilt_slider, self.tilt_spin = self.create_slider_spin_float_simple(-180.0, 180.0, 23.5)
        tilt_box.addWidget(self.tilt_slider); tilt_box.addWidget(self.tilt_spin)
        opt_layout.addLayout(tilt_box)

        self.btn_cloud = QPushButton("구름 업데이트"); self.btn_cloud.clicked.connect(self.download_clouds)
        opt_layout.addWidget(self.btn_cloud)
        self.btn_apply = QPushButton("배경화면 적용"); self.btn_apply.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc; padding: 5px;")
        self.btn_apply.clicked.connect(self.apply_wallpaper)
        opt_layout.addWidget(self.btn_apply)
        self.btn_reset = QPushButton("설정 초기화"); self.btn_reset.setFlat(True); self.btn_reset.setStyleSheet("color: #888; font-size: 11px;")
        self.btn_reset.clicked.connect(self.reset_defaults)
        opt_layout.addWidget(self.btn_reset, alignment=Qt.AlignmentFlag.AlignRight)
        opt_layout.addStretch()
        main_layout.addWidget(opts, stretch=0)

    def init_tray(self):
        self.tray = QSystemTrayIcon(self)
        if self.app_icon:
            self.tray.setIcon(self.app_icon)
        else:
            self.tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
            
        menu = QMenu(); menu.addAction("열기", self.show_window); menu.addAction("종료", self.quit_app)
        self.tray.setContextMenu(menu); self.tray.activated.connect(lambda r: self.show_window() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None); self.tray.show()

    def create_slider_spin(self, min_v, max_v, def_v, layout, txt):
        s = QSlider(Qt.Orientation.Horizontal); s.setRange(min_v, max_v); s.setValue(def_v)
        sp = QSpinBox(); sp.setRange(min_v, max_v); sp.setValue(def_v); sp.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons); sp.setFixedWidth(45); sp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.valueChanged.connect(sp.setValue); sp.valueChanged.connect(s.setValue); s.valueChanged.connect(self.trigger_preview); sp.valueChanged.connect(self.trigger_preview)
        h = QHBoxLayout(); h.addWidget(s); h.addWidget(sp); layout.addRow(txt, h)
        return s, sp

    def create_slider_spin_float_simple(self, min_v, max_v, def_v):
        factor = 10; s = QSlider(Qt.Orientation.Horizontal); s.setRange(int(min_v * factor), int(max_v * factor)); s.setValue(int(def_v * factor))
        sp = QDoubleSpinBox(); sp.setRange(min_v, max_v); sp.setValue(def_v); sp.setSingleStep(0.5); sp.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons); sp.setFixedWidth(55); sp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.valueChanged.connect(lambda v: sp.setValue(v / factor)); sp.valueChanged.connect(lambda v: s.setValue(int(v * factor))); s.valueChanged.connect(self.trigger_preview); sp.valueChanged.connect(self.trigger_preview)
        return s, sp

    def toggle_inputs(self): self.input_api_key.setEnabled(self.radio_api.isChecked()); self.input_url.setEnabled(not self.radio_api.isChecked())
    
    def load_config(self):
        # [수정] 기본값에 layout_idx 추가
        self.cfg = {"mode": "url", "api_key": "", "url": "", "lat": 37, "lon": 127, 
                    "tilt": 23.5, "zoom": 80, "opa": 90, "cont": 160, 
                    "int": 2, "auto": False, "layout_idx": 2} # default: 2 (Stretch)
        if os.path.exists(self.config_file):
            try: self.cfg.update(json.load(open(self.config_file, encoding='utf-8')))
            except: pass
    
    def save_config(self):
        self.cfg.update({
            "mode": "api" if self.radio_api.isChecked() else "url", 
            "api_key": self.input_api_key.text(), 
            "url": self.input_url.text(), 
            "lat": self.lat_slider.value(), 
            "lon": self.lon_slider.value(), 
            "tilt": self.tilt_spin.value(), 
            "zoom": self.zoom_slider.value(), 
            "opa": self.opacity_slider.value(), 
            "cont": self.contrast_slider.value(), 
            "int": self.interval_combo.currentIndex(), 
            "auto": self.check_autorun.isChecked(),
            "layout_idx": self.layout_combo.currentIndex() # [추가] 배치 옵션 저장
        })
        json.dump(self.cfg, open(self.config_file, 'w', encoding='utf-8'), indent=4)
    
    def restore_ui_state(self):
        self.radio_api.setChecked(self.cfg["mode"]=="api"); self.radio_url.setChecked(self.cfg["mode"]=="url")
        self.input_api_key.setText(self.cfg["api_key"]); self.input_url.setText(self.cfg["url"])
        self.lat_spin.setValue(self.cfg["lat"]); self.lon_spin.setValue(self.cfg["lon"]); self.tilt_spin.setValue(self.cfg.get("tilt", 23.5))
        self.zoom_spin.setValue(self.cfg["zoom"]); self.opacity_spin.setValue(self.cfg["opa"]); self.contrast_spin.setValue(self.cfg.get("cont", 160))
        self.interval_combo.setCurrentIndex(self.cfg["int"]); self.check_autorun.setChecked(self.cfg["auto"])
        self.layout_combo.setCurrentIndex(self.cfg.get("layout_idx", 2)) # [추가] 배치 복원
        self.toggle_inputs()
    
    def reset_defaults(self):
        self.lat_spin.setValue(37); self.lon_spin.setValue(127); self.tilt_spin.setValue(23.5); self.zoom_spin.setValue(80); self.opacity_spin.setValue(90); self.contrast_spin.setValue(160)
        self.input_url.setText("http://jikji.duckdns.org:8085/cloud/clouds.jpg"); self.radio_url.setChecked(True)
        self.layout_combo.setCurrentIndex(2) # 확대(Stretch)로 리셋
        self.trigger_preview()
    
    def trigger_preview(self): self.debounce_timer.start(100)
    
    def download_clouds(self):
        if not self.cloud_worker.isRunning():
            self.save_config()
            self.cloud_worker.set_config("api" if self.radio_api.isChecked() else "url", self.input_api_key.text(), self.input_url.text())
            self.btn_cloud.setDisabled(True)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("다운로드 중 (%p%)")
            
            # 다운로드 시작 시: 진행바를 기본 파란색(#0078d7)으로 설정
            self.progress_bar.setStyleSheet(
                "QProgressBar { border: 0px; background-color: #f0f0f0; height: 5px; } "
                "QProgressBar::chunk { background-color: #0078d7; }"
            )
            
            self.cloud_worker.start()
    
    def update_progress_bar(self, val): self.progress_bar.setValue(val)
    
    def on_cloud_update_finished(self, msg):
        self.btn_cloud.setDisabled(False)
        self.progress_bar.setFormat(msg)
        
        if "완료" in msg:
            # 다운로드 완료 시: 진행바 색상을 초록색(#4caf50)으로 변경
            self.progress_bar.setStyleSheet(
                "QProgressBar { border: 0px; background-color: #f0f0f0; height: 5px; } "
                "QProgressBar::chunk { background-color: #4caf50; }"
            )
            self.update_wallpaper_process()
            # 3초 뒤에 진행바 리셋
            QTimer.singleShot(3000, self.reset_progress_bar)
        else:
            # 에러 발생 시: 진행바 색상을 빨간색(#f44336)으로 변경
            self.progress_bar.setStyleSheet(
                "QProgressBar { border: 0px; background-color: #f0f0f0; height: 5px; } "
                "QProgressBar::chunk { background-color: #f44336; }"
            )
            QTimer.singleShot(3000, self.reset_progress_bar)

    def reset_progress_bar(self):
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 0px; background-color: #f0f0f0; height: 5px; } "
            "QProgressBar::chunk { background-color: transparent; }"
        )

    def update_wallpaper_process(self):
        s = QApplication.primaryScreen().size(); self.generate_image(self.output_file, s.width(), s.height())
        self.set_wallpaper_style() # [수정] 변경된 함수 호출
        ctypes.windll.user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, self.output_file, SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE)
        self.update_preview()
    
    # [신규] 배경화면 스타일 동적 설정 함수
    def set_wallpaper_style(self):
        idx = self.layout_combo.currentIndex()
        
        # Mapping: Index -> (WallpaperStyle, TileWallpaper)
        # 0:채우기, 1:맞춤, 2:확대, 3:바둑판, 4:가운데, 5:스팬
        styles = {
            0: ("10", "0"), # Fill
            1: ("6", "0"),  # Fit
            2: ("2", "0"),  # Stretch (Default)
            3: ("1", "1"),  # Tile
            4: ("0", "0"),  # Center
            5: ("22", "0")  # Span
        }
        
        wp_style, tile_wp = styles.get(idx, ("2", "0"))
        
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE)
        try: 
            winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, wp_style)
            winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, tile_wp)
        except: pass
        winreg.CloseKey(key)
    
    def update_preview(self):
        s = self.preview_label.size()
        self.generate_image(self.preview_file, s.width(), s.height())
        self.preview_label.clear_pixmap()
        self.preview_label.setPixmap(QPixmap(self.preview_file))
    
    def generate_image(self, path, w, h):
        img = EarthRenderer.render_globe(width=w, height=h, lat=self.lat_slider.value(), lon=self.lon_slider.value(), zoom=self.zoom_slider.value(), tilt=self.tilt_spin.value(), earth_dir=self.earth_dir, assets_dir=self.assets_dir, cloud_path=self.cloud_file, opacity=self.opacity_slider.value(), contrast=self.contrast_slider.value() / 100.0)
        if img: img.save(path)
    
    def apply_wallpaper(self): self.update_wallpaper_process()
    
    def setup_timer(self):
        if hasattr(self, 'timer'): self.timer.stop()
        m = [10, 30, 60][self.interval_combo.currentIndex()]; self.timer = QTimer(self); self.timer.timeout.connect(self.download_clouds); self.timer.start(m * 60 * 1000)
    
    def toggle_autorun(self):
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
        try:
            if self.check_autorun.isChecked():
                # [수정] sys.executable을 사용하여 실제 exe 경로를 레지스트리에 등록
                exe_path = sys.executable
                # 윈도우에서는 경로에 공백이 있을 수 있으므로 따옴표로 감싸는 것이 안전
                winreg.SetValueEx(key, "EarthWallpaper", 0, winreg.REG_SZ, f'"{exe_path}"')
            else:
                winreg.DeleteValue(key, "EarthWallpaper")
        except: pass
        winreg.CloseKey(key)
    
    def closeEvent(self, e):
        if self.tray.isVisible(): self.hide(); self.save_config(); e.ignore()
    def show_window(self): self.show(); self.activateWindow()
    def quit_app(self): self.save_config(); QApplication.quit()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # 중복 실행 방지
    lock_file = QLockFile(QDir.temp().filePath("earth_wallpaper_v2.lock"))
    if not lock_file.tryLock(100):
        sys.exit(0)
        
    app.setQuitOnLastWindowClosed(False)
    EarthWallpaperApp()
    sys.exit(app.exec())