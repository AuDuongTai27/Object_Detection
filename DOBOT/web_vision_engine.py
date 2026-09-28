"""
Module Thị Giác AI & Tự Động Phân Loại (Vision & Auto Sort Engine)
cho FabLab AI & Dobot Web Studio:
- Đọc luồng Camera thời gian thực (Ưu tiên Camera ngoài USB, fallback Camera laptop)
- Nhận diện vật thể bằng YOLOv8 / YOLO11
- Tách biệt luồng ảnh RAW (Tab 2) và luồng YOLO Detect (Tab 4) không xung đột
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
    def __init__(self, robot_controller=None, default_cam=None):
        self.robot = robot_controller
        self.cap = None
        self.running = False
        self.worker_thread = None
        self.lock = threading.Lock()

        # Frame buffers & versioning
        self.raw_frame = None
        self.annotated_frame = None
        self.latest_raw_jpeg = None
        self.latest_yolo_jpeg = None
        self.raw_frame_id = 0
        self.yolo_frame_id = 0
        self.frame_id = 0
        self.detected_cubes = []

        # Placeholder frame khi chưa có camera
        self.placeholder_jpeg = self._create_placeholder_jpeg("Đang khởi động Camera...")

        # Worker threads
        self.capture_thread = None
        self.ai_thread = None

        # Danh sách camera đã quét
        self.available_cameras = []
        self.cam_id = 0

        # Vision settings
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

        # Danh sách camera ban đầu
        self.cam_id = 0
        self.available_cameras = [
            {"id": 0, "name": "Camera 0 (Camera tích hợp laptop / PC)", "is_external": False, "is_current": True},
            {"id": 1, "name": "Camera 1 (USB Camera ngoài - Ưu tiên ⭐)", "is_external": True, "is_current": False}
        ]

        # Camera được giữ ở trạng thái tự do (không chiếm dụng phần cứng)
        # để các công cụ chuyên dụng (capture_from_camera, dobot_auto_sort) luôn mở được 100%
        self.cap = None
        self.running = False
        print("[VisionEngine] 📷 Sẵn sàng chế độ Native Tools (Camera tự do)")

    def _create_placeholder_jpeg(self, text="Camera Offline"):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[:] = (24, 27, 34) # Nền tối sang trọng
        cv2.putText(img, text, (140, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
        _, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return buf.tobytes()

    def scan_cameras(self):
        """
        Quét các camera có trên máy tính khi người dùng yêu cầu:
        - Giữ nguyên camera đang chạy
        - Kiểm tra an toàn kèm delay nhỏ để tránh khóa driver DirectShow trên Windows
        """
        cams = []
        tested_indices = [1, 2, 0]

        for idx in tested_indices:
            # Nếu camera này đang chạy bởi chính WebVisionEngine, đánh dấu có sẵn luôn
            if self.running and self.cap and self.cap.isOpened() and self.cam_id == idx:
                is_ext = (idx > 0)
                label = f"Camera {idx} (USB Camera ngoài - Đang kết nối ⭐)" if is_ext else "Camera 0 (Camera tích hợp máy tính - Đang kết nối)"
                cams.append({
                    "id": idx,
                    "name": label,
                    "is_external": is_ext,
                    "is_current": True
                })
                continue

            try:
                backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
                c = cv2.VideoCapture(idx, backend)
                if c.isOpened():
                    ret, _ = c.read()
                    c.release()
                    time.sleep(0.05)  # Tránh kẹt driver DirectShow trên Windows
                    if ret:
                        is_ext = (idx > 0)
                        label = f"Camera {idx} (USB Camera ngoài - Ưu tiên ⭐)" if is_ext else "Camera 0 (Camera tích hợp laptop / PC)"
                        cams.append({
                            "id": idx,
                            "name": label,
                            "is_external": is_ext,
                            "is_current": (self.cam_id == idx)
                        })
            except Exception:
                pass

        if not cams:
            cams = [{"id": 0, "name": "Camera 0 (Mặc định)", "is_external": False, "is_current": True}]

        # Sắp xếp: Camera ngoài lên đầu, sau đó đến camera tích hợp
        cams.sort(key=lambda x: (not x.get("is_external", False), x["id"]))
        with self.lock:
            self.available_cameras = cams

        print(f"[VisionEngine] 📷 Danh sách Camera phát hiện: {[c['name'] for c in cams]}")
        return cams

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
        """Khởi động camera an toàn với fallback DirectShow và tách riêng thread Capture & thread AI."""
        with self.lock:
            # 1. Dừng các thread cũ nếu có
            self.running = False

        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1.0)
        if self.ai_thread and self.ai_thread.is_alive():
            self.ai_thread.join(timeout=1.0)

        with self.lock:
            if self.cap:
                try:
                    self.cap.release()
                    time.sleep(0.1)  # Đảm bảo Windows DirectShow kịp giải phóng
                except Exception:
                    pass
                self.cap = None

            self.cam_id = int(cam_id)
            print(f"[VisionEngine] 🔄 Đang mở Camera ID: {self.cam_id}...")

            # Thử mở bằng DirectShow (Windows) trước, nếu lỗi thử CAP_ANY
            cap = None
            if sys.platform == "win32":
                try:
                    cap = cv2.VideoCapture(self.cam_id, cv2.CAP_DSHOW)
                except Exception:
                    cap = None

            if not cap or not cap.isOpened():
                try:
                    cap = cv2.VideoCapture(self.cam_id, cv2.CAP_ANY)
                except Exception:
                    cap = None

            # Fallback về Camera 0 nếu Camera ID được chọn (ví dụ 1) không khả dụng
            if (not cap or not cap.isOpened()) and self.cam_id != 0:
                print(f"[VisionEngine] ⚠️ Không mở được Camera {self.cam_id}, tự động chuyển sang Camera 0...")
                self.cam_id = 0
                if sys.platform == "win32":
                    try:
                        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                    except Exception:
                        cap = None
                if not cap or not cap.isOpened():
                    try:
                        cap = cv2.VideoCapture(0, cv2.CAP_ANY)
                    except Exception:
                        cap = None

            if not cap or not cap.isOpened():
                print(f"[VisionEngine] ❌ Không thể mở Camera ID: {self.cam_id}!")
                self.placeholder_jpeg = self._create_placeholder_jpeg(f"Camera ID {self.cam_id} không thể mở!")
                return False

            # Cài đặt kích thước và phần cứng tối ưu
            try:
                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                cap.set(cv2.CAP_PROP_FOURCC, fourcc)
            except Exception:
                pass
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Thử đọc frame khởi động (warmup)
            ret = False
            warm_frame = None
            for _ in range(5):
                ret, warm_frame = cap.read()
                if ret and warm_frame is not None:
                    break
                time.sleep(0.05)

            if not ret or warm_frame is None:
                print(f"[VisionEngine] ⚠️ Mở được camera {self.cam_id} nhưng chưa đọc được ảnh.")
            else:
                print(f"[VisionEngine] ✅ Camera {self.cam_id} sẵn sàng! Độ sáng: {warm_frame.mean():.1f}")
                self.raw_frame = warm_frame.copy()
                _, b1 = cv2.imencode('.jpg', warm_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                self.latest_raw_jpeg = b1.tobytes()
                self.latest_yolo_jpeg = self.latest_raw_jpeg
                self.raw_frame_id += 1
                self.yolo_frame_id += 1
                self.frame_id += 1

            self.cap = cap
            self.running = True

            # Khởi động riêng biệt 2 thread: Capture (30 FPS) và AI (asynchronous)
            self.capture_thread = threading.Thread(target=self._capture_worker, daemon=True)
            self.capture_thread.start()
            self.ai_thread = threading.Thread(target=self._ai_worker, daemon=True)
            self.ai_thread.start()

            # Cập nhật cờ is_current trong danh sách
            for c in self.available_cameras:
                c["is_current"] = (c["id"] == self.cam_id)

            return True

    def _capture_worker(self):
        """Vòng lặp đọc frame từ Camera liên tục ở tốc độ cao (30 FPS), không bị block bởi AI."""
        while self.running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret or frame is None:
                time.sleep(0.015)
                continue

            # Nén RAW JPEG siêu tốc
            ret_raw, buf_raw = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ret_raw:
                raw_bytes = buf_raw.tobytes()
                with self.lock:
                    self.raw_frame = frame
                    self.latest_raw_jpeg = raw_bytes
                    self.raw_frame_id += 1
                    self.frame_id = self.raw_frame_id

            time.sleep(0.01)

    def _ai_worker(self):
        """Vòng lặp xử lý YOLO nhận diện vật thể trong nền độc lập, không làm chậm camera gốc."""
        last_processed_raw_id = -1
        while self.running:
            cur_raw_id = self.raw_frame_id
            frame_to_process = None
            if cur_raw_id != last_processed_raw_id:
                with self.lock:
                    if self.raw_frame is not None:
                        frame_to_process = self.raw_frame.copy()
                last_processed_raw_id = cur_raw_id

            if frame_to_process is not None and self.yolo_model is not None:
                try:
                    ann_frame, cubes = self._process_yolo(frame_to_process)
                    ret_yolo, buf_yolo = cv2.imencode('.jpg', ann_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    if ret_yolo:
                        with self.lock:
                            self.latest_yolo_jpeg = buf_yolo.tobytes()
                            self.yolo_frame_id += 1
                            self.detected_cubes = cubes
                except Exception:
                    time.sleep(0.03)
            elif frame_to_process is not None:
                with self.lock:
                    self.latest_yolo_jpeg = self.latest_raw_jpeg
                    self.yolo_frame_id = self.raw_frame_id

            time.sleep(0.02)

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

                    # Vẽ Bounding Box & tâm
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
        except Exception:
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

    def get_jpeg_with_id(self, mode="raw"):
        """Trả về (frame_id, jpeg_bytes) theo chế độ yêu cầu (raw hoặc yolo)."""
        with self.lock:
            if mode == "yolo":
                jpeg = self.latest_yolo_jpeg or self.latest_raw_jpeg or self.placeholder_jpeg
                return self.yolo_frame_id, jpeg
            else:
                jpeg = self.latest_raw_jpeg or self.placeholder_jpeg
                return self.raw_frame_id, jpeg

    def get_jpeg(self, mode="raw"):
        _, jpeg = self.get_jpeg_with_id(mode)
        return jpeg

    def get_raw_frame(self):
        with self.lock:
            return self.raw_frame.copy() if self.raw_frame is not None else None

    def get_camera_devices(self):
        """Trả về danh sách camera khả dụng mà không làm gián đoạn luồng đang chạy."""
        with self.lock:
            return list(self.available_cameras)

    def get_status(self):
        with self.lock:
            return {
                "camera_online": self.running and self.cap is not None and self.cap.isOpened(),
                "camera_id": self.cam_id,
                "available_cameras": list(self.available_cameras),
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
                target_cube = None
                with self.lock:
                    for c in self.detected_cubes:
                        coord = c.get("dobot_coord", {})
                        if coord.get("x") is not None and coord.get("y") is not None:
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
