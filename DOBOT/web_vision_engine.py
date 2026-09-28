"""
Module Thị Giác AI & Tự Động Phân Loại (Vision & Auto Sort Engine)
cho FabLab AI & Dobot Web Studio:
- Đọc luồng Camera liên tục (OpenCV CAP_DSHOW, MJPG)
- Nhận diện vật thể bằng YOLOv8 / YOLO11
- Ánh xạ tọa độ ảnh (u, v) sang tọa độ Dobot (X, Y) bằng Homography
- Hỗ trợ Click-to-Pick (Nhấp chuột trên video để gắp)
- Hỗ trợ Chế độ Tự Động Phân Loại (Auto Sort)
"""

import os
import sys
import time
import json
import threading
from pathlib import Path
import cv2
import numpy as np

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
HOMOGRAPHY_JSON_PATH = BASE_DIR / "homography_dobot.json"
MODELS_DIR = PROJECT_ROOT / "models"

# Độ cao chuẩn Dobot (mm)
Z_PICK_FLANGE = -51.7
Z_SAFE_FLANGE = 35.0

# Tọa độ khay thả mặc định
DEFAULT_DROP_TARGET = {
    "x": 49.2,
    "y": -230.1,
    "z": -44.0,
    "name": "Khay Thả (49.2, -230.1)"
}

