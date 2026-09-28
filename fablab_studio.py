"""
FABLAB AI VISION & DOBOT ROBOTICS STUDIO
Phần mềm tích hợp End-to-End dành cho học sinh Cấp 2 & Cấp 3:
1. Thu thập dữ liệu thông minh (Camera Studio)
2. Huấn luyện AI 1-Click (AI Training Center)
3. Bản sao số 3D thời gian thực (Dobot Live Server - Digital Twin)
4. AI Vision & Tự động phân loại khối màu bằng Dobot (Dobot Auto Sort)
"""

import os
import sys
import time
import math
import json
import webbrowser
import subprocess
from pathlib import Path

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import cv2
import numpy as np

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QUrl
from PyQt6.QtGui import QImage, QPixmap, QFont, QIcon, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QComboBox, QSlider, QProgressBar,
    QTextEdit, QGroupBox, QGridLayout, QFrame, QMessageBox, QSplitter
)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
    print("[!] Cảnh báo: PyQt6-WebEngine chưa được nạp.")

# Thêm thư mục DOBOT vào sys.path để tái sử dụng module đồng nghiệp
BASE_DIR = Path(__file__).resolve().parent
DOBOT_DIR = BASE_DIR / "DOBOT"
if str(DOBOT_DIR) not in sys.path:
    sys.path.append(str(DOBOT_DIR))

try:
    from dobot_auto_sort import (
        HomographyTransformer, DobotExecutor, DEFAULT_DROP_TARGET,
        Z_PICK_FLANGE, Z_SAFE_FLANGE, OFFSET_PICK_X, OFFSET_PICK_Y,
        DROP_TARGETS_BY_COLOR
    )
    HAS_DOBOT_MODULE = True
