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
# Đã hạ tiếp 0.5 cm (5.0 mm): Mức tiếp xúc Z_TCP = -109.2 mm -> Hạ xuống Z_TCP = -114.2 mm (Z_Flange = -54.7 mm)
Z_PICK_FLANGE = -54.7
Z_SAFE_FLANGE = 35.0

DROP_TARGETS_JSON_PATH = BASE_DIR / "drop_targets.json"

# Tọa độ khay thả mặc định
DEFAULT_DROP_TARGET = {
    "x": 49.2,
    "y": -230.1,
    "z": -44.0,
    "l": 0.0,
    "rail_l": 0.0,
    "name": "Khay Thả (49.2, -230.1)"
}

DROP_TARGETS_BY_COLOR = {
    "cube_red":    {"x": 49.2, "y": -230.1, "z": -44.0, "l": 0.0, "rail_l": 0.0, "name": "Khay Đỏ (49.2, -230.1)"},
    "cube_green":  {"x": 49.2, "y": -230.1, "z": -44.0, "l": 0.0, "rail_l": 0.0, "name": "Khay Xanh Lục (49.2, -230.1)"},
    "cube_blue":   {"x": 49.2, "y": -230.1, "z": -44.0, "l": 0.0, "rail_l": 0.0, "name": "Khay Xanh Dương (49.2, -230.1)"},
    "cube_yellow": {"x": 49.2, "y": -230.1, "z": -44.0, "l": 0.0, "rail_l": 0.0, "name": "Khay Vàng (49.2, -230.1)"},
}

DROP_TARGETS_MODE = "all"
CALIB_RAIL_L = 0.0

