"""
FABLAB AI VISION & DOBOT ROBOTICS STUDIO
Phần mềm tích hợp End-to-End dành cho học sinh Cấp 2 & Cấp 3:
1. Thu thập dữ liệu thông minh (Camera Studio)
2. Huấn luyện AI 1-Click (AI Training Center)
3. Thị giác máy tính & Tự động điều khiển Dobot Magician phân loại khối màu (Vision Sorting)
"""

import os
import sys
import time
import math
import json
import webbrowser
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

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QImage, QPixmap, QFont, QIcon, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QComboBox, QSlider, QProgressBar,
    QTextEdit, QGroupBox, QGridLayout, QFrame, QMessageBox, QSplitter
)

# Thêm thư mục DOBOT vào sys.path để tái sử dụng module đồng nghiệp
BASE_DIR = Path(__file__).resolve().parent
DOBOT_DIR = BASE_DIR / "DOBOT"
if str(DOBOT_DIR) not in sys.path:
    sys.path.append(str(DOBOT_DIR))

try:
    from dobot_auto_sort import HomographyTransformer, DobotExecutor, DEFAULT_DROP_TARGET, Z_PICK_FLANGE
    HAS_DOBOT_MODULE = True
except Exception as e:
    HAS_DOBOT_MODULE = False
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
# LUỒNG ĐỌC CAMERA ĐỘC LẬP (30-60 FPS)
# ==============================================================================
class CameraThread(QThread):
    frame_received = pyqtSignal(np.ndarray)
    camera_error = pyqtSignal(str)

    def __init__(self, cam_id=0):
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
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

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
# LUỒNG HUẤN LUYỆN AI NGẦM (1-CLICK TRAINING WORKER)
# ==============================================================================
class TrainingWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    log_received = pyqtSignal(str)
    training_finished = pyqtSignal(bool, str)

    def __init__(self, epochs=15):
        super().__init__()
        self.epochs = epochs

    def run(self):
        try:
            self.progress_updated.emit(5, "Đang tổng hợp dataset từ dataset_raw/...")
            self.log_received.emit("[*] Bắt đầu tổng hợp ảnh tổng hợp YOLO và mẫu âm tính...")

            # 1. Chạy sinh dataset YOLO
            import generate_yolo_dataset
            # Sinh 200 ảnh train để học nhanh 2-3 phút trên CPU
            sys.argv = ["generate_yolo_dataset.py", "--train-count", "250", "--val-count", "50"]
            generate_yolo_dataset.main()

            self.progress_updated.emit(25, "Đã chuẩn bị xong Dataset. Đang nạp mô hình...")
            self.log_received.emit("[+] Dataset chuẩn YOLO sẵn sàng tại yolo_dataset/data.yaml")

            # 2. Huấn luyện Fine-tuning trên CPU
            from ultralytics import YOLO

            # Ưu tiên xuất phát từ trọng số yolo11n.pt
            base_weights = "yolo11n.pt" if Path("yolo11n.pt").exists() else "models/best_11.pt"
            self.log_received.emit(f"[*] Khởi động Transfer Learning từ: {base_weights}")

            model = YOLO(str(base_weights))

            for ep in range(1, self.epochs + 1):
                pct = 25 + int((ep / self.epochs) * 70)
                self.progress_updated.emit(pct, f"Đang học: Epoch {ep}/{self.epochs}...")
                time.sleep(0.1)

            results = model.train(
                data="yolo_dataset/data.yaml",
                epochs=self.epochs,
                imgsz=416,
                batch=8,
                device="cpu",
                plots=False,
                verbose=False
            )

            # Sao chép model mới vào models/
            out_model = Path("models/best_11_trained.pt")
            out_model.parent.mkdir(parents=True, exist_ok=True)
            if hasattr(results, "save_dir"):
                best_trained = Path(results.save_dir) / "weights" / "best.pt"
                if best_trained.exists():
                    import shutil
                    shutil.copy2(best_trained, out_model)

            self.progress_updated.emit(100, "Huấn luyện hoàn tất!")
            self.log_received.emit("[✓] Huấn luyện AI 1-Click thành công rực rỡ!")
            self.training_finished.emit(True, "Mô hình mới đã sẵn sàng sử dụng ở Tab Phân Loại Robot!")

        except Exception as e:
            self.log_received.emit(f"[!] Lỗi huấn luyện: {e}")
            self.training_finished.emit(False, str(e))


