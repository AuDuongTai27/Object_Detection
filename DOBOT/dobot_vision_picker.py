#!/usr/bin/env python3
"""
dobot_vision_picker.py
FABLAB - Module hỗ trợ chuyển đổi tọa độ thị giác và thực thi gắp thả tự động.

Chức năng:
1. Nạp ma trận Homography đã calib (từ homography_dobot.json hoặc homography_dobot.npy).
2. Hàm `pixel_to_dobot(u, v)`: Nhận tọa độ pixel của khối màu -> Trả về (X_robot, Y_robot) mm.
3. Hàm `pick_and_place(x, y, z_pick, target_box)`: Gửi lệnh qua WebSocket đến dobot_live_server.py
   để thực hiện chu trình hút và thả phôi vào khay tương ứng.
"""

import os
import sys
import json
import time
import math
from pathlib import Path
import numpy as np

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Thử import websocket-client nếu có
try:
    import websocket
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False

BASE_DIR = Path(__file__).resolve().parent
HOMOGRAPHY_JSON_PATH = str(BASE_DIR / "homography_dobot.json")
HOMOGRAPHY_NPY_PATH = str(BASE_DIR / "homography_dobot.npy")


class DobotVisionTransformer:
    def __init__(self, homography_path=HOMOGRAPHY_JSON_PATH):
        self.H = None
        self.load_homography(homography_path)

    def load_homography(self, path):
        if path.endswith(".npy") and os.path.exists(path):
            self.H = np.load(path)
            print(f"[+] Đã nạp ma trận Homography từ file NPY: {path}")
        elif os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.H = np.array(data["homography_matrix"], dtype=np.float64)
            mean_err = data.get("mean_error_mm", 0.0)
            print(f"[+] Đã nạp ma trận Homography từ JSON: {path} (Sai số calib: {mean_err:.2f} mm)")
        elif os.path.exists(HOMOGRAPHY_NPY_PATH):
            self.H = np.load(HOMOGRAPHY_NPY_PATH)
            print(f"[+] Đã nạp ma trận Homography từ file NPY mặc định: {HOMOGRAPHY_NPY_PATH}")
        else:
            print(f"[!] Chưa có file calib Homography tại: {path}")
            print("    -> Vui lòng chạy calibrate_camera_to_dobot.py trước!")

    def pixel_to_dobot(self, u, v):
        """
        Quy đổi từ tọa độ pixel (u, v) sang tọa độ Cartesian (X, Y) của Dobot (mm).
        """
        if self.H is None:
            raise RuntimeError("Chưa nạp ma trận Homography! Hãy chạy calibrate_camera_to_dobot.py")

        pt = np.array([[[float(u), float(v)]]], dtype=np.float32)
        dst = cv2_transform = cv2_perspective_transform(pt, self.H)
        rx = float(dst[0])
        ry = float(dst[1])
        return rx, ry

    def is_safe_coordinate(self, x, y):
        """Kiểm tra điểm đến có nằm trong tầm với an toàn của Dobot không."""
        r = math.hypot(x, y)
        return (140.0 <= r <= 330.0) and (-220.0 <= y <= 220.0) and (x >= 140.0)


def cv2_perspective_transform(pt, H):
    """Tính phép biến đổi phối cảnh 2D thuần NumPy (không phụ thuộc bắt buộc vào OpenCV)."""
    u, v = pt[0][0][0], pt[0][0][1]
    vec = np.array([u, v, 1.0], dtype=np.float64)
    res = H @ vec
    if abs(res[2]) < 1e-9:
        return (0.0, 0.0)
    x = res[0] / res[2]
    y = res[1] / res[2]
    return (x, y)


def execute_pick_and_place_ws(ws_url, pick_x, pick_y, pick_z=-55.0, place_x=49.2, place_y=-230.1, place_z=-44.0, safe_z=80.0):
    """
    Thực hiện chu trình gắp thả tự động bằng cách gửi lệnh JSON qua WebSocket tới dobot_live_server.py
    """
    if not HAS_WEBSOCKET:
        print("[!] Cần cài websocket-client: pip install websocket-client")
        return False

    try:
        ws = websocket.create_connection(ws_url, timeout=3.0)
        print(f"[+] Đã kết nối tới WebSocket Server: {ws_url}")

        # 1. Bay trên đỉnh phôi cần gắp
        print(f"[*] 1. Bay tới trên đỉnh phôi: X={pick_x:.1f}, Y={pick_y:.1f}, Z_safe={safe_z:.1f}")
        ws.send(json.dumps({"type": "move_xyz", "x": pick_x, "y": pick_y, "z": safe_z, "r": 0.0, "mode": 1}))
        time.sleep(1.8)

        # 2. Bật bơm hút
        print("[*] 2. Bật bơm hút chân không...")
        ws.send(json.dumps({"type": "suction", "enable": True}))
        time.sleep(0.3)

        # 3. Hạ thẳng xuống gắp phôi
        print(f"[*] 3. Hạ xuống gắp: Z={pick_z:.1f}")
        ws.send(json.dumps({"type": "move_xyz", "x": pick_x, "y": pick_y, "z": pick_z, "r": 0.0, "mode": 1}))
        time.sleep(1.2)

        # 4. Nhấc phôi lên cao an toàn
        print(f"[*] 4. Nhấc lên cao: Z={safe_z:.1f}")
        ws.send(json.dumps({"type": "move_xyz", "x": pick_x, "y": pick_y, "z": safe_z, "r": 0.0, "mode": 1}))
        time.sleep(1.2)

        # 5. Bay sang khay thả hàng
        print(f"[*] 5. Bay sang khay thả: X={place_x:.1f}, Y={place_y:.1f}")
        ws.send(json.dumps({"type": "move_xyz", "x": place_x, "y": place_y, "z": safe_z, "r": 0.0, "mode": 1}))
        time.sleep(1.8)

        # 6. Hạ xuống khay
        print(f"[*] 6. Hạ vào khay: Z={place_z:.1f}")
        ws.send(json.dumps({"type": "move_xyz", "x": place_x, "y": place_y, "z": place_z, "r": 0.0, "mode": 1}))
        time.sleep(1.0)

        # 7. Nhả phôi (Tắt bơm & xả khí)
        print("[*] 7. Nhả phôi...")
        ws.send(json.dumps({"type": "suction", "enable": False}))
        time.sleep(0.5)

        # 8. Nhấc lên và về Home
        ws.send(json.dumps({"type": "move_xyz", "x": place_x, "y": place_y, "z": safe_z, "r": 0.0, "mode": 1}))
        time.sleep(1.0)

        ws.close()
        print("[✓] HOÀN THÀNH CHU TRÌNH GẮP THẢ!")
        return True
    except Exception as e:
        print(f"[!] Lỗi kết nối WebSocket: {e}")
        return False


if __name__ == "__main__":
    transformer = DobotVisionTransformer()
    # Test mẫu nếu có file homography
    if transformer.H is not None:
        test_u, test_v = 640, 360
        rx, ry = transformer.pixel_to_dobot(test_u, test_v)
        print(f"Test quy đổi tâm ảnh ({test_u}, {test_v}) ➔ Dobot (X={rx:.1f} mm, Y={ry:.1f} mm)")