def load_drop_targets():
    """Tự động nạp tọa độ khay thả & Z gắp từ file drop_targets.json."""
    global DEFAULT_DROP_TARGET, DROP_TARGETS_BY_COLOR, DROP_TARGETS_MODE, Z_PICK_FLANGE, CALIB_RAIL_L
    if DROP_TARGETS_JSON_PATH.exists():
        try:
            with open(DROP_TARGETS_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "pick_z" in data:
                Z_PICK_FLANGE = float(data["pick_z"])
            if "mode" in data:
                DROP_TARGETS_MODE = data["mode"]
            if "calib_rail_l" in data:
                CALIB_RAIL_L = float(data["calib_rail_l"])
            if "default" in data:
                DEFAULT_DROP_TARGET.update(data["default"])
            if "by_color" in data:
                DROP_TARGETS_BY_COLOR.update(data["by_color"])
            print(f"[VisionEngine] Đã nạp cấu hình vị trí thả đồ (Chế độ: {DROP_TARGETS_MODE}, Z_Pick={Z_PICK_FLANGE}mm, Calib_L={CALIB_RAIL_L}mm) từ: {DROP_TARGETS_JSON_PATH}")
        except Exception as e:
            print(f"[VisionEngine] Lỗi nạp drop_targets.json: {e}")

load_drop_targets()

COLOR_MAP = {
    "cube_red":    (0, 0, 255),
    "cube_green":  (0, 255, 0),
    "cube_blue":   (255, 120, 0),
    "cube_yellow": (0, 230, 255),
    "background":  (128, 128, 128)
}


try:
    from dobot_auto_sort import solve_rail_kinematics
except ImportError:
    try:
        from .dobot_auto_sort import solve_rail_kinematics
    except Exception:
        solve_rail_kinematics = None


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

        # Danh sách camera ban đầu (quét an toàn)
        self.cam_id = 0
        self.available_cameras = []
        try:
            self.scan_cameras()
        except Exception:
            pass
        if self.available_cameras:
            self.cam_id = self.available_cameras[0]["id"]

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
                    self.calib_rail_l = float(data.get("rail_l", data.get("calib_rail_l", CALIB_RAIL_L)))
                    print(f"[VisionEngine] Đã nạp ma trận Homography từ {HOMOGRAPHY_JSON_PATH} (calib_rail_l={self.calib_rail_l:.1f}mm)")
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

                    sol_rail = None
                    is_rail = bool(getattr(self.robot, "is_rail_mode", False))
                    if dobot_x is not None and dobot_y is not None:
                        r_dist = (dobot_x**2 + dobot_y**2)**0.5
                        if (r_dist < 140.0 or r_dist > 330.0 or dobot_x < 70.0) and is_rail:
                            cur_l = float(getattr(self.robot, "rail_current_pos", 0.0))
                            sol_rail = solve_rail_kinematics(dobot_x, dobot_y, current_rail_l=cur_l, calib_rail_l=0.0)

                    # Vẽ Bounding Box & tâm
                    box_color = (255, 215, 0) if sol_rail is not None else color
                    cv2.rectangle(display, (x1, y1), (x2, y2), box_color, 2)
                    cv2.circle(display, (int(u_center), int(v_center)), 4, (0, 0, 255) if sol_rail is None else (255, 255, 0), -1)

                    # Nhãn & Tọa độ
                    label_text = f"{cls_name} {conf:.2f}"
                    if sol_rail is not None:
                        coord_text = f"X:{dobot_x:.1f} Y:{dobot_y:.1f} [RAY L={sol_rail['optimal_l']:.0f}]"
                    else:
                        coord_text = f"X:{dobot_x:.1f} Y:{dobot_y:.1f}" if dobot_x is not None else ""

                    cv2.putText(display, label_text, (x1, max(18, y1 - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, box_color, 2)
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
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "sol_rail": sol_rail
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
            return {"success": False, "status": "error", "error": "Robot Dobot chưa kết nối!", "message": "Robot Dobot chưa kết nối!"}

        if self.is_picking:
            return {"success": False, "status": "error", "error": "Robot đang bận thực hiện chu trình trước!", "message": "Robot đang bận thực hiện chu trình trước!"}

        def _worker():
            self.is_picking = True
            try:
                if DROP_TARGETS_MODE == "all":
                    target_tray = DEFAULT_DROP_TARGET
                else:
                    target_tray = DROP_TARGETS_BY_COLOR.get(cube_name, DEFAULT_DROP_TARGET)
                drop_x = float(target_tray["x"])
                drop_y = float(target_tray["y"])
                drop_z = float(target_tray["z"])
                tray_rail_l = float(target_tray.get("rail_l", target_tray.get("l", 0.0)))
                pick_station_l = float(getattr(self, "calib_rail_l", CALIB_RAIL_L))

                print(f"[VisionEngine] 🚀 Bắt đầu gắp {cube_name} tại ({pick_x:.1f}, {pick_y:.1f}) -> Thả khay ({drop_x:.1f}, {drop_y:.1f}, Z={drop_z:.1f}, L={tray_rail_l:.1f})")

                # Kiểm tra chế độ ray trượt
                is_rail = bool(getattr(self.robot, "is_rail_mode", False))

                # Bước 0: Nếu có ray trượt và robot chưa ở vị trí bàn gắp (vị trí calib L = pick_station_l)
                if is_rail:
                    cur_rail_l = float(getattr(self.robot, "rail_current_pos", 0.0))
                    if abs(cur_rail_l - pick_station_l) > 1.0:
                        print(f"[VisionEngine] 🚄 Di chuyển ray về vị trí calib đón phôi L = {pick_station_l:.1f} mm...")
                        # Nâng tay lên an toàn trước khi di chuyển ray
                        cur_p = self.robot.get_pose() or {"x": 200.0, "y": 0.0, "z": Z_SAFE_FLANGE}
                        if cur_p.get("z", 0.0) < Z_SAFE_FLANGE - 5.0:
                            self.robot.move_to_xyz(cur_p["x"], cur_p["y"], Z_SAFE_FLANGE, r=0.0)
                            time.sleep(1.0)
                        self.robot.rail_move_to(pick_station_l, speed_mm_s=50.0)
                        time.sleep(0.4)
                    else:
                        print(f"[VisionEngine] 🎯 Robot đã sẵn sàng tại vị trí bàn gắp L = {cur_rail_l:.1f} mm!")

                # Bước 1: Bay an toàn tới phôi và hạ xuống gắp
                print(f"[VisionEngine] 🦾 Hạ tay gắp phôi {cube_name} tại ({pick_x:.1f}, {pick_y:.1f}, Z={Z_PICK_FLANGE:.1f})")
                self.robot.move_safe_jump(pick_x, pick_y, Z_PICK_FLANGE, r=0.0, safe_z=Z_SAFE_FLANGE)
                if hasattr(self.robot, "wait_pose_reached"):
                    self.robot.wait_pose_reached(pick_x, pick_y, Z_PICK_FLANGE, tol=6.0, timeout=3.5)
                else:
                    time.sleep(2.5)

                # Bước 2: Bật giác hút
                self.robot.set_suction(True)
                time.sleep(0.5)

                # Bước 3: Nhấc lên độ cao an toàn
                self.robot.move_to_xyz(pick_x, pick_y, Z_SAFE_FLANGE, r=0.0)
                if hasattr(self.robot, "wait_pose_reached"):
                    self.robot.wait_pose_reached(pick_x, pick_y, Z_SAFE_FLANGE, tol=6.0, timeout=2.5)
                else:
                    time.sleep(1.2)

                # Bước 4: Di chuyển ray về vị trí khay thả (nếu có ray)
                if is_rail:
                    cur_now_l = float(getattr(self.robot, "rail_current_pos", 0.0))
                    if abs(tray_rail_l - cur_now_l) > 1.0:
                        print(f"[VisionEngine] 🚄 Di chuyển ray về khay thả L = {tray_rail_l:.1f} mm...")
                        self.robot.rail_move_to(tray_rail_l, speed_mm_s=50.0)
                        time.sleep(0.4)
                    else:
                        print(f"[VisionEngine] 🎯 Khay thả đã nằm ngay tại L = {cur_now_l:.1f} mm!")

                # Bước 5: Bay sang điểm thả trong khay
                print(f"[VisionEngine] 📥 Đưa phôi vào khay tại ({drop_x:.1f}, {drop_y:.1f}, Z={drop_z:.1f})")
                self.robot.move_safe_jump(drop_x, drop_y, drop_z, r=0.0, safe_z=Z_SAFE_FLANGE)
                if hasattr(self.robot, "wait_pose_reached"):
                    self.robot.wait_pose_reached(drop_x, drop_y, drop_z, tol=6.0, timeout=3.5)
                else:
                    time.sleep(2.5)

                # Bước 6: Tắt giác hút (nhả phôi)
                self.robot.set_suction(False)
                time.sleep(0.4)

                # Bước 7: Nhấc lên an toàn hoàn tất chu trình
                self.robot.move_to_xyz(drop_x, drop_y, Z_SAFE_FLANGE, r=0.0)
                if hasattr(self.robot, "wait_pose_reached"):
                    self.robot.wait_pose_reached(drop_x, drop_y, Z_SAFE_FLANGE, tol=6.0, timeout=2.5)
                else:
                    time.sleep(1.2)

                print(f"[VisionEngine] ✅ Hoàn tất gắp thả {cube_name}!")
            except Exception as e:
                print(f"[VisionEngine] ❌ Lỗi chu trình gắp: {e}")
            finally:
                self.is_picking = False
                if on_complete:
                    on_complete()

        threading.Thread(target=_worker, daemon=True).start()
        return {"success": True, "status": "ok", "message": f"Đã gửi lệnh gắp {cube_name}"}

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
                            cx = float(coord["x"])
                            cy = float(coord["y"])
                            r = (cx**2 + cy**2)**0.5
                            is_reachable = False
                            if 140.0 <= r <= 330.0 and cx >= 70.0:
                                is_reachable = True
                            elif getattr(self.robot, "is_rail_mode", False):
                                cur_l = float(getattr(self.robot, "rail_current_pos", 0.0))
                                sol = solve_rail_kinematics(cx, cy, current_rail_l=cur_l, calib_rail_l=0.0)
                                if sol is not None:
                                    is_reachable = True

                            if is_reachable:
                                target_cube = c
                                break

                if target_cube:
                    cx = target_cube["dobot_coord"]["x"]
                    cy = target_cube["dobot_coord"]["y"]
                    cname = target_cube["class_name"]
                    self.execute_pick_and_place(cx, cy, cname)

            time.sleep(1.0)
        print("[VisionEngine] Đã dừng chế độ tự động phân loại.")
