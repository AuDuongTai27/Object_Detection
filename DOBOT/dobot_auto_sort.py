#!/usr/bin/env python3
"""
dobot_auto_sort.py
FABLAB - Hệ thống tự động nhận diện và phân loại khối màu bằng Dobot Magician.

Tích hợp toàn diện:
1. Khử méo thấu kính (calib_data_mono.json)
2. Nhận diện khối màu đa vật thể (Ưu tiên YOLO best_v8_more_augmentation.pt, best_v11.pt hoặc OpenCV HSV)
3. Chuyển đổi tọa độ Camera -> Dobot qua ma trận Homography (homography_dobot.json)
4. Tự động điều khiển Dobot gắp thả vào các khay phân loại màu tương ứng:
   - cube_red:    Khay Đỏ (Phải)
   - cube_green:  Khay Xanh lục (Phải)
   - cube_blue:   Khay Xanh dương (Trái)
   - cube_yellow: Khay Vàng (Trái)
"""

import os
import sys
import time
import json
import math
import struct
import argparse
import threading
import urllib.request
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

# Đường dẫn tương đối đa nền tảng (hoạt động tốt trên cả Windows và Linux)
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

CALIB_JSON_PATH = BASE_DIR / "calib_data_mono.json"
HOMOGRAPHY_JSON_PATH = BASE_DIR / "homography_dobot.json"
HOMOGRAPHY_NPY_PATH = BASE_DIR / "homography_dobot.npy"
MODEL_DIR = PROJECT_ROOT / "models"

# Độ cao chuẩn làm việc của Dobot (Z_Flange = Z_TCP + 59.5)
# Đã hạ tiếp 0.2 cm (2.0 mm): Z_TCP = -111.2 mm -> Z_Flange = -51.7 mm
Z_PICK_FLANGE = -51.7
Z_SAFE_FLANGE = 35.0

# Tọa độ điểm thả mặc định cho mọi khối màu theo cấu hình của bạn:
DEFAULT_DROP_TARGET = {
    "x": 49.2,
    "y": -230.1,
    "z": -44.0,
    "name": "Khay Thả (49.2, -230.1)"
}