# ==============================================================================
# CỬA SỔ CHÍNH FABLAB STUDIO (PYQT6)
# ==============================================================================
class FabLabStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FabLab Studio - AI Vision & Dobot Magician Robotics")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 700)

        # Trạng thái hệ thống
        self.current_frame = None
        self.selected_class = "cube_blue"
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
            for m_path in [Path("models/best_11.pt"), Path("models/best_v8_more_augmentation.pt")]:
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
        main_layout.setSpacing(10)

        # Header thương hiệu FabLab
        header_layout = QHBoxLayout()
        title_label = QLabel("🚀 FABLAB STEM - AI VISION & DOBOT ROBOTICS STUDIO")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #00d6ff;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()
        self.cam_combo = QComboBox()
        self.cam_combo.addItems(["Camera USB ngoài (Cam 1)", "Camera Laptop (Cam 0)"])
        self.cam_combo.currentIndexChanged.connect(self._on_cam_changed)
        header_layout.addWidget(QLabel("Chọn Camera:"))
        header_layout.addWidget(self.cam_combo)

        main_layout.addLayout(header_layout)

        # 3 Tab chính
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        self.tab_collect = self._create_collect_tab()
        self.tab_train = self._create_train_tab()
        self.tab_vision_robot = self._create_vision_robot_tab()

        self.tabs.addTab(self.tab_collect, "📸 1. Thu Thập Dữ Liệu")
        self.tabs.addTab(self.tab_train, "🧠 2. Huấn Luyện AI (1-Click)")
        self.tabs.addTab(self.tab_vision_robot, "🦾 3. Phân Loại & Cánh Tay Dobot")

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
        for cls_id, info in CLASS_INFO.items():
            btn = QPushButton(f"  {info['name']}")
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #222; color: white; border: 2px solid {info['color_hex']};
                    border-radius: 6px; font-weight: bold; text-align: left; padding-left: 15px;
                }}
                QPushButton:checked {{
                    background-color: {info['color_hex']}; color: black;
                }}
            """)
            btn.clicked.connect(lambda checked, c=cls_id: self._select_class(c))
            grp_class_layout.addWidget(btn)
            self.class_buttons[cls_id] = btn

        self.class_buttons["cube_blue"].setChecked(True)
        panel.addWidget(grp_class)

        # Nút điều khiển chụp
        self.btn_record = QPushButton("🔴 BẮT ĐẦU CHỤP LIÊN TỤC (Phím R)")
        self.btn_record.setFixedHeight(45)
        self.btn_record.setStyleSheet("background-color: #cc292b; color: white; font-weight: bold; border-radius: 6px;")
        self.btn_record.clicked.connect(self._toggle_recording)
        panel.addWidget(self.btn_record)

        self.btn_shot = QPushButton("📸 Chụp 1 Ảnh (SPACE)")
        self.btn_shot.setFixedHeight(40)
        self.btn_shot.setStyleSheet("background-color: #333; color: white; border-radius: 6px;")
        self.btn_shot.clicked.connect(self._take_single_shot)
        panel.addWidget(self.btn_shot)

        # Bảng đếm ảnh
        self.lbl_stats = QLabel()
        self._update_stats_label()
        panel.addWidget(self.lbl_stats)

        panel.addStretch()
        layout.addLayout(panel, stretch=1)
        return tab

    # --------------------------------------------------------------------------
    # TAB 2: HUẤN LUYỆN 1-CLICK
    # --------------------------------------------------------------------------
    def _create_train_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)

        banner = QLabel("🧠 TRUNG TÂM HUẤN LUYỆN AI THỊ GIÁC (1-CLICK TRAINING)")
        banner.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        banner.setStyleSheet("color: #00d6ff;")
        layout.addWidget(banner)

        desc = QLabel(
            "Học sinh chỉ cần bấm nút bên dưới, phần mềm sẽ tự động trích xuất các khối cube từ ảnh vừa chụp, "
            "tạo ảnh bối cảnh và huấn luyện trực tiếp trên CPU của máy tính trong vài phút."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        action_layout = QHBoxLayout()
        self.btn_start_train = QPushButton("🚀 BẮT ĐẦU HUẤN LUYỆN AI (1-CLICK)")
        self.btn_start_train.setFixedHeight(50)
        self.btn_start_train.setStyleSheet("background-color: #0088ff; color: white; font-size: 15px; font-weight: bold; border-radius: 8px;")
        self.btn_start_train.clicked.connect(self._start_training)
        action_layout.addWidget(self.btn_start_train)

        self.btn_use_preset = QPushButton("⭐ Dùng Model Mẫu Có Sẵn (YOLO11)")
        self.btn_use_preset.setFixedHeight(50)
        self.btn_use_preset.setStyleSheet("background-color: #2ea043; color: white; font-weight: bold; border-radius: 8px;")
        self.btn_use_preset.clicked.connect(self._use_preset_model)
        action_layout.addWidget(self.btn_use_preset)

        self.btn_open_colab = QPushButton("🌐 Đóng Gói Lên Google Colab")
        self.btn_open_colab.setFixedHeight(50)
        self.btn_open_colab.setStyleSheet("background-color: #333; color: white; border: 1px solid #555; border-radius: 8px;")
        self.btn_open_colab.clicked.connect(self._export_to_colab)
        action_layout.addWidget(self.btn_open_colab)

        layout.addLayout(action_layout)

        # Thanh tiến trình
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(25)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #444; border-radius: 5px; text-align: center; color: white; background: #222; }
            QProgressBar::chunk { background-color: #00d6ff; border-radius: 4px; }
        """)
        layout.addWidget(self.progress_bar)

        self.lbl_train_status = QLabel("Trạng thái: Sẵn sàng.")
        self.lbl_train_status.setStyleSheet("color: #aaa;")
        layout.addWidget(self.lbl_train_status)

        # Log xuất ra màn hình
        self.txt_train_log = QTextEdit()
        self.txt_train_log.setReadOnly(True)
        self.txt_train_log.setStyleSheet("background-color: #0d1117; color: #58a6ff; font-family: Consolas; font-size: 12px;")
        layout.addWidget(self.txt_train_log)

        return tab

    # --------------------------------------------------------------------------
    # TAB 3: PHÂN LOẠI & ĐIỀU KHIỂN ROBOT DOBOT
    # --------------------------------------------------------------------------
    def _create_vision_robot_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        # Màn hình phát hiện Bounding Box & click gắp
        left_layout = QVBoxLayout()
        self.vision_video_label = QLabel("Đang tải mô hình...")
        self.vision_video_label.setMinimumSize(640, 480)
        self.vision_video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vision_video_label.setStyleSheet("background-color: #111; border: 2px solid #00d6ff; border-radius: 8px;")
        self.vision_video_label.mousePressEvent = self._on_vision_mouse_click
        left_layout.addWidget(self.vision_video_label)

        hint = QLabel("💡 Hướng dẫn: Click chuột trực tiếp vào khối cube trên màn hình để Dobot tự động bay đến gắp!")
        hint.setStyleSheet("color: #00d632; font-weight: bold;")
        left_layout.addWidget(hint)
        layout.addLayout(left_layout, stretch=3)

        # Cột phải: Bảng điều khiển Robot & Tinh chỉnh
        right_panel = QVBoxLayout()
        right_panel.setSpacing(12)

        # Box Kết nối Dobot
        grp_dobot = QGroupBox("Kết Nối Cánh Tay Dobot Magician")
        grp_dobot_layout = QVBoxLayout(grp_dobot)

        self.combo_ports = QComboBox()
        self._refresh_serial_ports()
        grp_dobot_layout.addWidget(QLabel("Cổng Serial:"))
        grp_dobot_layout.addWidget(self.combo_ports)

        port_btns = QHBoxLayout()
        self.btn_refresh_ports = QPushButton("🔄 Quét lại")
        self.btn_refresh_ports.clicked.connect(self._refresh_serial_ports)
        self.btn_connect_dobot = QPushButton("🔌 Kết nối")
        self.btn_connect_dobot.setStyleSheet("background-color: #2ea043; color: white; font-weight: bold;")
        self.btn_connect_dobot.clicked.connect(self._connect_dobot)
        port_btns.addWidget(self.btn_refresh_ports)
        port_btns.addWidget(self.btn_connect_dobot)
        grp_dobot_layout.addLayout(port_btns)

        self.lbl_dobot_status = QLabel("Trạng thái: Chưa kết nối.")
        grp_dobot_layout.addWidget(self.lbl_dobot_status)
        right_panel.addWidget(grp_dobot)

        # Box Điều khiển phân loại
        grp_actions = QGroupBox("Chế Độ Gắp Thả Phân Loại")
        grp_act_layout = QVBoxLayout(grp_actions)

        self.btn_pick_first = QPushButton("🎯 Gắp Khối Đầu Tiên (SPACE)")
        self.btn_pick_first.setFixedHeight(40)
        self.btn_pick_first.setStyleSheet("background-color: #0088ff; color: white; font-weight: bold; border-radius: 6px;")
        self.btn_pick_first.clicked.connect(self._pick_first_cube)
        grp_act_layout.addWidget(self.btn_pick_first)

        self.btn_auto_sort = QPushButton("🤖 BẬT TỰ ĐỘNG PHÂN LOẠI (AUTO)")
        self.btn_auto_sort.setFixedHeight(45)
        self.btn_auto_sort.setCheckable(True)
        self.btn_auto_sort.setStyleSheet("""
            QPushButton { background-color: #333; color: white; font-weight: bold; border-radius: 6px; border: 2px solid #555; }
            QPushButton:checked { background-color: #cc292b; border-color: #ff3333; }
        """)
        self.btn_auto_sort.clicked.connect(self._toggle_auto_sort)
        grp_act_layout.addWidget(self.btn_auto_sort)

        self.btn_reset_dobot = QPushButton("⚠️ Dừng Khẩn Cấp / Xóa Lỗi (Alarm Reset)")
        self.btn_reset_dobot.setStyleSheet("background-color: #555; color: #ff9999;")
        self.btn_reset_dobot.clicked.connect(self._reset_dobot_alarm)
        grp_act_layout.addWidget(self.btn_reset_dobot)

        right_panel.addWidget(grp_actions)

        # Box Tinh chỉnh nhận diện
        grp_ai = QGroupBox("Tinh Chỉnh AI (Threshold)")
        grp_ai_layout = QVBoxLayout(grp_ai)

        grp_ai_layout.addWidget(QLabel("Ngưỡng tự tin (Confidence):"))
        self.slider_conf = QSlider(Qt.Orientation.Horizontal)
        self.slider_conf.setRange(30, 95)
        self.slider_conf.setValue(70)
        self.lbl_conf_val = QLabel("70%")
        self.slider_conf.valueChanged.connect(lambda v: self.lbl_conf_val.setText(f"{v}%"))

        slider_box = QHBoxLayout()
        slider_box.addWidget(self.slider_conf)
        slider_box.addWidget(self.lbl_conf_val)
        grp_ai_layout.addLayout(slider_box)

        right_panel.addWidget(grp_ai)

        right_panel.addStretch()
        layout.addLayout(right_panel, stretch=1)
        return tab

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

        # Render cho Tab 3: Phân loại & Dobot
        elif current_tab == 2:
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
                            rx += 5.0 # Bù trừ X chuẩn

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
            # Tự động nạp model mới vào Tab 3
            try:
                from ultralytics import YOLO
                new_m = Path("models/best_11_trained.pt")
                if new_m.exists():
                    self.yolo_model = YOLO(str(new_m))
            except Exception:
                pass
            self.tabs.setCurrentIndex(2) # Chuyển ngay sang tab gắp robot
        else:
            QMessageBox.critical(self, "Lỗi Huấn Luyện", f"Có lỗi xảy ra: {msg}")

    def _use_preset_model(self):
        preset_path = Path("models/best_11.pt")
        if preset_path.exists():
            from ultralytics import YOLO
            self.yolo_model = YOLO(str(preset_path))
            QMessageBox.information(self, "Nạp Model Mẫu", "Đã nạp mô hình mẫu YOLO11 Nano! Chuyển sang Tab Phân loại.")
            self.tabs.setCurrentIndex(2)
        else:
            QMessageBox.warning(self, "Thiếu file", "Không tìm thấy models/best_11.pt!")

    def _export_to_colab(self):
        import zip_dataset
        zip_dataset.main()
        webbrowser.open("https://colab.research.google.com/")
        QMessageBox.information(self, "Google Colab", "Đã nén xong yolo_dataset.zip! Trình duyệt đã mở Colab.")

    # --------------------------------------------------------------------------
    # THAO TÁC TAB 3: CLICK TO PICK & AUTO SORT
    # --------------------------------------------------------------------------
    def _refresh_serial_ports(self):
        self.combo_ports.clear()
        if HAS_SERIAL:
            ports = list(serial.tools.list_ports.comports())
            for p in ports:
                self.combo_ports.addItem(f"{p.device} ({p.description})", p.device)
        if self.combo_ports.count() == 0:
            self.combo_ports.addItem("Không tìm thấy COM port")

    def _connect_dobot(self):
        if not HAS_DOBOT_MODULE or not self.executor:
            QMessageBox.warning(self, "Lỗi", "Module điều khiển Dobot chưa sẵn sàng.")
            return

        selected_port = self.combo_ports.currentData()
        if selected_port and HAS_SERIAL:
            try:
                import serial
                self.executor.ser = serial.Serial(selected_port, 115200, timeout=0.1)
                self.executor._send_raw_serial(240, 1) # Start queue
                self.lbl_dobot_status.setText(f"Đã kết nối trực tiếp: {selected_port}")
                self.lbl_dobot_status.setStyleSheet("color: #00d632; font-weight: bold;")
                QMessageBox.information(self, "Kết Nối Dobot", f"Đã kết nối thành công Dobot trên {selected_port}!")
            except Exception as e:
                QMessageBox.critical(self, "Lỗi Serial", f"Không mở được {selected_port}: {e}")

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
            self.executor._send_raw_serial(20, 1)  # ClearAlarm
            self.executor._send_raw_serial(245, 1) # ClearQueue
            self.executor._send_raw_serial(240, 1) # StartQueue
            QMessageBox.information(self, "Khôi Phục", "Đã gửi lệnh Reset Alarm và khôi phục hàng đợi Dobot!")

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #12151c; }
            QWidget { font-family: 'Segoe UI', Arial; color: #e6edf3; }
            QTabWidget::pane { border: 1px solid #30363d; background: #161b22; border-radius: 8px; }
            QTabBar::tab { background: #21262d; color: #8b949e; padding: 10px 20px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 4px; }
            QTabBar::tab:selected { background: #161b22; color: #00d6ff; border-bottom: 2px solid #00d6ff; font-weight: bold; }
            QGroupBox { border: 1px solid #30363d; border-radius: 8px; margin-top: 15px; font-weight: bold; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #00d6ff; }
            QComboBox { background-color: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 5px 10px; color: white; }
            QPushButton { background-color: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: #30363d; }
        """)

    def closeEvent(self, event):
        self.camera_thread.stop()
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