except Exception as e:
    HAS_DOBOT_MODULE = False
    Z_PICK_FLANGE = -51.7
    Z_SAFE_FLANGE = 35.0
    OFFSET_PICK_X = 0.0
    OFFSET_PICK_Y = 0.0
    DEFAULT_DROP_TARGET = {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Thả (49.2, -230.1)"}
    DROP_TARGETS_BY_COLOR = {}
    print(f"[!] Cảnh báo module Dobot: {e}")

try:
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

# Màu nhận diện và BGR tương ứng
CLASS_INFO = {
    "cube_blue": {"name": "Cube Xanh Dương", "color_hex": "#0088ff", "bgr": (255, 120, 0)},
    "cube_green": {"name": "Cube Xanh Lục", "color_hex": "#00d632", "bgr": (0, 230, 0)},
    "cube_red": {"name": "Cube Đỏ", "color_hex": "#ff3333", "bgr": (0, 0, 255)},
    "cube_yellow": {"name": "Cube Vàng", "color_hex": "#ffcc00", "bgr": (0, 230, 255)},
    "background": {"name": "Bối Cảnh Nền", "color_hex": "#888888", "bgr": (128, 128, 128)},
}


# ==============================================================================
# QUẢN LÝ TIẾN TRÌNH DOBOT LIVE SERVER
# ==============================================================================
class LiveServerManager:
    def __init__(self):
        self.process = None

    def start_if_needed(self):
        """Khởi động dobot_live_server.py nếu chưa có server nào chạy trên port 8080."""
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(("127.0.0.1", 8080))
            s.close()
            print("[LiveServerManager] [+] Live Server 8080 đã đang chạy sẵn.")
            return True
        except Exception:
            pass

        server_script = DOBOT_DIR / "dobot_live_server.py"
        if server_script.exists():
            print("[LiveServerManager] [*] Đang khởi động dobot_live_server.py ngầm cho Tab 3...")
            try:
                self.process = subprocess.Popen(
                    [sys.executable, "-u", str(server_script)],
                    cwd=str(DOBOT_DIR),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(1.8)
                return True
            except Exception as e:
                print(f"[LiveServerManager] [!] Lỗi khởi động live server: {e}")
        return False

    def stop(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2.0)
            except Exception:
                pass
            self.process = None


# ==============================================================================
# LUỒNG ĐỌC CAMERA ĐỘC LẬP (30-60 FPS)
# ==============================================================================
class CameraThread(QThread):
    frame_received = pyqtSignal(np.ndarray)
    camera_error = pyqtSignal(str)

    def __init__(self, cam_id=1):
        super().__init__()
        self.cam_id = cam_id
        self.running = False
        self.cap = None

    def set_camera_id(self, cam_id):
        self.cam_id = cam_id
        if self.running:
            self.stop()
            self.start()

    def run(self):
        self.running = True
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_V4L2
        self.cap = cv2.VideoCapture(self.cam_id, backend)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.cam_id)
        if not self.cap.isOpened() and self.cam_id != 0:
            self.cap = cv2.VideoCapture(0, backend)

        if not self.cap.isOpened():
            self.camera_error.emit(f"Không thể mở Camera {self.cam_id}")
            self.running = False
            return

        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        while self.running:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.frame_received.emit(frame)
            else:
                time.sleep(0.01)

        if self.cap:
            self.cap.release()

    def stop(self):
        self.running = False
        self.wait(1000)


# ==============================================================================
# LUỒNG HUẤN LUYỆN AI NGẦM (1-CLICK TRAINING)
# ==============================================================================
class TrainingWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    training_finished = pyqtSignal(bool, str)
    log_received = pyqtSignal(str)

    def __init__(self, epochs=15):
        super().__init__()
        self.epochs = epochs

    def run(self):
        try:
            self.progress_updated.emit(10, "Bắt đầu tổng hợp dữ liệu & Augmentation...")
            self.log_received.emit("[1/3] Đang chạy sinh tập dữ liệu (Cutout ngón tay + Ghép nền)...")
            
            import generate_yolo_dataset
            generate_yolo_dataset.main()
            self.log_received.emit("✓ Đã sinh xong tập dữ liệu YOLO chuẩn xác.")

            self.progress_updated.emit(35, "Đang nạp mô hình nền tảng YOLO11...")
            self.log_received.emit("[2/3] Khởi động Ultralytics YOLO...")

            from ultralytics import YOLO
            data_yaml = Path("yolo_dataset/data.yaml")
            if not data_yaml.exists():
                self.training_finished.emit(False, "Không tìm thấy file yolo_dataset/data.yaml")
                return

            model = YOLO("yolo11n.pt")
            self.progress_updated.emit(50, f"Đang huấn luyện {self.epochs} epochs trên CPU/GPU...")
            self.log_received.emit(f"Bắt đầu huấn luyện {self.epochs} epochs...")

            results = model.train(
                data=str(data_yaml.resolve()),
                epochs=self.epochs,
                imgsz=416,
                batch=8,
                project="models_trained",
                name="fablab_run",
                exist_ok=True,
                verbose=False
            )

            best_weight = Path("models_trained/fablab_run/weights/best.pt")
            if best_weight.exists():
                target_weight = Path("models/best_11_trained.pt")
                import shutil
                shutil.copy(str(best_weight), str(target_weight))
                self.log_received.emit(f"✓ Đã lưu mô hình mới tại: {target_weight}")
                self.progress_updated.emit(100, "Hoàn tất huấn luyện!")
                self.training_finished.emit(True, "Huấn luyện AI thành công! Mô hình đã sẵn sàng gắp thả.")
            else:
                self.training_finished.emit(False, "Không tìm thấy file trọng số đầu ra.")

        except Exception as e:
            self.training_finished.emit(False, f"Lỗi trong quá trình huấn luyện: {str(e)}")


# ==============================================================================
# GIAO DIỆN CHÍNH (FABLAB STUDIO: 4 TABS)
# ==============================================================================
class FabLabStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FabLab STEM - AI Vision & Dobot Robotics Studio")
        self.setMinimumSize(1240, 820)
        self.resize(1340, 880)

        # Trình quản lý Live Server ngầm
        self.live_server_mgr = LiveServerManager()
        self.live_server_mgr.start_if_needed()

        # Biến trạng thái
        self.current_frame = None
        self.selected_class = "cube_red"
        self.is_recording = False
        self.record_timer = QTimer()
        self.record_timer.timeout.connect(self._save_recorded_frame)

        # AI & Robot Objects
        self.yolo_model = None
        self.transformer = None
        self.executor = None
        self.detected_cubes = []
        self.auto_sort_active = False
        self.last_auto_pick = 0

        self._init_homography_and_models()
        self._setup_ui()
        self._apply_dark_theme()

        # Khởi động luồng Camera
        self.camera_thread = CameraThread(cam_id=1)
        self.camera_thread.frame_received.connect(self._on_frame_received)
        self.camera_thread.start()

    def _init_homography_and_models(self):
        """Khởi tạo Transformer và executor nếu có module Dobot."""
        if HAS_DOBOT_MODULE:
            try:
                self.transformer = HomographyTransformer()
                self.executor = DobotExecutor()
            except Exception as e:
                print(f"[!] Lỗi khởi tạo Homography/Dobot: {e}")

        # Nạp mặc định model tối ưu nhất
        try:
            from ultralytics import YOLO
            for m_path in [Path("models/best_v8_more_augmentation.pt"), Path("models/best_11.pt")]:
                if m_path.exists():
                    self.yolo_model = YOLO(str(m_path))
                    self.loaded_model_name = m_path.name
                    print(f"[+] Studio đã nạp: {m_path.name}")
                    break
        except Exception as e:
            print(f"[!] Chưa nạp được YOLO: {e}")

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Header thương hiệu FabLab
        header_layout = QHBoxLayout()
        title_label = QLabel("🚀 FABLAB STEM - AI VISION & DOBOT ROBOTICS STUDIO")
        title_label.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #00d6ff;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()
        self.cam_combo = QComboBox()
        self.cam_combo.addItems(["Camera USB ngoài (Cam 1)", "Camera Laptop (Cam 0)"])
        self.cam_combo.currentIndexChanged.connect(self._on_cam_changed)
        header_layout.addWidget(QLabel("Chọn Camera:"))
        header_layout.addWidget(self.cam_combo)

        main_layout.addLayout(header_layout)

        # 4 Tab chính theo yêu cầu
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        self.tab_collect = self._create_collect_tab()
        self.tab_train = self._create_train_tab()
        self.tab_live_server = self._create_live_server_tab()
        self.tab_auto_sort = self._create_auto_sort_tab()

        self.tabs.addTab(self.tab_collect, "📸 1. Thu Thập Dữ Liệu")
        self.tabs.addTab(self.tab_train, "🧠 2. Huấn Luyện AI (1-Click)")
        self.tabs.addTab(self.tab_live_server, "🧊 3. Bản Sao Số 3D (Live Server)")
        self.tabs.addTab(self.tab_auto_sort, "🦾 4. AI Vision & Tự Động Phân Loại (Auto Sort)")

        main_layout.addWidget(self.tabs)

    # --------------------------------------------------------------------------
    # TAB 1: THU THẬP DỮ LIỆU
    # --------------------------------------------------------------------------
    def _create_collect_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        # Cột trái: Khung hiển thị Camera
        self.collect_video_label = QLabel("Đang mở camera...")
        self.collect_video_label.setMinimumSize(640, 480)
        self.collect_video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.collect_video_label.setStyleSheet("background-color: #111; border: 2px solid #333; border-radius: 8px;")
        layout.addWidget(self.collect_video_label, stretch=3)

        # Cột phải: Bảng điều khiển chọn nhãn & chụp
        panel = QVBoxLayout()
        panel.setSpacing(12)

        grp_class = QGroupBox("Chọn Nhãn Vật Thể Thu Thập")
        grp_class_layout = QVBoxLayout(grp_class)

        self.class_buttons = {}
        for cls_name, info in CLASS_INFO.items():
            btn = QPushButton(f"● {info['name']}")
            btn.setCheckable(True)
            btn.setChecked(cls_name == self.selected_class)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: #21262d; border: 2px solid {info['color_hex']}; color: white; border-radius: 6px; padding: 7px; text-align: left; font-weight: bold; }}
                QPushButton:checked {{ background-color: {info['color_hex']}; color: {'black' if cls_name in ['cube_yellow', 'cube_green'] else 'white'}; }}
            """)
            btn.clicked.connect(lambda _, c=cls_name: self._select_class(c))
            self.class_buttons[cls_name] = btn
            grp_class_layout.addWidget(btn)

        panel.addWidget(grp_class)

        grp_actions = QGroupBox("Thao Tác Chụp Ảnh")
        grp_act_layout = QVBoxLayout(grp_actions)

        self.btn_take_photo = QPushButton("📷 CHỤP 1 ẢNH (Phím SPACE)")
        self.btn_take_photo.setFixedHeight(40)
        self.btn_take_photo.setStyleSheet("background-color: #238636; color: white; font-weight: bold; border-radius: 6px;")
        self.btn_take_photo.clicked.connect(self._take_single_shot)
        grp_act_layout.addWidget(self.btn_take_photo)

        self.btn_record = QPushButton("🔴 BẮT ĐẦU CHỤP LIÊN TỤC (Phím R)")
        self.btn_record.setFixedHeight(40)
        self.btn_record.setStyleSheet("background-color: #cc292b; color: white; font-weight: bold; border-radius: 6px;")
        self.btn_record.clicked.connect(self._toggle_recording)
        grp_act_layout.addWidget(self.btn_record)

        panel.addWidget(grp_actions)

        grp_stats = QGroupBox("Thống Kê Tập Dữ Liệu")
        grp_stats_layout = QVBoxLayout(grp_stats)
        self.lbl_stats = QLabel("Đang quét dataset_raw/...")
        self.lbl_stats.setStyleSheet("font-size: 12px; line-height: 1.4;")
        self._update_stats_label()
        grp_stats_layout.addWidget(self.lbl_stats)
        panel.addWidget(grp_stats)

        panel.addStretch()
        layout.addLayout(panel, stretch=1)
        return tab

    # --------------------------------------------------------------------------
    # TAB 2: HUẤN LUYỆN AI (1-CLICK TRAINING)
    # --------------------------------------------------------------------------
    def _create_train_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        banner = QLabel("🧠 TRUNG TÂM HUẤN LUYỆN MÔ HÌNH THỊ GIÁC AI (YOLO11)")
        banner.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        banner.setStyleSheet("color: #58a6ff;")
        layout.addWidget(banner)

        desc = QLabel(
            "Tự động chạy pipeline hoàn chỉnh: Sinh nhãn YOLO -> Augmentation (Mô phỏng ngón tay che khuất & ánh sáng) "
            "-> Transfer Learning trên YOLO11 Nano. Sau khi huấn luyện, model sẽ tự động sẵn sàng cho cánh tay Dobot."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8b949e; font-size: 13px;")
        layout.addWidget(desc)

        action_box = QHBoxLayout()
        self.btn_start_train = QPushButton("🚀 BẮT ĐẦU HUẤN LUYỆN (1-CLICK TRAIN)")
        self.btn_start_train.setFixedHeight(45)
        self.btn_start_train.setStyleSheet("background-color: #1f6feb; color: white; font-size: 13px; font-weight: bold; border-radius: 6px;")
        self.btn_start_train.clicked.connect(self._start_training)
        action_box.addWidget(self.btn_start_train)

        self.btn_preset_model = QPushButton("⚡ Nạp Model Chuẩn (best_11.pt)")
        self.btn_preset_model.setFixedHeight(45)
        self.btn_preset_model.setStyleSheet("background-color: #238636; color: white; font-weight: bold; border-radius: 6px;")
        self.btn_preset_model.clicked.connect(self._use_preset_model)
        action_box.addWidget(self.btn_preset_model)

        self.btn_export_colab = QPushButton("☁️ Xuất Dataset Lên Google Colab")
        self.btn_export_colab.setFixedHeight(45)
        self.btn_export_colab.setStyleSheet("background-color: #d29922; color: black; font-weight: bold; border-radius: 6px;")
        self.btn_export_colab.clicked.connect(self._export_to_colab)
        action_box.addWidget(self.btn_export_colab)

        layout.addLayout(action_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("QProgressBar { height: 18px; border-radius: 9px; text-align: center; } QProgressBar::chunk { background-color: #2ea043; border-radius: 9px; }")
        layout.addWidget(self.progress_bar)

        self.lbl_train_status = QLabel("Trạng thái: Sẵn sàng huấn luyện.")
        self.lbl_train_status.setStyleSheet("font-weight: bold; color: #7ee787;")
        layout.addWidget(self.lbl_train_status)

        layout.addWidget(QLabel("Nhật ký Huấn Luyện (Training Log):"))
        self.txt_train_log = QTextEdit()
        self.txt_train_log.setReadOnly(True)
        self.txt_train_log.setStyleSheet("background-color: #0d1117; color: #c9d1d9; font-family: Consolas, monospace; font-size: 12px; border: 1px solid #30363d; border-radius: 6px;")
        layout.addWidget(self.txt_train_log, stretch=1)

        return tab

    # --------------------------------------------------------------------------
    # TAB 3: BẢN SAO SỐ 3D (DOBOT LIVE SERVER) - "BÊ Y CHANG SERVER_LIVE SANG"
    # --------------------------------------------------------------------------
    def _create_live_server_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Thanh công cụ trên cùng của Tab 3
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(6, 2, 6, 2)

        self.lbl_server_status = QLabel("🟢 Live Digital Twin 3D: http://127.0.0.1:8080")
        self.lbl_server_status.setStyleSheet("color: #2ed573; font-weight: bold; font-size: 12px;")
        top_bar.addWidget(self.lbl_server_status)

        top_bar.addStretch()

        self.btn_reload_3d = QPushButton("🔄 Tải lại 3D")
        self.btn_reload_3d.setStyleSheet("background-color: #21262d; border: 1px solid #444; padding: 6px 12px; font-weight: bold; border-radius: 6px;")
        self.btn_reload_3d.clicked.connect(self._reload_3d_view)
        top_bar.addWidget(self.btn_reload_3d)

        self.btn_open_ext_browser = QPushButton("🌐 Mở Trình Duyệt Ngoài")
        self.btn_open_ext_browser.setStyleSheet("background-color: #1f6feb; color: white; padding: 6px 12px; font-weight: bold; border-radius: 6px;")
        self.btn_open_ext_browser.clicked.connect(lambda: webbrowser.open("http://127.0.0.1:8080"))
        top_bar.addWidget(self.btn_open_ext_browser)

        layout.addLayout(top_bar)

        # Nhúng Web Engine hiển thị Bản sao số 3D của dobot_visualizer.html
        if HAS_WEBENGINE:
            self.web_view = QWebEngineView()
            self.web_view.setUrl(QUrl("http://127.0.0.1:8080"))
            layout.addWidget(self.web_view, stretch=1)
        else:
            fallback = QLabel("Vui lòng mở http://127.0.0.1:8080 trên trình duyệt để tương tác 3D.")
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(fallback, stretch=1)

        return tab

    def _reload_3d_view(self):
        if hasattr(self, 'web_view') and self.web_view:
            self.web_view.reload()

    # --------------------------------------------------------------------------
    # TAB 4: AI VISION & TỰ ĐỘNG PHÂN LOẠI (DOBOT AUTO SORT)
    # --------------------------------------------------------------------------
    def _create_auto_sort_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Cột trái: Khung hiển thị Camera AI & Click-to-Pick
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # Thanh tiêu đề camera + nút Toggle Mở rộng/Thu gọn Camera
        cam_header = QHBoxLayout()
        cam_title = QLabel("📹 Luồng Camera Nhận Diện AI & Gắp Thả (Click-to-Pick)")
        cam_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        cam_title.setStyleSheet("color: #00d632;")
        cam_header.addWidget(cam_title)

        cam_header.addStretch()

        # NÚT TOGGLE MỞ RỘNG CAMERA (ẨN/HIỆN BẢNG ĐIỀU KHIỂN BÊN PHẢI)
        self.btn_toggle_cam_expand = QPushButton("⛶ Mở Rộng Toàn Khung (Ẩn Menu)")
        self.btn_toggle_cam_expand.setStyleSheet("background-color: #21262d; border: 1px solid #444; border-radius: 6px; padding: 4px 10px; font-weight: bold;")
        self.btn_toggle_cam_expand.clicked.connect(self._toggle_auto_sort_camera_expand)
        cam_header.addWidget(self.btn_toggle_cam_expand)

        left_layout.addLayout(cam_header)

        # Màn hình video có gắn sự kiện click chuột
        self.vision_video_label = QLabel("Đang tải mô hình YOLO...")
        self.vision_video_label.setMinimumSize(640, 480)
        self.vision_video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vision_video_label.setStyleSheet("background-color: #0d1117; border: 2px solid #30363d; border-radius: 8px;")
        self.vision_video_label.mousePressEvent = self._on_vision_mouse_click
        self.vision_video_label.setCursor(Qt.CursorShape.CrossCursor)
        left_layout.addWidget(self.vision_video_label, stretch=1)

        hint = QLabel("💡 Hướng dẫn: Click chuột trực tiếp vào khối cube bất kỳ trên màn hình để Dobot tự động bay đến gắp!")
        hint.setStyleSheet("color: #38d9a9; font-weight: bold; font-size: 11.5px;")
        left_layout.addWidget(hint)

        layout.addWidget(left_widget, stretch=3)

        # Cột phải: Bảng điều khiển Robot & Tinh chỉnh của dobot_auto_sort.py (Có thể Toggle Ẩn/Hiện)
        self.auto_sort_right_widget = QWidget()
        right_panel = QVBoxLayout(self.auto_sort_right_widget)
        right_panel.setContentsMargins(0, 0, 0, 0)
        right_panel.setSpacing(10)

        # Box 1: Kết nối Robot Dobot
        grp_dobot = QGroupBox("Kết Nối Cánh Tay Dobot Magician")
        grp_dobot_layout = QVBoxLayout(grp_dobot)

        self.lbl_dobot_status = QLabel("Trạng thái: Đang kết nối Live Server...")
        self.lbl_dobot_status.setStyleSheet("color: #2ed573; font-weight: bold;")
        grp_dobot_layout.addWidget(self.lbl_dobot_status)

        conn_btns = QHBoxLayout()
        self.btn_recheck_conn = QPushButton("🔄 Kiểm tra kết nối")
        self.btn_recheck_conn.clicked.connect(self._check_dobot_status)
        self.btn_reset_dobot = QPushButton("⚠️ Dừng / Xóa lỗi")
        self.btn_reset_dobot.setStyleSheet("background-color: #555; color: #ff9999;")
        self.btn_reset_dobot.clicked.connect(self._reset_dobot_alarm)
        conn_btns.addWidget(self.btn_recheck_conn)
        conn_btns.addWidget(self.btn_reset_dobot)
        grp_dobot_layout.addLayout(conn_btns)
        right_panel.addWidget(grp_dobot)

        # Box 2: Điều khiển phân loại (Auto Sort)
        grp_actions = QGroupBox("Chế Độ Phân Loại (Auto Sort)")
        grp_act_layout = QVBoxLayout(grp_actions)

        self.btn_auto_sort = QPushButton("🤖 BẬT TỰ ĐỘNG PHÂN LOẠI (AUTO)")
        self.btn_auto_sort.setFixedHeight(45)
        self.btn_auto_sort.setCheckable(True)
        self.btn_auto_sort.setStyleSheet("""
            QPushButton { background-color: #21262d; color: white; font-weight: bold; border-radius: 6px; border: 2px solid #555; }
            QPushButton:checked { background-color: #d9480f; border-color: #ff922b; }
        """)
        self.btn_auto_sort.clicked.connect(self._toggle_auto_sort)
        grp_act_layout.addWidget(self.btn_auto_sort)

        self.btn_pick_first = QPushButton("🎯 Gắp Khối Đầu Tiên (Phím SPACE)")
        self.btn_pick_first.setFixedHeight(38)
        self.btn_pick_first.setStyleSheet("background-color: #1971c2; color: white; font-weight: bold; border-radius: 6px;")
        self.btn_pick_first.clicked.connect(self._pick_first_cube)
        grp_act_layout.addWidget(self.btn_pick_first)
        right_panel.addWidget(grp_actions)

        # Box 3: Tinh chỉnh AI Model & Ngưỡng nhận diện
        grp_ai = QGroupBox("Cấu Hình Mô Hình AI")
        grp_ai_layout = QVBoxLayout(grp_ai)

        self.combo_models = QComboBox()
        self.combo_models.addItem("YOLOv8 Nano (best_v8_more_augmentation.pt - Nhạy cao)", "best_v8_more_augmentation.pt")
        self.combo_models.addItem("YOLO11 Nano (best_11.pt - Chống nhận nhầm)", "best_11.pt")
        self.combo_models.currentIndexChanged.connect(self._on_model_selection_changed)
        grp_ai_layout.addWidget(QLabel("Mô hình YOLO:"))
        grp_ai_layout.addWidget(self.combo_models)

        grp_ai_layout.addWidget(QLabel("Ngưỡng tự tin (Confidence):"))
        self.slider_conf = QSlider(Qt.Orientation.Horizontal)
        self.slider_conf.setRange(30, 95)
        self.slider_conf.setValue(65)
        self.lbl_conf_val = QLabel("65%")
        self.slider_conf.valueChanged.connect(lambda v: self.lbl_conf_val.setText(f"{v}%"))

        slider_box = QHBoxLayout()
        slider_box.addWidget(self.slider_conf)
        slider_box.addWidget(self.lbl_conf_val)
        grp_ai_layout.addLayout(slider_box)
        right_panel.addWidget(grp_ai)

        # Box 4: Thông số Tọa độ Điểm thả & Calib
        grp_params = QGroupBox("Thông Số Calib & Tọa Độ")
        grp_params_layout = QVBoxLayout(grp_params)
        self.lbl_calib_info = QLabel(
            "• Điểm thả: X=49.2, Y=-230.1, Z=-44.0\n"
            "• Độ cao gắp: Z_Flange=-51.7 mm\n"
            "• Độ cao an toàn: Z_Flange=35.0 mm\n"
            "• Sai số Homography: 0.00 mm (Offset: 0.0)"
        )
        self.lbl_calib_info.setStyleSheet("color: #94a3b8; font-size: 11px; font-family: monospace;")
        grp_params_layout.addWidget(self.lbl_calib_info)
        right_panel.addWidget(grp_params)

        # Box 5: Danh sách phôi đang nhận diện
        grp_cubes = QGroupBox("Khối Phôi Trong Tầm Nhìn")
        grp_cubes_layout = QVBoxLayout(grp_cubes)
        self.lbl_detected_list = QLabel("Chưa phát hiện khối màu nào.")
        self.lbl_detected_list.setStyleSheet("color: #adb5bd; font-size: 11px;")
        grp_cubes_layout.addWidget(self.lbl_detected_list)
        right_panel.addWidget(grp_cubes)

        right_panel.addStretch()
        layout.addWidget(self.auto_sort_right_widget, stretch=1)
        return tab

    def _toggle_auto_sort_camera_expand(self):
        """Toggle mở rộng/thu gọn camera (ẩn/hiện bảng điều khiển bên phải)."""
        is_visible = self.auto_sort_right_widget.isVisible()
        self.auto_sort_right_widget.setVisible(not is_visible)
        if is_visible:
            self.btn_toggle_cam_expand.setText("⛶ Hiện Bảng Điều Khiển")
            self.btn_toggle_cam_expand.setStyleSheet("background-color: #1971c2; color: white; border-radius: 6px; padding: 4px 10px; font-weight: bold;")
        else:
            self.btn_toggle_cam_expand.setText("⛶ Mở Rộng Toàn Khung (Ẩn Menu)")
            self.btn_toggle_cam_expand.setStyleSheet("background-color: #21262d; border: 1px solid #444; border-radius: 6px; padding: 4px 10px; font-weight: bold;")

    def _on_model_selection_changed(self, idx):
        model_filename = self.combo_models.currentData()
        p = Path("models") / model_filename
        if p.exists():
            try:
                from ultralytics import YOLO
                self.yolo_model = YOLO(str(p))
                self.loaded_model_name = p.name
                QMessageBox.information(self, "Đổi Mô Hình", f"Đã chuyển sang mô hình: {p.name}")
            except Exception as e:
                QMessageBox.critical(self, "Lỗi Nạp Model", str(e))

    def _check_dobot_status(self):
        if self.executor:
            is_http = self.executor.check_http_server()
            if is_http:
                self.lbl_dobot_status.setText("Đã kết nối qua Dobot Live Server (HTTP 8080)")
                self.lbl_dobot_status.setStyleSheet("color: #2ed573; font-weight: bold;")
            elif self.executor.ser and self.executor.ser.is_open:
                self.lbl_dobot_status.setText(f"Đã kết nối trực tiếp Serial: {self.executor.ser.port}")
                self.lbl_dobot_status.setStyleSheet("color: #2ed573; font-weight: bold;")
            else:
                self.lbl_dobot_status.setText("Chưa kết nối (Đang thử lại...)")
                self.lbl_dobot_status.setStyleSheet("color: #ff4757;")

    # --------------------------------------------------------------------------
    # XỬ LÝ SỰ KIỆN CAMERA & RENDER TỪNG FRAME
    # --------------------------------------------------------------------------
    def _on_frame_received(self, frame):
        self.current_frame = frame
        current_tab = self.tabs.currentIndex()

        # Render cho Tab 1: Thu thập
        if current_tab == 0:
            h, w = frame.shape[:2]
            display_frame = frame.copy()
            if self.is_recording:
                cv2.circle(display_frame, (30, 30), 10, (0, 0, 255), -1)
                cv2.putText(display_frame, "DANG LUU LIEN TUC...", (50, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
            self.collect_video_label.setPixmap(QPixmap.fromImage(qimg).scaled(
                self.collect_video_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))

        # Render cho Tab 4: AI Vision & Dobot Auto Sort
        elif current_tab == 3:
            display_frame = frame.copy()
            h, w = frame.shape[:2]
            conf_th = self.slider_conf.value() / 100.0

            detected = []
            if self.yolo_model is not None:
                results = self.yolo_model.predict(display_frame, imgsz=416, conf=conf_th, verbose=False)
                boxes = results[0].boxes
                if boxes is not None:
                    for b in boxes:
                        cls_id = int(b.cls[0])
                        cls_name = self.yolo_model.names.get(cls_id, f"cube_{cls_id}")
                        conf = float(b.conf[0])
                        xyxy = b.xyxy[0].cpu().numpy().astype(int)
                        x1, y1, x2, y2 = xyxy
                        bw, bh = x2 - x1, y2 - y1

                        # Lọc kích thước
                        if bw * bh < 250:
                            continue

                        cx, cy = x1 + bw // 2, y1 + bh // 2
                        rx, ry = 0.0, 0.0
                        if self.transformer and self.transformer.H is not None:
                            rx, ry = self.transformer.pixel_to_dobot(cx, cy)
                            rx += OFFSET_PICK_X
                            ry += OFFSET_PICK_Y

                        color = CLASS_INFO.get(cls_name, {}).get("bgr", (0, 255, 255))
                        cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
                        cv2.circle(display_frame, (cx, cy), 4, (0, 255, 255), -1)

                        lbl_text = f"{cls_name} {int(conf*100)}% | X={rx:.0f}, Y={ry:.0f}"
                        cv2.putText(display_frame, lbl_text, (x1, max(15, y1 - 6)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                        detected.append({
                            "name": cls_name, "box": (x1, y1, bw, bh),
                            "rx": rx, "ry": ry
                        })

            self.detected_cubes = detected

            # Cập nhật danh sách text
            if detected:
                txt = ""
                for idx, c in enumerate(detected[:4]):
                    dist = math.hypot(c["rx"], c["ry"])
                    reach = "✓ Trong tầm" if 140.0 <= dist <= 330.0 else "⚠️ Ngoài tầm"
                    txt += f"[{idx+1}] {c['name']}: ({c['rx']:.0f}, {c['ry']:.0f}) - {reach}\n"
                self.lbl_detected_list.setText(txt.strip())
            else:
                self.lbl_detected_list.setText("Chưa phát hiện khối màu nào.")

            # Tự động gắp nếu bật AUTO
            if self.auto_sort_active and self.executor and not self.executor.is_busy:
                if time.time() - self.last_auto_pick > 2.0 and detected:
                    valid_cubes = [c for c in detected if 140.0 <= math.hypot(c["rx"], c["ry"]) <= 330.0]
                    if valid_cubes:
                        target = valid_cubes[0]
                        self.executor.pick_and_place_async(target["rx"], target["ry"], target["name"])
                        self.last_auto_pick = time.time()

            rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
            self.vision_video_label.setPixmap(QPixmap.fromImage(qimg).scaled(
                self.vision_video_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))

    # --------------------------------------------------------------------------
    # THAO TÁC TAB 1: CHỤP ẢNH
    # --------------------------------------------------------------------------
    def _select_class(self, cls_name):
        self.selected_class = cls_name
        for c, btn in self.class_buttons.items():
            btn.setChecked(c == cls_name)

    def _toggle_recording(self):
        self.is_recording = not self.is_recording
        if self.is_recording:
            self.btn_record.setText("⏹️ DỪNG LƯU LIÊN TỤC (Phím R)")
            self.btn_record.setStyleSheet("background-color: #ffaa00; color: black; font-weight: bold; border-radius: 6px;")
            self.record_timer.start(140) # ~7 fps
        else:
            self.btn_record.setText("🔴 BẮT ĐẦU CHỤP LIÊN TỤC (Phím R)")
            self.btn_record.setStyleSheet("background-color: #cc292b; color: white; font-weight: bold; border-radius: 6px;")
            self.record_timer.stop()
            self._update_stats_label()

    def _save_recorded_frame(self):
        if self.current_frame is not None:
            self._save_frame(self.current_frame, self.selected_class)

    def _take_single_shot(self):
        if self.current_frame is not None:
            self._save_frame(self.current_frame, self.selected_class)
            self._update_stats_label()

    def _save_frame(self, frame, cls_name):
        folder = Path("dataset_raw") / cls_name
        folder.mkdir(parents=True, exist_ok=True)
        count = len(list(folder.glob("*.jpg"))) + 1
        filepath = folder / f"img_{count:04d}.jpg"
        cv2.imwrite(str(filepath), frame)

    def _update_stats_label(self):
        text = "<b>Số lượng ảnh đã thu thập:</b><br>"
        for cls_name, info in CLASS_INFO.items():
            folder = Path("dataset_raw") / cls_name
            cnt = len(list(folder.glob("*.jpg"))) if folder.exists() else 0
            text += f"• <span style='color:{info['color_hex']}'>{info['name']}</span>: <b>{cnt}</b> ảnh<br>"
        self.lbl_stats.setText(text)

    def _on_cam_changed(self, idx):
        cam_id = 1 if idx == 0 else 0
        self.camera_thread.set_camera_id(cam_id)

    # --------------------------------------------------------------------------
    # THAO TÁC TAB 2: HUẤN LUYỆN
    # --------------------------------------------------------------------------
    def _start_training(self):
        self.btn_start_train.setEnabled(False)
        self.txt_train_log.clear()
        self.worker = TrainingWorker(epochs=15)
        self.worker.progress_updated.connect(lambda p, msg: (self.progress_bar.setValue(p), self.lbl_train_status.setText(msg)))
        self.worker.log_received.connect(lambda log: self.txt_train_log.append(log))
        self.worker.training_finished.connect(self._on_training_finished)
        self.worker.start()

    def _on_training_finished(self, success, msg):
        self.btn_start_train.setEnabled(True)
        if success:
            QMessageBox.information(self, "Thành Công", msg)
            try:
                from ultralytics import YOLO
                new_m = Path("models/best_11_trained.pt")
                if new_m.exists():
                    self.yolo_model = YOLO(str(new_m))
            except Exception:
                pass
            self.tabs.setCurrentIndex(3) # Chuyển ngay sang tab gắp robot (Tab 4)
        else:
            QMessageBox.critical(self, "Lỗi Huấn Luyện", f"Có lỗi xảy ra: {msg}")

    def _use_preset_model(self):
        preset_path = Path("models/best_11.pt")
        if preset_path.exists():
            from ultralytics import YOLO
            self.yolo_model = YOLO(str(preset_path))
            QMessageBox.information(self, "Nạp Model Mẫu", "Đã nạp mô hình mẫu YOLO11 Nano! Chuyển sang Tab Phân loại.")
            self.tabs.setCurrentIndex(3)
        else:
            QMessageBox.warning(self, "Thiếu file", "Không tìm thấy models/best_11.pt!")

    def _export_to_colab(self):
        import zip_dataset
        zip_dataset.main()
        webbrowser.open("https://colab.research.google.com/")
        QMessageBox.information(self, "Google Colab", "Đã nén xong yolo_dataset.zip! Trình duyệt đã mở Colab.")

    # --------------------------------------------------------------------------
    # THAO TÁC TAB 4: CLICK TO PICK & AUTO SORT
    # --------------------------------------------------------------------------
    def _on_vision_mouse_click(self, event):
        """Click chuột trực tiếp vào khối cube để Dobot gắp."""
        if not self.executor or self.executor.is_busy:
            return

        lbl_w = self.vision_video_label.width()
        lbl_h = self.vision_video_label.height()
        pos = event.position()
        click_x = int((pos.x() / lbl_w) * 640)
        click_y = int((pos.y() / lbl_h) * 480)

        for cube in self.detected_cubes:
            bx, by, bw, bh = cube["box"]
            if bx <= click_x <= bx + bw and by <= click_y <= by + bh:
                self.executor.pick_and_place_async(cube["rx"], cube["ry"], cube["name"])
                break

    def _pick_first_cube(self):
        if self.executor and not self.executor.is_busy and self.detected_cubes:
            target = self.detected_cubes[0]
            self.executor.pick_and_place_async(target["rx"], target["ry"], target["name"])

    def _toggle_auto_sort(self):
        self.auto_sort_active = self.btn_auto_sort.isChecked()
        if self.auto_sort_active:
            self.btn_auto_sort.setText("⏹️ DỪNG TỰ ĐỘNG PHÂN LOẠI")
        else:
            self.btn_auto_sort.setText("🤖 BẬT TỰ ĐỘNG PHÂN LOẠI (AUTO)")

    def _reset_dobot_alarm(self):
        if self.executor:
            # Gửi lệnh xóa cờ lỗi và hàng đợi
            self.executor.send_cmd({"action": "clear_alarms"})
            QMessageBox.information(self, "Khôi Phục", "Đã gửi lệnh Reset Alarm và khôi phục hàng đợi Dobot!")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and self.tabs.currentIndex() == 3:
            self._pick_first_cube()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #12151c; }
            QWidget { font-family: 'Segoe UI', Arial; color: #e6edf3; }
            QTabWidget::pane { border: 1px solid #30363d; background: #161b22; border-radius: 8px; }
            QTabBar::tab { background: #21262d; color: #8b949e; padding: 10px 18px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 4px; font-weight: bold; }
            QTabBar::tab:selected { background: #161b22; color: #00d6ff; border-bottom: 2px solid #00d6ff; }
            QGroupBox { border: 1px solid #30363d; border-radius: 8px; margin-top: 15px; font-weight: bold; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #00d6ff; }
            QComboBox { background-color: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 5px 10px; color: white; }
            QPushButton { background-color: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 7px; font-weight: bold; }
            QPushButton:hover { background-color: #30363d; }
        """)

    def closeEvent(self, event):
        self.camera_thread.stop()
        self.live_server_mgr.stop()
        event.accept()


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================
def main():
    app = QApplication(sys.argv)
    window = FabLabStudio()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