# Tùy chọn: Tọa độ phân loại riêng biệt cho từng màu (nếu muốn xếp riêng từng khay)
# Mặc định gom về (49.2, -230.1) theo cấu hình mới của bạn
DROP_TARGETS_BY_COLOR = {
    "cube_red":    {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Đỏ (49.2, -230.1)"},
    "cube_green":  {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Xanh Lục (49.2, -230.1)"},
    "cube_blue":   {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Xanh Dương (49.2, -230.1)"},
    "cube_yellow": {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Vàng (49.2, -230.1)"},
}

# Độ bù trừ vị trí hút phôi (mm):
# Sau khi calib lại 4 điểm chuẩn xác (sai số 0.00 mm), đặt bù trừ về 0.0 mm
OFFSET_PICK_X = 0.0
OFFSET_PICK_Y = 0.0

# Dải màu HSV của OpenCV (Dùng dự phòng khi không nạp được YOLO)
COLOR_RANGES = {
    "cube_blue": {
        "lower": np.array([90, 70, 50]),
        "upper": np.array([135, 255, 255]),
        "bgr_color": (255, 120, 0),
    },
    "cube_green": {
        "lower": np.array([35, 70, 50]),
        "upper": np.array([85, 255, 255]),
        "bgr_color": (0, 230, 0),
    },
    "cube_yellow": {
        "lower": np.array([15, 80, 80]),
        "upper": np.array([38, 255, 255]),
        "bgr_color": (0, 230, 255),
    },
    "cube_red": {
        "lower_1": np.array([0, 70, 50]),
        "upper_1": np.array([10, 255, 255]),
        "lower_2": np.array([168, 70, 50]),
        "upper_2": np.array([180, 255, 255]),
        "bgr_color": (0, 0, 255),
    },
}


# ==============================================================================
# 1. BỘ CHUYỂN ĐỔI TỌA ĐỘ HOMOGRAPHY
# ==============================================================================
class HomographyTransformer:
    def __init__(self, json_path=HOMOGRAPHY_JSON_PATH):
        self.H = None
        self.load(json_path)

    def load(self, path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.H = np.array(data["homography_matrix"], dtype=np.float64)
            print(f"[+] Đã nạp Homography từ: {path}")
        elif os.path.exists(HOMOGRAPHY_NPY_PATH):
            self.H = np.load(HOMOGRAPHY_NPY_PATH)
            print(f"[+] Đã nạp Homography từ: {HOMOGRAPHY_NPY_PATH}")
        else:
            raise FileNotFoundError(f"Không tìm thấy file Homography tại {path}! Hãy chạy calibrate_camera_to_dobot.py trước.")

    def pixel_to_dobot(self, u, v):
        """Chuyển đổi (u, v) pixel sang (X, Y) Dobot (mm)."""
        vec = np.array([float(u), float(v), 1.0], dtype=np.float64)
        res = self.H @ vec
        if abs(res[2]) < 1e-9:
            return 0.0, 0.0
        return float(res[0] / res[2]), float(res[1] / res[2])


# ==============================================================================
# 2. BỘ ĐIỀU KHIỂN DOBOT (HỖ TRỢ CẢ HTTP API VÀ SERIAL TRỰC TIẾP)
# ==============================================================================
class DobotExecutor:
    def __init__(self, server_url="http://127.0.0.1:8080/api/cmd", drop_target=None, pick_z=Z_PICK_FLANGE):
        self.server_url = server_url
        self.drop_target = drop_target or DEFAULT_DROP_TARGET
        self.pick_z = pick_z
        self.ser = None
        self.is_busy = False
        self.use_http = self.check_http_server()

        if not self.use_http:
            self.init_serial()

    def check_http_server(self):
        try:
            req = urllib.request.Request(self.server_url, method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    print(f"[+] Đã kết nối thành công tới Dobot Live Server: {self.server_url}")
                    return True
        except Exception:
            pass
        return False

    def init_serial(self):
        """Dự phòng kết nối Serial nếu server chưa mở (hỗ trợ cả Windows COM và Linux ttyUSB)."""
        try:
            import serial
            import serial.tools.list_ports
            import glob

            selected_port = None
            ports = list(serial.tools.list_ports.comports())

            # 1. Tìm theo tên chip USB-UART phổ biến của Dobot (CP2102, FTDI, CH340)
            for p in ports:
                desc = f"{p.description} {p.manufacturer} {p.hwid}".lower()
                if any(k in desc for k in ["cp210", "silicon labs", "ch340", "ch341", "ftdi", "usb serial"]):
                    selected_port = p.device
                    break

            # 2. Nếu không tìm thấy theo tên, lấy cổng COM/tty đầu tiên khả dụng
            if not selected_port and ports:
                selected_port = ports[0].device
            elif not selected_port and sys.platform != "win32":
                devs = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
                if devs:
                    selected_port = devs[0]

            if selected_port:
                self.ser = serial.Serial(selected_port, 115200, timeout=0.1)
                print(f"[+] Mở kết nối Serial trực tiếp tới Dobot: {selected_port}")
                # ID 240: Start Queue
                self._send_raw_serial(240, 1)
            else:
                print("[-] Không phát hiện cổng Serial Dobot nào (Chế độ mô phỏng / chỉ camera).")
        except Exception as e:
            print(f"[!] Không mở được Serial: {e}")

    def _send_raw_serial(self, cmd_id, ctrl, params=b""):
        if not self.ser or not self.ser.is_open:
            return
        payload = bytes([cmd_id, ctrl]) + params
        length = len(payload)
        chk = (256 - (sum(payload) % 256)) % 256
        packet = b"\xAA\xAA" + bytes([length]) + payload + bytes([chk])
        self.ser.write(packet)

    def send_cmd(self, action_dict):
        """Gửi lệnh đến Dobot qua HTTP API hoặc Serial."""
        if self.use_http:
            try:
                data = json.dumps(action_dict).encode("utf-8")
                req = urllib.request.Request(self.server_url, data=data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    return resp.status == 200
            except Exception as e:
                print(f"[!] Lỗi gửi HTTP API: {e}")
                self.use_http = self.check_http_server()
        elif self.ser:
            action = action_dict.get("action")
            if action == "move_xyz":
                x, y, z, r = action_dict["x"], action_dict["y"], action_dict["z"], action_dict["r"]
                params = bytes([1]) + struct.pack("<4f", float(x), float(y), float(z), float(r))
                self._send_raw_serial(84, 3, params)
                return True
            elif action == "suction":
                val = 1 if action_dict.get("value") else 0
                self._send_raw_serial(62, 3, bytes([1, val]))
                self._send_raw_serial(62, 1, bytes([1, val]))
                return True
        return False

    def pick_and_place_async(self, pick_x, pick_y, cube_name, on_complete=None):
        """Chạy chu trình gắp thả trong luồng nền để không làm đứng khung hình camera."""
        if self.is_busy:
            print("[!] Robot đang bận thực hiện chu trình trước!")
            return False

        t = threading.Thread(target=self._pick_and_place_worker, args=(pick_x, pick_y, cube_name, on_complete), daemon=True)
        t.start()
        return True

    def _pick_and_place_worker(self, pick_x, pick_y, cube_name, on_complete):
        self.is_busy = True
        target = DROP_TARGETS_BY_COLOR.get(cube_name, self.drop_target)
        place_x = target.get("x", self.drop_target["x"])
        place_y = target.get("y", self.drop_target["y"])
        place_z = target.get("z", self.drop_target["z"])
        tray_name = target.get("name", f"({place_x:.1f}, {place_y:.1f})")

        print(f"\n🚀 BẮT ĐẦU GẮP: {cube_name} tại ({pick_x:.1f}, {pick_y:.1f}) ➔ Thả vào {tray_name} (X={place_x:.1f}, Y={place_y:.1f})")

        # 1. Bay trên đỉnh phôi ở độ cao an toàn (Safe Arch)
        self.send_cmd({"action": "move_xyz", "x": pick_x, "y": pick_y, "z": Z_SAFE_FLANGE, "r": 0.0, "mode": 1})
        time.sleep(1.6)

        # 2. Bật bơm hút
        self.send_cmd({"action": "suction", "value": True})
        time.sleep(0.3)

        # 3. Hạ thẳng xuống gắp khối màu (Z_pick = -49.7mm tương ứng Z_TCP = -109.2mm)
        self.send_cmd({"action": "move_xyz", "x": pick_x, "y": pick_y, "z": self.pick_z, "r": 0.0, "mode": 1})
        time.sleep(1.2)

        # 4. Nhấc lên cao an toàn
        self.send_cmd({"action": "move_xyz", "x": pick_x, "y": pick_y, "z": Z_SAFE_FLANGE, "r": 0.0, "mode": 1})
        time.sleep(1.2)

        # 5. Bay sang khay phân loại
        self.send_cmd({"action": "move_xyz", "x": place_x, "y": place_y, "z": Z_SAFE_FLANGE, "r": 0.0, "mode": 1})
        time.sleep(1.8)

        # 6. Hạ vào khay
        self.send_cmd({"action": "move_xyz", "x": place_x, "y": place_y, "z": place_z, "r": 0.0, "mode": 1})
        time.sleep(1.0)

        # 7. Nhả phôi (Tắt bơm & xả khí)
        self.send_cmd({"action": "suction", "value": False})
        time.sleep(0.5)

        # 8. Nhấc lên an toàn và hoàn tất
        self.send_cmd({"action": "move_xyz", "x": place_x, "y": place_y, "z": Z_SAFE_FLANGE, "r": 0.0, "mode": 1})
        time.sleep(1.0)

        print(f"✓ ĐÃ HOÀN TẤT GẮP THẢ: {cube_name}!\n")
        self.is_busy = False
        if on_complete:
            on_complete()


# ==============================================================================
# 3. CHƯƠNG TRÌNH NHẬN DIỆN VÀ PHÂN LOẠI CHÍNH
# ==============================================================================
def find_yolo_model(requested_model=None):
    """Tìm mô hình YOLO, ưu tiên best_v8_more_augmentation.pt theo khuyến nghị."""
    if requested_model:
        p = Path(requested_model)
        if p.exists():
            return p
        p = MODEL_DIR / requested_model
        if p.exists():
            return p

    # Danh sách ưu tiên nạp mô hình đã kiểm định
    priority_list = [
        MODEL_DIR / "best_11.pt",
        MODEL_DIR / "best_v11.pt",
        MODEL_DIR / "best_v8_more_augmentation.pt",
        BASE_DIR / "models" / "best_11.pt",
        BASE_DIR / "models" / "best_v8_more_augmentation.pt",
        Path("models/best_11.pt"),
        Path("models/best_v11.pt"),
        Path("models/best_v8_more_augmentation.pt"),
        Path("best_11.pt"),
        Path("best_v8_more_augmentation.pt"),
    ]
    for p in priority_list:
        if p.exists():
            return p

    # Tìm kiếm dự phòng
    fallback_pts = list(MODEL_DIR.glob("*.pt")) + list(Path("models").glob("*.pt"))
    if fallback_pts:
        return fallback_pts[0]
    return None


def main():
    parser = argparse.ArgumentParser(description="Dobot Vision Auto Sorting")
    parser.add_argument("--cam", type=int, default=1, help="ID camera (default: 1)")
    parser.add_argument("--engine", choices=["auto", "yolo", "opencv"], default="auto",
                        help="Engine nhận diện: 'yolo', 'opencv' hoặc 'auto' (default: auto)")
    parser.add_argument("--model", type=str, default=None,
                        help="Mô hình YOLO chỉ định (Mặc định: ưu tiên best_v8_more_augmentation.pt)")
    parser.add_argument("--width", type=int, default=1280, help="Độ rộng khung hình (1280)")
    parser.add_argument("--height", type=int, default=720, help="Độ cao khung hình (720)")
    parser.add_argument("--drop_x", type=float, default=49.2, help="Tọa độ X điểm thả (default: 49.2)")
    parser.add_argument("--drop_y", type=float, default=-230.1, help="Tọa độ Y điểm thả (default: -230.1)")
    parser.add_argument("--drop_z", type=float, default=-44.0, help="Tọa độ Z_Flange điểm thả (default: -44.0)")
    parser.add_argument("--pick_z", type=float, default=Z_PICK_FLANGE,
                        help=f"Độ cao Z_Flange khi hút (default: {Z_PICK_FLANGE} mm)")
    parser.add_argument("--offset_x", type=float, default=OFFSET_PICK_X,
                        help=f"Độ bù trừ trục X lúc hút (mm, default: {OFFSET_PICK_X} mm = 0.5 cm)")
    parser.add_argument("--offset_y", type=float, default=OFFSET_PICK_Y,
                        help=f"Độ bù trừ trục Y lúc hút (mm, default: {OFFSET_PICK_Y} mm)")
    args = parser.parse_args()

    drop_target = {
        "x": args.drop_x,
        "y": args.drop_y,
        "z": args.drop_z,
        "name": f"Khay Thả ({args.drop_x:.1f}, {args.drop_y:.1f})"
    }

    # Nạp ma trận Homography
    transformer = HomographyTransformer()

    # Nạp thông số khử méo camera
    K, D = None, None
    if os.path.exists(CALIB_JSON_PATH):
        try:
            with open(CALIB_JSON_PATH, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            K = np.array(cdata["matrix"] if "matrix" in cdata else cdata["left"]["matrix"], dtype=np.float64)
            D = np.array(cdata["distortion"] if "distortion" in cdata else cdata["left"]["distortion"], dtype=np.float64)
            print("[+] Đã nạp thông số khử méo thấu kính!")
        except Exception as e:
            print(f"[!] Không đọc được calib thấu kính: {e}")

    # Khởi tạo mô hình nhận diện (YOLO hoặc OpenCV)
    yolo_model = None
    loaded_model_name = "None"
    if args.engine in ["auto", "yolo"]:
        try:
            from ultralytics import YOLO
            model_path = find_yolo_model(args.model)
            if model_path and model_path.exists():
                print(f"[*] Đang nạp mô hình YOLO: {model_path.name} (Khuyên dùng v8 / v11)")
                yolo_model = YOLO(str(model_path))
                loaded_model_name = model_path.name
        except Exception as e:
            print(f"[!] Không thể khởi động YOLO ({e}), chuyển sang OpenCV HSV.")

    engine_name = f"YOLO ({loaded_model_name})" if yolo_model is not None else "OpenCV HSV"
    print(f"[*] Chế độ nhận diện đang chạy: {engine_name}")
    print(f"[*] Điểm thả phôi đã cài đặt: X={drop_target['x']:.1f}, Y={drop_target['y']:.1f}, Z_Flange={drop_target['z']:.1f}")
    print(f"[*] Độ cao hút phôi: Z_Flange={args.pick_z:.1f} mm (Z_TCP={args.pick_z - 59.5:.1f} mm)")
    print(f"[*] Độ bù vị trí hút: Offset X = +{args.offset_x:.1f} mm, Offset Y = {args.offset_y:.1f} mm")

    # Kết nối Dobot
    executor = DobotExecutor(drop_target=drop_target, pick_z=args.pick_z)

    # Mở Camera (hỗ trợ Windows DirectShow và Linux V4L2)
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_V4L2
    cap = cv2.VideoCapture(args.cam, backend)
    if not cap.isOpened():
        cap = cv2.VideoCapture(args.cam)
    if not cap.isOpened() and args.cam != 0:
        print(f"[!] Không thể mở camera {args.cam}, đang thử camera 0...")
        cap = cv2.VideoCapture(0, backend)
    if not cap.isOpened():
        print(f"[!] Không thể mở bất kỳ camera nào! Vui lòng kiểm tra lại thiết bị.")
        return

    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    cap.set(cv2.CAP_PROP_FOURCC, fourcc)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    win_name = "FABLAB - Dobot Magician Vision Auto-Sorting"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

    current_detected_cubes = []

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and not executor.is_busy:
            for cube in current_detected_cubes:
                bx, by, bw, bh = cube["box"]
                if bx <= x <= bx + bw and by <= y <= by + bh:
                    print(f"\n[+] BẠN ĐÃ CLICK VÀO: {cube['name']} tại ({cube['rx']:.1f}, {cube['ry']:.1f})")
                    executor.pick_and_place_async(cube["rx"], cube["ry"], cube["name"])
                    break

    cv2.setMouseCallback(win_name, on_mouse)

    auto_sort_enabled = False
    last_auto_pick_time = 0
    kernel = np.ones((5, 5), np.uint8)

    print("\n" + "=" * 65)
    print(" HƯỚNG DẪN ĐIỀU KHIỂN:")
    print(" - CLICK CHUỘT vào bất kỳ khối màu nào trên màn hình để gắp khối đó")
    print(" - Nhấn [SPACE] : Gắp khối màu đầu tiên tìm thấy")
    print(" - Nhấn [A]     : Bật / Tắt chế độ Tự Động Hoàn Toàn (Auto Sorting)")
    print(" - Nhấn [Q]     : Thoát chương trình")
    print("=" * 65 + "\n")

    while True:
        ret, raw_frame = cap.read()
        if not ret or raw_frame is None:
            time.sleep(0.01)
            continue

        # 1. Khử méo
        frame = cv2.undistort(raw_frame, K, D) if (K is not None and D is not None) else raw_frame
        h_img, w_img = frame.shape[:2]

        detected_cubes = []

        # 2. Nhận diện vật thể
        if yolo_model is not None:
            # Nhận diện qua YOLO
            results = yolo_model.predict(frame, imgsz=416, conf=0.65, verbose=False)
            boxes = results[0].boxes
            if boxes is not None:
                for b in boxes:
                    cls_id = int(b.cls[0])
                    name = yolo_model.names.get(cls_id, f"cube_{cls_id}")
                    xyxy = b.xyxy[0].cpu().numpy().astype(int)
                    x1, y1, x2, y2 = xyxy
                    bw, bh = x2 - x1, y2 - y1
                    cx, cy = x1 + bw // 2, y1 + bh // 2
                    rx, ry = transformer.pixel_to_dobot(cx, cy)
                    rx += args.offset_x
                    ry += args.offset_y
                    detected_cubes.append({
                        "name": name, "box": (x1, y1, bw, bh),
                        "center": (cx, cy), "rx": rx, "ry": ry,
                        "color": COLOR_RANGES.get(name, {}).get("bgr_color", (0, 255, 255))
                    })
        else:
            # Nhận diện qua OpenCV HSV
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            for name, cfg in COLOR_RANGES.items():
                if name == "cube_red":
                    m1 = cv2.inRange(hsv, cfg["lower_1"], cfg["upper_1"])
                    m2 = cv2.inRange(hsv, cfg["lower_2"], cfg["upper_2"])
                    mask = cv2.bitwise_or(m1, m2)
                else:
                    mask = cv2.inRange(hsv, cfg["lower"], cfg["upper"])

                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
                cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for c in cnts:
                    area = cv2.contourArea(c)
                    if area > 1800:
                        x, y, w, h = cv2.boundingRect(c)
                        cx, cy = x + w // 2, y + h // 2
                        rx, ry = transformer.pixel_to_dobot(cx, cy)
                        rx += args.offset_x
                        ry += args.offset_y
                        detected_cubes.append({
                            "name": name, "box": (x, y, w, h),
                            "center": (cx, cy), "rx": rx, "ry": ry,
                            "color": cfg["bgr_color"]
                        })

        current_detected_cubes = detected_cubes

        # 3. Vẽ thông tin lên màn hình
        for cube in detected_cubes:
            x, y, w, h = cube["box"]
            name = cube["name"]
            color = cube["color"]
            rx, ry = cube["rx"], cube["ry"]

            # Đánh dấu viền Bounding Box
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.circle(frame, cube["center"], 4, (0, 255, 255), -1)

            # Hiển thị Tên + Tọa độ Robot
            label = f"{name} | Robot: X={rx:.1f}, Y={ry:.1f}"
            t_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            cv2.rectangle(frame, (x, y - 24), (x + t_size[0] + 8, y), color, -1)
            cv2.putText(frame, label, (x + 4, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

        # 4. Thanh Header trạng thái
        cv2.rectangle(frame, (0, 0), (w_img, 45), (25, 25, 25), -1)
        robot_status = "DANG GAP THA..." if executor.is_busy else "SAN SANG (IDLE)"
        status_color = (0, 165, 255) if executor.is_busy else (0, 255, 0)
        mode_text = "[AUTO ON]" if auto_sort_enabled else "[MANUAL]"

        header_text = f"Dobot Vision: {engine_name} | Tim thay: {len(detected_cubes)} cube | Robot: {robot_status} | Che do: {mode_text}"
        cv2.putText(frame, header_text, (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2, cv2.LINE_AA)

        # 5. Xử lý chế độ Tự Động (Auto Sort)
        if auto_sort_enabled and not executor.is_busy:
            if time.time() - last_auto_pick_time > 2.0 and len(detected_cubes) > 0:
                # Chọn cube trong tầm với (140 <= R <= 330)
                valid_cubes = [c for c in detected_cubes if 140.0 <= math.hypot(c["rx"], c["ry"]) <= 330.0]
                if valid_cubes:
                    target = valid_cubes[0]
                    print(f"[*] AUTO TRIGGER: Gắp {target['name']} tại X={target['rx']:.1f}, Y={target['ry']:.1f}")
                    executor.pick_and_place_async(target["rx"], target["ry"], target["name"])
                    last_auto_pick_time = time.time()

        cv2.imshow(win_name, frame)

        key = cv2.waitKey(10) & 0xFF
        if key in [ord('q'), ord('Q'), 27]:
            break
        elif key == ord(' '): # Phím cách: Gắp khối đầu tiên
            if not executor.is_busy and len(detected_cubes) > 0:
                target = detected_cubes[0]
                print(f"[+] NHẤN SPACE: Gắp {target['name']} tại X={target['rx']:.1f}, Y={target['ry']:.1f}")
                executor.pick_and_place_async(target["rx"], target["ry"], target["name"])
        elif key in [ord('a'), ord('A')]: # Bật/Tắt Auto Sort
            auto_sort_enabled = not auto_sort_enabled
            print(f"[*] Chế độ Tự Động Phân Loại (Auto Sort): {'BẬT' if auto_sort_enabled else 'TẮT'}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