DROP_TARGETS_BY_COLOR = {
    "cube_red":    {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Đỏ (49.2, -230.1)"},
    "cube_green":  {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Xanh Lục (49.2, -230.1)"},
    "cube_blue":   {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Xanh Dương (49.2, -230.1)"},
    "cube_yellow": {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Vàng (49.2, -230.1)"},
}

COLOR_MAP = {
    "cube_red":    (0, 0, 255),
    "cube_green":  (0, 255, 0),
    "cube_blue":   (255, 120, 0),
    "cube_yellow": (0, 230, 255),
    "background":  (128, 128, 128)
}


class WebVisionEngine:
    def __init__(self, robot_controller=None, default_cam=0):
        self.robot = robot_controller
        self.cam_id = default_cam
        self.cap = None
        self.running = False
        self.lock = threading.Lock()

        # Frame data
        self.raw_frame = None
        self.annotated_frame = None
        self.latest_jpeg = None
        self.detected_cubes = []

        # Vision mode: 'raw' (cho thu thập ảnh) hoặc 'yolo' (cho phân loại)
        self.stream_mode = "raw" 
        self.conf_threshold = 0.45

        # Homography
        self.homography_matrix = None
        self.load_homography()

        # YOLO Model
        self.yolo_model = None
        self.active_model_name = ""
        self.load_best_yolo_model()

        # Auto sort state
        self.auto_sort_active = False
        self.is_picking = False
        self.auto_sort_thread = None

        # Start camera thread
        self.start_camera(self.cam_id)

    def load_homography(self):
        if HOMOGRAPHY_JSON_PATH.exists():
            try:
                with open(HOMOGRAPHY_JSON_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.homography_matrix = np.array(data["homography_matrix"], dtype=np.float64)
                    print(f"[VisionEngine] Đã nạp ma trận Homography từ {HOMOGRAPHY_JSON_PATH}")
            except Exception as e:
                print(f"[VisionEngine] Lỗi nạp Homography: {e}")

    def load_best_yolo_model(self, custom_path=None):
        try:
            from ultralytics import YOLO
            candidates = [
                custom_path,
                MODELS_DIR / "best_trained.pt",
                MODELS_DIR / "best_11.pt",
                MODELS_DIR / "best_v8_more_augmentation.pt",
                MODELS_DIR / "best_v11.pt",
            ]
            for c in candidates:
                if c and Path(c).exists():
                    self.yolo_model = YOLO(str(c))
                    self.active_model_name = Path(c).name
                    print(f"[VisionEngine] Đã nạp mô hình YOLO: {c}")
                    return True
            print("[VisionEngine] Chưa tìm thấy mô hình YOLO trong models/")
            return False
        except Exception as e:
            print(f"[VisionEngine] Lỗi khởi tạo mô hình YOLO: {e}")
            return False

    def start_camera(self, cam_id=0):
        with self.lock:
            self.running = False
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    pass

            self.cam_id = int(cam_id)
            backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
            self.cap = cv2.VideoCapture(self.cam_id, backend)
            if self.cap.isOpened():
                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                self.cap.set(cv2.CAP_PROP_FOURCC, fourcc)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self.running = True
                threading.Thread(target=self._camera_worker, daemon=True).start()
                print(f"[VisionEngine] Đã mở Camera ID: {self.cam_id}")
                return True
            else:
                print(f"[VisionEngine] Không mở được Camera ID: {self.cam_id}")
                return False

    def _camera_worker(self):
        while self.running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret or frame is None:
                time.sleep(0.03)
                continue

            with self.lock:
                self.raw_frame = frame.copy()

            # Nếu ở chế độ phân loại hoặc auto sort: chạy YOLO inference
            if self.stream_mode == "yolo" and self.yolo_model is not None:
                ann_frame, cubes = self._process_yolo(frame)
                with self.lock:
                    self.annotated_frame = ann_frame
                    self.detected_cubes = cubes
                    display_frame = ann_frame
            else:
                with self.lock:
                    self.detected_cubes = []
                    display_frame = frame

            # Nén sang JPEG để stream
            ret_encode, buf = cv2.imencode('.jpg', display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ret_encode:
                with self.lock:
                    self.latest_jpeg = buf.tobytes()

            time.sleep(0.02) # ~40-50 FPS

    def _process_yolo(self, frame):
        h, w = frame.shape[:2]
        display = frame.copy()
        cubes = []

        try:
            results = self.yolo_model(frame, conf=self.conf_threshold, verbose=False)
            for res in results:
                for box in res.boxes:
                    cls_id = int(box.cls[0].item())
                    cls_name = res.names.get(cls_id, f"obj_{cls_id}")
                    conf = float(box.conf[0].item())

                    xyxy = box.xyxy[0].cpu().numpy().astype(int)
                    x1, y1, x2, y2 = xyxy
                    u_center = float((x1 + x2) / 2.0)
                    v_center = float((y1 + y2) / 2.0)

                    # Tính tọa độ thực Dobot từ Homography
                    dobot_x, dobot_y = self.pixel_to_dobot(u_center, v_center)

                    color = COLOR_MAP.get(cls_name, (0, 255, 255))

                    # Vẽ Bounding Box
                    cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
                    cv2.circle(display, (int(u_center), int(v_center)), 4, (0, 0, 255), -1)

                    # Nhãn & Tọa độ
                    label_text = f"{cls_name} {conf:.2f}"
                    coord_text = f"X:{dobot_x:.1f} Y:{dobot_y:.1f}" if dobot_x is not None else ""

                    cv2.putText(display, label_text, (x1, max(18, y1 - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
                    if coord_text:
                        cv2.putText(display, coord_text, (x1, y2 + 18),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

                    cubes.append({
                        "id": len(cubes) + 1,
                        "class_name": cls_name,
                        "confidence": round(conf, 2),
                        "pixel": {"u": round(u_center, 1), "v": round(v_center, 1)},
                        "dobot_coord": {"x": round(dobot_x, 1) if dobot_x else None, "y": round(dobot_y, 1) if dobot_y else None},
                        "dobot_x": round(dobot_x, 1) if dobot_x else None,
                        "dobot_y": round(dobot_y, 1) if dobot_y else None,
                        "bbox": [int(x1), int(y1), int(x2), int(y2)]
                    })
        except Exception as e:
            pass

        return display, cubes

    def pixel_to_dobot(self, u: float, v: float):
        if self.homography_matrix is None:
            return None, None
        pixel_pt = np.array([u, v, 1.0], dtype=np.float64)
        dobot_pt = np.dot(self.homography_matrix, pixel_pt)
        if abs(dobot_pt[2]) < 1e-6:
            return None, None
        x = float(dobot_pt[0] / dobot_pt[2])
        y = float(dobot_pt[1] / dobot_pt[2])
        return x, y

    def get_jpeg(self):
        with self.lock:
            return self.latest_jpeg

    def get_raw_frame(self):
        with self.lock:
            return self.raw_frame.copy() if self.raw_frame is not None else None

    def get_status(self):
        with self.lock:
            return {
                "camera_online": self.running and self.cap is not None and self.cap.isOpened(),
                "camera_id": self.cam_id,
                "stream_mode": self.stream_mode,
                "active_model": self.active_model_name,
                "homography_loaded": self.homography_matrix is not None,
                "auto_sort_active": self.auto_sort_active,
                "auto_sort_enabled": self.auto_sort_active,
                "is_picking": self.is_picking,
                "detected_count": len(self.detected_cubes),
                "detected_cubes": list(self.detected_cubes),
                "cubes": list(self.detected_cubes)
            }

    def execute_pick_and_place(self, pick_x: float, pick_y: float, cube_name="cube", on_complete=None):
        if not self.robot or not self.robot.connected:
            return {"success": False, "error": "Robot Dobot chưa kết nối!"}

        if self.is_picking:
            return {"success": False, "error": "Robot đang bận thực hiện chu trình gắp trước!"}

        def _worker():
            self.is_picking = True
            try:
                # Điểm thả
                target_tray = DROP_TARGETS_BY_COLOR.get(cube_name, DEFAULT_DROP_TARGET)
                drop_x = target_tray["x"]
                drop_y = target_tray["y"]
                drop_z = target_tray["z"]

                print(f"[VisionEngine] 🚀 Bắt đầu gắp {cube_name} tại ({pick_x:.1f}, {pick_y:.1f}) -> Thả ({drop_x}, {drop_y})")

                # 1. Bay an toàn tới điểm trên phôi
                self.robot.move_safe_jump(pick_x, pick_y, Z_PICK_FLANGE, r=0.0, safe_z=Z_SAFE_FLANGE)
                time.sleep(1.2)

                # 2. Bật giác hút
                self.robot.set_suction(True)
                time.sleep(0.4)

                # 3. Nhấc lên độ cao an toàn
                self.robot.move_to_xyz(pick_x, pick_y, Z_SAFE_FLANGE, r=0.0)
                time.sleep(0.6)

                # 4. Bay sang điểm thả
                self.robot.move_safe_jump(drop_x, drop_y, drop_z, r=0.0, safe_z=Z_SAFE_FLANGE)
                time.sleep(1.2)

                # 5. Tắt giác hút
                self.robot.set_suction(False)
                time.sleep(0.3)

                # 6. Nhấc lên an toàn hoàn tất chu trình
                self.robot.move_to_xyz(drop_x, drop_y, Z_SAFE_FLANGE, r=0.0)
                time.sleep(0.6)

                print(f"[VisionEngine] ✅ Hoàn tất gắp thả {cube_name}!")
            except Exception as e:
                print(f"[VisionEngine] ❌ Lỗi chu trình gắp: {e}")
            finally:
                self.is_picking = False
                if on_complete:
                    on_complete()

        threading.Thread(target=_worker, daemon=True).start()
        return {"success": True, "message": f"Đã gửi lệnh gắp {cube_name}"}

    def toggle_auto_sort(self, enable=None):
        if enable is None:
            self.auto_sort_active = not self.auto_sort_active
        else:
            self.auto_sort_active = bool(enable)

        if self.auto_sort_active:
            if not self.auto_sort_thread or not self.auto_sort_thread.is_alive():
                self.auto_sort_thread = threading.Thread(target=self._auto_sort_worker, daemon=True)
                self.auto_sort_thread.start()
        return {"success": True, "auto_sort": self.auto_sort_active}

    def _auto_sort_worker(self):
        print("[VisionEngine] BẮT ĐẦU CHẾ ĐỘ TỰ ĐỘNG PHÂN LOẠI (AUTO SORT)...")
        while self.auto_sort_active:
            if not self.is_picking and self.robot and self.robot.connected:
                # Tìm một khối màu hợp lệ đang nằm trên mặt phẳng
                target_cube = None
                with self.lock:
                    for c in self.detected_cubes:
                        coord = c.get("dobot_coord", {})
                        if coord.get("x") is not None and coord.get("y") is not None:
                            # Kiểm tra bán kính làm việc an toàn
                            r = (coord["x"]**2 + coord["y"]**2)**0.5
                            if 150 <= r <= 320:
                                target_cube = c
                                break

                if target_cube:
                    cx = target_cube["dobot_coord"]["x"]
                    cy = target_cube["dobot_coord"]["y"]
                    cname = target_cube["class_name"]
                    self.execute_pick_and_place(cx, cy, cname)

            time.sleep(1.0)
        print("[VisionEngine] Đã dừng chế độ tự động phân loại.")
