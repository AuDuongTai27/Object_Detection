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
# Đã hạ tiếp 0.5 cm (5.0 mm): Mức tiếp xúc Z_TCP = -109.2 mm -> Hạ xuống Z_TCP = -114.2 mm (Z_Flange = -54.7 mm)
Z_PICK_FLANGE = -54.7
Z_SAFE_FLANGE = 35.0

DROP_TARGETS_JSON_PATH = BASE_DIR / "drop_targets.json"

# Tọa độ điểm thả mặc định cho mọi khối màu theo cấu hình của bạn:
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
CALIB_RAIL_L = 360.0

def load_drop_targets():
    """Tự động nạp tọa độ khay thả & Z gắp từ file drop_targets.json do Web Studio thiết lập."""
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
            print(f"[+] Đã nạp cấu hình vị trí thả đồ (Chế độ: {DROP_TARGETS_MODE}, Z_Pick={Z_PICK_FLANGE}mm, Calib_L={CALIB_RAIL_L}mm) từ: {DROP_TARGETS_JSON_PATH}")
        except Exception as e:
            print(f"[!] Lỗi khi nạp drop_targets.json: {e}")

load_drop_targets()

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
        self.H_inv = None
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

        # Tính toán ma trận nghịch đảo để chiếu ngược từ tọa độ Robot sang điểm ảnh Camera
        try:
            self.H_inv = np.linalg.inv(self.H)
        except Exception as e:
            print(f"[!] Lỗi nghịch đảo ma trận Homography: {e}")
            self.H_inv = None

    def pixel_to_dobot(self, u, v):
        """Chuyển đổi (u, v) pixel sang (X, Y) Dobot (mm)."""
        vec = np.array([float(u), float(v), 1.0], dtype=np.float64)
        res = self.H @ vec
        if abs(res[2]) < 1e-9:
            return 0.0, 0.0
        return float(res[0] / res[2]), float(res[1] / res[2])

    def dobot_to_pixel(self, rx, ry):
        """Chuyển đổi tọa độ Robot (rx, ry) sang điểm ảnh (u, v) trên khung hình camera."""
        if self.H_inv is None:
            return 0, 0
        vec = np.array([float(rx), float(ry), 1.0], dtype=np.float64)
        res = self.H_inv @ vec
        if abs(res[2]) < 1e-9:
            return 0, 0
        return int(round(res[0] / res[2])), int(round(res[1] / res[2]))

    def get_workspace_roi(self, r_min=140.0, r_max=330.0, x_min=70.0):
        """
        Tính toán đa giác và đường biên của Vùng Làm Việc An Toàn (140 <= R <= 330 mm, X >= 70 mm)
        chiếu trực tiếp lên hệ tọa độ điểm ảnh Camera.
        """
        if self.H_inv is None:
            return None, None, None, None, None

        # 1. Cung tròn ngoài R_MAX = 330 mm
        arc_outer = []
        for deg in np.linspace(-72, 72, 36):
            rad = np.radians(deg)
            rx = r_max * np.cos(rad)
            ry = r_max * np.sin(rad)
            if rx >= x_min:
                arc_outer.append(self.dobot_to_pixel(rx, ry))

        # 2. Cung tròn trong R_MIN = 140 mm
        arc_inner = []
        for deg in np.linspace(60, -60, 26):
            rad = np.radians(deg)
            rx = r_min * np.cos(rad)
            ry = r_min * np.sin(rad)
            if rx >= x_min:
                arc_inner.append(self.dobot_to_pixel(rx, ry))

        if not arc_outer or not arc_inner:
            return None, None, None, None, None

        # Đa giác khép kín bao quanh toàn bộ vùng an toàn
        poly_pts = np.array(arc_outer + arc_inner, dtype=np.int32)
        arc_outer_pts = np.array(arc_outer, dtype=np.int32)
        arc_inner_pts = np.array(arc_inner, dtype=np.int32)

        # Tọa độ đặt nhãn ghi chú
        lbl_outer = arc_outer[len(arc_outer) // 2]
        lbl_inner = arc_inner[len(arc_inner) // 2]

        return poly_pts, arc_outer_pts, arc_inner_pts, lbl_outer, lbl_inner


def is_safe_workspace(rx, ry, r_min=140.0, r_max=330.0, x_min=70.0):
    """
    Kiểm tra một tọa độ robot có nằm trong vùng làm việc an toàn hay không.
    Ngăn chặn tuyệt đối các lệnh gửi ra ngoài tầm với gây còi kêu, đèn đỏ (Alarm 0x10/0x11).
    """
    r = math.hypot(rx, ry)
    return (r_min <= r <= r_max) and (rx >= x_min)


def solve_rail_kinematics(rx, ry, current_rail_l=0.0, calib_rail_l=0.0):
    """
    Giải động học ray trượt 1000mm cho tọa độ camera (rx, ry) đã calib tại calib_rail_l.
    Tọa độ Dobot: X vươn xa từ ray, Y dọc theo hướng ray.
    Tọa độ World tương ứng:
      x_world = rx
      z_world = (calib_rail_l - 500.0) - ry
    Returns: dict { 'l', 'optimal_l', 'z_carriage', 'x', 'y', 'r', 'j1', ... } hoặc None nếu ngoài tầm ray 1000mm.
    """
    x_world = float(rx)
    z_world = float((calib_rail_l - 500.0) - ry)

    # Giới hạn vật lý khi Dobot gắn trên ray trượt:
    # Mép thanh nhôm định hình ray tại X ~ 70mm, tầm với tối đa của tay robot là ~330mm
    if x_world < 70.0 or x_world > 330.0:
        return None

    cur_l = max(0.0, min(1000.0, float(current_rail_l)))
    zc_cur = cur_l - 500.0
    y_arm_cur = -(z_world - zc_cur)
    r_cur = math.hypot(x_world, y_arm_cur)
    j1_cur_deg = math.degrees(math.atan2(y_arm_cur, x_world))

    def _make_res(l_val, zc_val, ya, r_val, j1_val, in_current_reach=False):
        l_f = round(float(l_val), 1)
        ya_f = round(float(ya), 1)
        r_f = round(float(r_val), 1)
        xw_f = round(float(x_world), 1)
        return {
            "l": l_f,
            "optimal_l": l_f,
            "z_carriage": round(float(zc_val), 1),
            "x": xw_f,
            "x_arm": xw_f,
            "y": ya_f,
            "y_arm": ya_f,
            "r": r_f,
            "r_arm": r_f,
            "j1": round(float(j1_val), 1),
            "x_world": xw_f,
            "z_world": round(float(z_world), 1),
            "in_current_reach": in_current_reach
        }

    # 2. Vị trí ray tối ưu (thẳng mặt mục tiêu z_world dọc trục ray)
    z_carriage_direct = max(-500.0, min(500.0, z_world))
    optimal_l_direct = z_carriage_direct + 500.0
    y_arm_direct = -(z_world - z_carriage_direct)
    r_direct = math.hypot(x_world, y_arm_direct)
    j1_direct_deg = math.degrees(math.atan2(y_arm_direct, x_world))

    # 1. KIỂM TRA ƯU TIÊN GẮP TẠI CHỖ:
    # Điểm chỉ được coi là "trong tầm gắp tại chỗ" khi xe trượt đang ở ngay sát vị trí tối ưu (lệch <= 40mm)
    # VÀ cánh tay ở tư thế tự nhiên thoải mái (bán kính 140..320mm, góc J1 <= 25 độ).
    # Nếu xe trượt đang ở xa (ví dụ đang ở khay thả L=150mm hay L=500mm), bắt buộc phải chạy ray về đón phôi!
    diff_l = abs(cur_l - optimal_l_direct)
    if diff_l <= 40.0 and 140.0 <= r_cur <= 320.0 and abs(j1_cur_deg) <= 25.0:
        return _make_res(cur_l, zc_cur, y_arm_cur, r_cur, j1_cur_deg, in_current_reach=True)

    # 3. Nếu đang ở xa hoặc góc lệch lớn: Giải vị trí ray tối ưu để đón phôi
    if x_world >= 150.0 and 140.0 <= r_direct <= 330.0 and abs(j1_direct_deg) <= 85.0:
        return _make_res(optimal_l_direct, z_carriage_direct, y_arm_direct, r_direct, j1_direct_deg, in_current_reach=False)

    # 3. Khi x_world < 150mm (ví dụ 70mm <= x_world < 150mm):
    # Dịch bàn trượt dọc theo ray để robot với chéo ở bán kính thoải mái r_target = 180mm.
    r_target = 180.0
    dy = math.sqrt(max(0.0, r_target * r_target - x_world * x_world))
    candidates = [z_world - dy, z_world + dy]

    best = None
    min_diff = float("inf")

    for zc in candidates:
        zc_clamped = max(-500.0, min(500.0, zc))
        l_cand = zc_clamped + 500.0
        y_arm = -(z_world - zc_clamped)
        r = math.hypot(x_world, y_arm)
        j1_deg = math.degrees(math.atan2(y_arm, x_world))

        if 140.0 <= r <= 330.0 and abs(j1_deg) <= 85.0:
            diff = abs(l_cand - cur_l)
            if diff < min_diff:
                min_diff = diff
                best = _make_res(l_cand, zc_clamped, y_arm, r, j1_deg, in_current_reach=False)

    # 4. Quét dự phòng dọc toàn bộ hành trình ray (0..1000mm)
    if not best:
        for l in range(0, 1001, 10):
            zc = float(l - 500.0)
            y_arm = -(z_world - zc)
            r = math.hypot(x_world, y_arm)
            j1_deg = math.degrees(math.atan2(y_arm, x_world))
            if 140.0 <= r <= 330.0 and abs(j1_deg) <= 85.0:
                diff = abs(l - cur_l)
                if diff < min_diff:
                    min_diff = diff
                    best = _make_res(l, zc, y_arm, r, j1_deg, in_current_reach=False)

    return best


def find_live_server_port(preferred_port=None):
    """Tự động dò cổng của Dobot Live Server (hỗ trợ cả 8080, 8081, 8082, 8088)."""
    if preferred_port:
        return preferred_port
    port_file = BASE_DIR / ".server_port.json"
    if port_file.exists():
        try:
            with open(port_file, "r", encoding="utf-8") as f:
                p = int(json.load(f).get("port", 8080))
                req = urllib.request.Request(f"http://127.0.0.1:{p}/api/cmd", method="GET")
                with urllib.request.urlopen(req, timeout=0.6) as resp:
                    if resp.status == 200:
                        return p
        except Exception:
            pass

    for p in [8080, 8081, 8082, 8088]:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{p}/api/cmd", method="GET")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                if resp.status == 200:
                    return p
        except Exception:
            pass
    return 8080


# ==============================================================================
# 2. BỘ ĐIỀU KHIỂN DOBOT (HỖ TRỢ CẢ HTTP API VÀ SERIAL TRỰC TIẾP)
# ==============================================================================
class DobotExecutor:
    def __init__(self, server_url=None, drop_target=None, pick_z=Z_PICK_FLANGE, server_port=None):
        self.server_port = server_port or find_live_server_port()
        self.server_url = server_url or f"http://127.0.0.1:{self.server_port}/api/cmd"
        self.drop_target = drop_target or DEFAULT_DROP_TARGET
        self.pick_z = float(pick_z)
        self.ser = None
        self.is_busy = False
        self.is_rail_mode = True
        self.rail_current_pos = 0.0
        self.current_task_status = {
            "state": "idle",
            "step": "ready",
            "msg": "Sẵn sàng",
            "error": False
        }
        self.use_http = self.check_http_server()

        if self.use_http:
            self.fetch_rail_status()

        if not self.use_http:
            self.init_serial()

    def fetch_rail_status(self):
        """Lấy trạng thái ray trượt và chế độ hoạt động từ Live Server."""
        if not self.use_http:
            return self.is_rail_mode, self.rail_current_pos
        for endpoint in [f"http://127.0.0.1:{self.server_port}/api/state", f"http://127.0.0.1:{self.server_port}/api/cmd"]:
            try:
                req = urllib.request.Request(endpoint, method="GET")
                with urllib.request.urlopen(req, timeout=0.8) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode())
                        rail_info = data.get("rail", {})
                        self.is_rail_mode = bool(data.get("is_rail_mode", rail_info.get("mode", True)))
                        self.rail_current_pos = float(data.get("rail_pos", rail_info.get("pos", self.rail_current_pos)))
                        break
            except Exception:
                pass
        return self.is_rail_mode, self.rail_current_pos

    def move_rail_and_wait(self, target_l, speed=100.0, timeout=15.0):
        """Di chuyển ray tới vị trí target_l (0..1000mm) và đợi dừng hẳn."""
        target_l = max(0.0, min(1000.0, float(target_l)))
        self.fetch_rail_status()
        delta = abs(target_l - self.rail_current_pos)
        if delta < 1.0:
            return True

        print(f"[Rail] 🚄 Đang di chuyển ray trượt tới L = {target_l:.1f} mm (Hiện tại: {self.rail_current_pos:.1f} mm)...")
        ok = self.send_cmd({"action": "rail_move", "pos": target_l, "l": target_l, "speed": speed})
        if not ok:
            return False

        t0 = time.time()
        time.sleep(0.3)
        while time.time() - t0 < timeout:
            self.fetch_rail_status()
            if abs(self.rail_current_pos - target_l) <= 1.5:
                print(f"[Rail] ✅ Ray đã tới đích L = {self.rail_current_pos:.1f} mm.")
                return True
            time.sleep(0.1)
        return False

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
                with urllib.request.urlopen(req, timeout=15.0) as resp:
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

    def get_pose(self):
        """Lấy tọa độ hiện tại (x, y, z, r, l) và cờ lỗi của robot từ Live Server."""
        if self.use_http:
            for endpoint in [f"http://127.0.0.1:{self.server_port}/api/state", f"http://127.0.0.1:{self.server_port}/api/cmd"]:
                try:
                    req = urllib.request.Request(endpoint, method="GET")
                    with urllib.request.urlopen(req, timeout=0.8) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode())
                            pose = data.get("pose", {})
                            has_alarm = bool(data.get("has_alarm", False) or len(data.get("alarms", [])) > 0)
                            if "rail_pos" in data:
                                self.rail_current_pos = float(data["rail_pos"])
                            return pose, has_alarm
                except Exception:
                    pass
        return None, False

    def wait_pose_reached(self, target_x: float, target_y: float, target_z: float, tol: float = 6.0, timeout: float = 6.0) -> bool:
        """Thăm dò thời gian thực: Khi robot tới tọa độ đích với độ lệch <= tol (mm) thì tiếp tục ngay lập tức, không lãng phí 0.1 giây nào."""
        if not self.use_http:
            time.sleep(1.0)
            return True
        t0 = time.time()
        time.sleep(0.08)  # Chờ 80ms nhỏ cho firmware bắt đầu nhận lệnh
        while time.time() - t0 < timeout:
            pose, has_alarm = self.get_pose()
            if has_alarm:
                print(f"[Safety] 🛑 Phát hiện đèn đỏ cảnh báo khi di chuyển tới ({target_x:.1f}, {target_y:.1f}, {target_z:.1f})!")
                return False
            if pose and "x" in pose and "y" in pose and "z" in pose:
                cur_x = float(pose["x"])
                cur_y = float(pose["y"])
                cur_z = float(pose["z"])
                if (abs(cur_x - float(target_x)) <= tol and
                    abs(cur_y - float(target_y)) <= tol and
                    abs(cur_z - float(target_z)) <= tol):
                    return True
            time.sleep(0.04)  # Thăm dò 25 lần/giây, tới đích là thoát ngay tức thì
        return not self.has_alarm()

    def has_alarm(self) -> bool:
        """Kiểm tra robot hiện tại có đang bị lỗi đèn đỏ không."""
        if self.use_http:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{self.server_port}/api/cmd", method="GET")
                with urllib.request.urlopen(req, timeout=0.8) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode())
                        return bool(data.get("has_alarm", False) or len(data.get("alarms", [])) > 0)
            except Exception:
                pass
        return False

    def recover_to_safe_pose(self) -> bool:
        """Kích hoạt cơ chế dừng ray, tắt hút và tự thu gọn về vị trí an toàn."""
        print("[Safety] 🛡️ KÍCH HOẠT CƠ CHẾ AN TOÀN: Dừng ray, tắt hút, tự thu gọn cánh tay...")
        if self.use_http:
            self.send_cmd({"action": "recover_pose"})
            time.sleep(1.5)
            return True
        elif self.ser:
            self._send_raw_serial(62, 1, bytes([1, 0]))  # Tắt hút
            self._send_raw_serial(21, 1)  # Clear alarms
            time.sleep(0.3)
            params = bytes([1]) + struct.pack("<4f", 200.0, 0.0, 45.0, 0.0)
            self._send_raw_serial(84, 3, params)
            time.sleep(1.5)
            return True
        return False

    def pick_and_place_async(self, pick_x, pick_y, cube_name, on_complete=None):
        """Chạy chu trình gắp thả trong luồng nền để không làm đứng khung hình camera."""
        if self.is_busy:
            print("[!] Robot đang bận thực hiện chu trình trước!")
            return False

        self.fetch_rail_status()
        t = threading.Thread(target=self._pick_and_place_worker, args=(pick_x, pick_y, cube_name, on_complete), daemon=True)
        t.start()
        return True

    def _pick_and_place_worker(self, pick_x, pick_y, cube_name, on_complete):
        self.is_busy = True
        try:
            # 0. Kiểm tra an toàn tầm với cánh tay (R=140..330mm, X>=50mm)
            pick_r = math.hypot(pick_x, pick_y)
            if pick_r < 140.0 or pick_r > 330.0 or pick_x < 50.0:
                print(f"[Safety] ⚠️ Tọa độ gắp ({pick_x:.1f}, {pick_y:.1f}, R={pick_r:.1f} mm) ngoài tầm vươn của Dobot! Hủy lệnh.")
                return

            if self.has_alarm():
                print("[Safety] ⚠️ Dobot đang bị đèn đỏ trước chu trình. Tự thu gọn xóa lỗi...")
                self.recover_to_safe_pose()
                time.sleep(0.5)

            if DROP_TARGETS_MODE == "all":
                target = self.drop_target
            else:
                target = DROP_TARGETS_BY_COLOR.get(cube_name, self.drop_target)
            place_x = float(target.get("x", self.drop_target["x"]))
            place_y = float(target.get("y", self.drop_target["y"]))
            place_z = float(target.get("z", self.drop_target["z"]))
            tray_name = target.get("name", f"({place_x:.1f}, {place_y:.1f})")

            # 1. NẾU CÓ RAY TRƯỢT: DI CHUYỂN RAY VỀ VỊ TRÍ BÀN GẮP (CALIB L)
            calib_rail_l = float(CALIB_RAIL_L)
            if self.is_rail_mode:
                delta_pick = abs(calib_rail_l - self.rail_current_pos)
                if delta_pick > 1.0:
                    print(f"[*] 🚄 Di chuyển ray về vị trí bàn gắp L = {calib_rail_l:.1f} mm...")
                    # Nâng tay lên an toàn trước khi di chuyển ray
                    self.send_cmd({"action": "move_xyz", "x": 200.0, "y": 0.0, "z": Z_SAFE_FLANGE, "r": 0.0, "mode": 1})
                    self.wait_pose_reached(200.0, 0.0, Z_SAFE_FLANGE, tol=8.0, timeout=4.0)
                    rail_ok = self.move_rail_and_wait(calib_rail_l)
                    if not rail_ok:
                        print(f"[Rail] 🛑 Không thể di chuyển ray về bàn gắp L={calib_rail_l:.1f} mm! Hủy chu trình.")
                        self.recover_to_safe_pose()
                        return
                else:
                    print(f"[*] 🎯 Robot đã sẵn sàng tại vị trí bàn gắp L = {self.rail_current_pos:.1f} mm!")

            print(f"\n🚀 BẮT ĐẦU GẮP: {cube_name} tại Dobot Arm (X={pick_x:.1f}, Y={pick_y:.1f}) ➔ Thả vào {tray_name} (X={place_x:.1f}, Y={place_y:.1f})")

            # 2. Bay trên đỉnh phôi ở độ cao an toàn (Safe Arch)
            self.send_cmd({"action": "move_xyz", "x": pick_x, "y": pick_y, "z": Z_SAFE_FLANGE, "r": 0.0, "mode": 1})
            self.wait_pose_reached(pick_x, pick_y, Z_SAFE_FLANGE, tol=6.0, timeout=5.0)

            # 3. Hạ thẳng xuống gắp khối màu
            self.send_cmd({"action": "move_xyz", "x": pick_x, "y": pick_y, "z": self.pick_z, "r": 0.0, "mode": 1})
            self.wait_pose_reached(pick_x, pick_y, self.pick_z, tol=6.0, timeout=7.0)

            # KIỂM TRA LỖI ĐÈN ĐỎ SAU KHI HẠ
            if self.has_alarm():
                print(f"[Safety] 🛑 Phát hiện đèn đỏ cảnh báo sau khi hạ gắp! HỦY DI CHUYỂN RAY, tự thu gọn an toàn...")
                self.recover_to_safe_pose()
                return

            # 4. Bật bơm hút
            self.send_cmd({"action": "suction", "value": True})
            time.sleep(0.3)

            # 5. Nhấc lên cao an toàn
            self.send_cmd({"action": "move_xyz", "x": pick_x, "y": pick_y, "z": Z_SAFE_FLANGE, "r": 0.0, "mode": 1})
            self.wait_pose_reached(pick_x, pick_y, Z_SAFE_FLANGE, tol=6.0, timeout=5.0)

            # KIỂM TRA LỖI ĐÈN ĐỎ SAU KHI NHẤC
            if self.has_alarm():
                print(f"[Safety] 🛑 Phát hiện đèn đỏ cảnh báo khi nhấc phôi! HỦY DI CHUYỂN RAY, tự thu gọn an toàn...")
                self.recover_to_safe_pose()
                return

            # 6. NẾU CÓ RAY TRƯỢT: DI CHUYỂN RAY VỀ VỊ TRÍ KHAY THẢ (CHỈ CHẠY NẾU GẮP THÀNH CÔNG VÀ KHÔNG BỊ ĐÈN ĐỎ)
            if self.is_rail_mode:
                tray_rail_l = float(target.get("rail_l", target.get("l", 0.0)))
                rail_ok = self.move_rail_and_wait(tray_rail_l)
                if not rail_ok:
                    print(f"[Rail] 🛑 Ray trượt chưa tới đích L={tray_rail_l:.1f} mm! Hủy thả để bảo vệ an toàn.")
                    self.recover_to_safe_pose()
                    return

            # 7. Bay sang khay phân loại
            self.send_cmd({"action": "move_xyz", "x": place_x, "y": place_y, "z": Z_SAFE_FLANGE, "r": 0.0, "mode": 1})
            self.wait_pose_reached(place_x, place_y, Z_SAFE_FLANGE, tol=6.0, timeout=6.0)

            # 8. Hạ vào khay
            self.send_cmd({"action": "move_xyz", "x": place_x, "y": place_y, "z": place_z, "r": 0.0, "mode": 1})
            self.wait_pose_reached(place_x, place_y, place_z, tol=6.0, timeout=6.0)

            # 9. Nhả phôi (Tắt bơm & xả khí)
            self.send_cmd({"action": "suction", "value": False})
            time.sleep(0.2)

            # 10. Nhấc lên an toàn và hoàn tất
            self.send_cmd({"action": "move_xyz", "x": place_x, "y": place_y, "z": Z_SAFE_FLANGE, "r": 0.0, "mode": 1})
            self.wait_pose_reached(place_x, place_y, Z_SAFE_FLANGE, tol=6.0, timeout=5.0)

            print(f"✓ ĐÃ HOÀN TẤT GẮP THẢ: {cube_name}!\n")
        except Exception as e:
            print(f"[VisionEngine] ❌ Lỗi chu trình gắp: {e}")
            self.recover_to_safe_pose()
        finally:
            self.is_busy = False
            if on_complete:
                on_complete()


# ==============================================================================
# 3. CHƯƠNG TRÌNH NHẬN DIỆN VÀ PHÂN LOẠI CHÍNH
# ==============================================================================
def find_yolo_model(requested_model=None):
    """Tìm mô hình YOLO, ưu tiên các mô hình .onnx siêu nhẹ theo khuyến nghị."""
    if requested_model:
        p = Path(requested_model)
        if p.exists():
            return p
        p = MODEL_DIR / requested_model
        if p.exists():
            return p
        p_onnx = MODEL_DIR / Path(requested_model).with_suffix(".onnx").name
        if p_onnx.exists():
            return p_onnx

    # Danh sách ưu tiên nạp mô hình ONNX siêu nhẹ
    priority_list = [
        MODEL_DIR / "best_trained.onnx",
        MODEL_DIR / "best_v8_more_augmentation.onnx",
        MODEL_DIR / "best_11.onnx",
        MODEL_DIR / "best_v11.onnx",
        MODEL_DIR / "yolov8n.onnx",
        PROJECT_ROOT / "yolov8n.onnx",
        # Dự phòng các file .pt cũ nếu chưa có onnx
        MODEL_DIR / "best_11.pt",
        MODEL_DIR / "best_v11.pt",
        MODEL_DIR / "best_v8_more_augmentation.pt",
        MODEL_DIR / "best_trained.pt",
    ]
    for p in priority_list:
        if p.exists():
            return p

    # Tìm kiếm dự phòng
    fallback_onnx = list(MODEL_DIR.glob("*.onnx"))
    if fallback_onnx:
        return fallback_onnx[0]
    fallback_pts = list(MODEL_DIR.glob("*.pt"))
    if fallback_pts:
        return fallback_pts[0]
    return None


def detect_available_cameras(max_tested=4):
    """Quét tìm tất cả camera đang kết nối."""
    available_cams = []
    for i in range(max_tested):
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(i, backend)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                available_cams.append((i, f"{w}x{h}"))
            cap.release()
    return available_cams


def open_camera(cam_index, width=1280, height=720):
    """Mở camera với DirectShow trên Windows để chống treo và nạp cấu hình phân giải."""
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(cam_index, backend)
    if not cap.isOpened() and sys.platform == "win32":
        cap = cv2.VideoCapture(cam_index)
    if cap.isOpened():
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


# ==============================================================================
# 4. TRỢ LÝ GIỌNG NÓI AI (VOICE ASSISTANT: PUSH-TO-TALK & SAFETY CONFIG)
# ==============================================================================
VOICE_CONFIG_PATH = BASE_DIR / "voice_config.json"


def parse_voice_command(raw_text):
    """Phân tích câu lệnh giọng nói tiếng Việt thành hành động robot."""
    t = raw_text.lower().strip()
    t_clean = t.replace(".", "").replace(",", "").replace("!", "")

    # 1. Phân tích màu sắc
    if any(k in t_clean for k in ["xanh lá", "xanh luc", "xanh lục", "lá cây", "lục"]):
        return {"action": "pick_color", "color": "cube_green", "color_vn": "xanh lục", "prompt": "Gắp khối xanh lục"}
    elif any(k in t_clean for k in ["xanh dương", "xanh biển", "da trời", "xanh nước biển", "biển"]):
        return {"action": "pick_color", "color": "cube_blue", "color_vn": "xanh dương", "prompt": "Gắp khối xanh dương"}
    elif any(k in t_clean for k in ["đỏ", "màu đỏ", "khối đỏ", "red"]):
        return {"action": "pick_color", "color": "cube_red", "color_vn": "đỏ", "prompt": "Gắp khối đỏ"}
    elif any(k in t_clean for k in ["vàng", "màu vàng", "khối vàng", "yellow"]):
        return {"action": "pick_color", "color": "cube_yellow", "color_vn": "vàng", "prompt": "Gắp khối vàng"}
    elif "xanh" in t_clean:  # Fallback nếu chỉ nói "màu xanh"
        return {"action": "pick_color", "color": "cube_blue", "color_vn": "xanh dương", "prompt": "Gắp khối xanh dương"}

    # 2. Phân tích các chế độ thao tác
    if any(k in t_clean for k in ["bật tự động", "chạy tự động", "tự động phân loại", "auto sort", "bật phân loại"]):
        return {"action": "enable_auto", "prompt": "Bật tự động phân loại"}
    elif any(k in t_clean for k in ["tắt tự động", "dừng tự động", "dừng phân loại", "dừng lại", "ngừng", "dừng"]):
        return {"action": "disable_auto", "prompt": "Dừng tự động phân loại"}
    elif any(k in t_clean for k in ["dừng khẩn cấp", "khẩn cấp", "cấp cứu"]):
        return {"action": "emergency_stop", "prompt": "Dừng khẩn cấp"}
    elif any(k in t_clean for k in ["về an toàn", "vị trí an toàn", "thu tay", "về home", "home"]):
        return {"action": "safe_home", "prompt": "Về vị trí an toàn"}
    elif any(k in t_clean for k in ["gắp một", "gắp 1", "gắp phôi", "gắp khối", "gắp vật", "gắp đi"]):
        return {"action": "pick_one", "prompt": "Gắp khối đầu tiên"}
    elif any(k in t_clean for k in ["đếm", "bao nhiêu"]):
        return {"action": "count", "prompt": "Đếm số lượng khối"}

    return {"action": "unknown", "prompt": raw_text}


class VoiceAssistantManager:
    """Quản lý Thu âm Push-To-Talk trên Camera, Nhận diện giọng nói tiếng Việt (STT) và Phản hồi (TTS)."""
    def __init__(self):
        self.confirm_required = True
        self.tts_enabled = True
        self.is_recording = False
        self.is_processing = False
        self.status_msg = ""
        self.last_status_time = 0.0
        self.pending_confirm = None
        self.confirm_expire = 0.0

        self._audio_frames = []
        self._stream = None
        self._tts_lock = threading.Lock()
        self.reload_config()

    def reload_config(self):
        """Đồng bộ cấu hình an toàn từ Web UI (voice_config.json)."""
        if VOICE_CONFIG_PATH.exists():
            try:
                with open(VOICE_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if "confirm_required" in cfg:
                    self.confirm_required = bool(cfg["confirm_required"])
                if "tts_enabled" in cfg:
                    self.tts_enabled = bool(cfg["tts_enabled"])
            except Exception:
                pass

    def start_recording(self):
        if self.is_recording or self.is_processing:
            return
        self.reload_config()
        try:
            import sounddevice as sd
            self._audio_frames = []
            self.is_recording = True
            self.status_msg = "Dang thu am giong noi... (Giu nut)"
            self.last_status_time = time.time()

            def _callback(indata, frames, time_info, status):
                if self.is_recording:
                    self._audio_frames.append(indata.copy())

            self._stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="int16",
                callback=_callback
            )
            self._stream.start()
            print("[VoiceAI] 🎙️ Bắt đầu thu âm giọng nói...")
        except Exception as e:
            print(f"[VoiceAI] ❌ Không mở được Micro: {e}")
            self.is_recording = False
            self.status_msg = f"Loi Micro: {e}"
            self.last_status_time = time.time()

    def stop_and_process(self, on_command_callback):
        if not self.is_recording:
            return
        self.is_recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if not self._audio_frames:
            self.status_msg = ""
            return

        self.is_processing = True
        self.status_msg = "Dang nhan dien giong noi..."
        self.last_status_time = time.time()

        def _worker():
            try:
                import io
                import numpy as np
                import soundfile as sf
                import speech_recognition as sr

                audio_data = np.concatenate(self._audio_frames, axis=0)
                if len(audio_data) < 16000 * 0.4:
                    print("[VoiceAI] ⚠️ Đoạn thu âm quá ngắn (<0.4s).")
                    self.status_msg = "Giong noi qua ngan"
                    self.last_status_time = time.time()
                    return

                wav_io = io.BytesIO()
                sf.write(wav_io, audio_data, 16000, format="WAV", subtype="PCM_16")
                wav_io.seek(0)

                recognizer = sr.Recognizer()
                with sr.AudioFile(wav_io) as source:
                    audio = recognizer.record(source)

                text = recognizer.recognize_google(audio, language="vi-VN")
                print(f"[VoiceAI] 🗣️ Nhận diện thành công: \"{text}\"")
                self.status_msg = f"Da nghe: \"{text}\""
                self.last_status_time = time.time()

                cmd = parse_voice_command(text)
                if on_command_callback:
                    on_command_callback(cmd, text)
            except Exception as e:
                err_str = str(e)
                if "UnknownValueError" in err_str or not err_str:
                    print("[VoiceAI] ⚠️ Không nhận diện rõ câu nói.")
                    self.status_msg = "Khong nghe ro cau noi"
                    self.last_status_time = time.time()
                    self.speak("Không thể thực hiện yêu cầu. Xin vui lòng nói lại.")
                else:
                    print(f"[VoiceAI] ❌ Lỗi STT: {e}")
                    self.status_msg = "Loi nhan dien"
                    self.last_status_time = time.time()
            finally:
                self.is_processing = False

        threading.Thread(target=_worker, daemon=True).start()

    def speak(self, text):
        self.reload_config()
        if not self.tts_enabled or not text:
            return

        def _tts_worker():
            with self._tts_lock:
                try:
                    import asyncio
                    import io
                    import sounddevice as sd
                    import soundfile as sf
                    import edge_tts

                    async def _gen():
                        comm = edge_tts.Communicate(text, "vi-VN-HoaiMyNeural")
                        chunks = []
                        async for chunk in comm.stream():
                            if chunk["type"] == "audio":
                                chunks.append(chunk["data"])
                        return b"".join(chunks)

                    raw = asyncio.run(_gen())
                    if raw:
                        data, fs = sf.read(io.BytesIO(raw))
                        sd.play(data, fs)
                        sd.wait()
                except Exception as e:
                    print(f"[VoiceAI TTS] ❌ Lỗi phát âm: {e}")

        threading.Thread(target=_tts_worker, daemon=True).start()

    def set_pending_confirm(self, cmd, prompt):
        self.pending_confirm = cmd
        self.pending_confirm["prompt"] = prompt
        self.confirm_expire = time.time() + 12.0

    def clear_pending_confirm(self):
        self.pending_confirm = None
        self.confirm_expire = 0.0


def draw_dobot_ui(
    frame,
    engine_name,
    cam_idx,
    detected_cubes,
    auto_sort_enabled,
    is_busy,
    is_rail_mode=False,
    rail_pos=0.0,
    show_workspace_roi=True,
    flash_msg="",
    alert_info=None,
    voice_mgr=None,
):
    """
    Vẽ giao diện hiển thị chuẩn gồm:
    1. Thanh tiêu đề phía trên (Model AI, Camera, Số khối phát hiện, Đèn trạng thái)
    2. Banner thông báo flash / Cảnh báo OSD / Xác nhận giọng nói an toàn
    3. Thanh 5 nút bấm điều khiển (có nút GIỮ ĐỂ NÓI tích hợp trực tiếp trên Camera)
    """
    h, w = frame.shape[:2]
    ui_frame = frame.copy()

    # --- 1. Thanh tiêu đề phía trên ---
    cv2.rectangle(ui_frame, (0, 0), (w, 45), (25, 25, 25), -1)
    cam_type = "USB Cam" if cam_idx > 0 else "Laptop Cam"
    rail_txt = f" | Ray: {rail_pos:.0f}mm" if is_rail_mode else ""
    title_text = f"Class: {engine_name}  |  Camera [{cam_idx} - {cam_type}]  |  Da phat hien: {len(detected_cubes)} khoi{rail_txt}"
    cv2.putText(ui_frame, title_text, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2, cv2.LINE_AA)

    # Đèn báo trạng thái ở góc phải thanh tiêu đề
    if is_busy:
        cv2.putText(ui_frame, "DANG GAP THA...", (w - 230, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 165, 255), 2, cv2.LINE_AA)
    elif auto_sort_enabled:
        blink = int(time.time() * 3) % 2 == 0
        rec_color = (0, 0, 255) if blink else (50, 50, 150)
        cv2.circle(ui_frame, (w - 245, 23), 10, rec_color, -1)
        cv2.putText(
            ui_frame,
            "AUTO SORT (BAT)",
            (w - 225, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
    else:
        cv2.putText(ui_frame, "THU CONG (SAN SANG)", (w - 250, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 2, cv2.LINE_AA)

    # --- 2. Thông báo Flash / Cảnh báo ngoài vùng / Xác nhận giọng nói ---
    if voice_mgr and voice_mgr.pending_confirm and time.time() < voice_mgr.confirm_expire:
        banner_h = 42
        cv2.rectangle(ui_frame, (0, 46), (w, 46 + banner_h), (50, 20, 80), -1)
        cv2.rectangle(ui_frame, (0, 46), (w, 46 + banner_h), (168, 85, 247), 2)
        confirm_txt = f"XAC NHAN LENH: {voice_mgr.pending_confirm.get('prompt', '')}?"
        cv2.putText(ui_frame, confirm_txt, (18, 46 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(ui_frame, "Bam [SPACE] de Dong Y  |  Bam [ESC] de Huy", (18, 46 + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 255, 255), 1, cv2.LINE_AA)
    elif alert_info and time.time() < alert_info.get("expire", 0):
        banner_h = 36
        cv2.rectangle(ui_frame, (0, 46), (w, 46 + banner_h), (0, 0, 180), -1)
        cv2.putText(ui_frame, alert_info["msg"], (18, 46 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    elif voice_mgr and (voice_mgr.is_recording or voice_mgr.is_processing or (time.time() - voice_mgr.last_status_time < 3.0 and voice_mgr.status_msg)):
        v_msg = f"[VOICE AI]: {voice_mgr.status_msg}"
        f_size = cv2.getTextSize(v_msg, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
        fx = (w - f_size[0]) // 2
        cv2.rectangle(ui_frame, (fx - 15, 50), (fx + f_size[0] + 15, 84), (40, 20, 70), -1)
        cv2.rectangle(ui_frame, (fx - 15, 50), (fx + f_size[0] + 15, 84), (168, 85, 247), 1)
        cv2.putText(ui_frame, v_msg, (fx, 74), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 200, 255), 2, cv2.LINE_AA)
    elif flash_msg:
        f_size = cv2.getTextSize(flash_msg, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)[0]
        fx = (w - f_size[0]) // 2
        cv2.rectangle(ui_frame, (fx - 15, 52), (fx + f_size[0] + 15, 88), (20, 20, 20), -1)
        cv2.rectangle(ui_frame, (fx - 15, 52), (fx + f_size[0] + 15, 88), (0, 255, 100), 1)
        cv2.putText(ui_frame, flash_msg, (fx, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 100), 2, cv2.LINE_AA)

    # --- 3. Thanh 5 nút bấm phía dưới đáy màn hình Camera ---
    bar_height = 70
    bar_y1 = h - bar_height
    cv2.rectangle(ui_frame, (0, bar_y1), (w, h), (35, 35, 35), -1)

    margin = 10
    btn_gap = 8
    total_gap = btn_gap * 4 + margin * 2
    btn_w = (w - total_gap) // 5
    btn_h = bar_height - 20
    btn_y1 = bar_y1 + 10
    btn_y2 = btn_y1 + btn_h

    # Nút 1: Tự động sort
    if auto_sort_enabled:
        btn1_text = "DUNG TU DONG"
        btn1_color = (0, 0, 220)
    else:
        btn1_text = "TU DONG SORT"
        btn1_color = (0, 90, 200)

    # Nút 3: Giữ để nói (Voice Assistant)
    if voice_mgr and voice_mgr.is_recording:
        btn_v_text = "DANG THU AM..."
        btn_v_key = "THA CHUOT GUI"
        btn_v_color = (0, 0, 220)  # Đỏ sáng khi thu âm
    elif voice_mgr and voice_mgr.is_processing:
        btn_v_text = "DANG NHAN DIEN"
        btn_v_key = "CHO TRONG GIAY LAT"
        btn_v_color = (0, 140, 255)  # Cam đang phân tích
    else:
        btn_v_text = "GIU DE NOI"
        btn_v_key = "PHIM [V]"
        btn_v_color = (140, 40, 180)  # Tím Voice AI

    btn_defs = [
        {"action": "toggle_auto", "text": btn1_text, "color": btn1_color, "key": "A"},
        {"action": "pick_one", "text": "GAP 1 KHOI", "color": (40, 160, 40), "key": "SPACE"},
        {"action": "voice_hold", "text": btn_v_text, "color": btn_v_color, "key": btn_v_key},
        {"action": "switch_cam", "text": "DOI CAMERA", "color": (180, 100, 30), "key": "S / TAB"},
        {"action": "quit", "text": "THOAT", "color": (60, 60, 180), "key": "Q / ESC"},
    ]

    buttons = []
    for i, btn in enumerate(btn_defs):
        bx1 = margin + i * (btn_w + btn_gap)
        bx2 = bx1 + btn_w

        cv2.rectangle(ui_frame, (bx1, btn_y1), (bx2, btn_y2), btn["color"], -1)
        cv2.rectangle(ui_frame, (bx1, btn_y1), (bx2, btn_y2), (255, 255, 255), 1)

        label_1 = btn["text"]
        label_2 = f"({btn['key']})"

        t_size1 = cv2.getTextSize(label_1, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 2)[0]
        tx1 = bx1 + (btn_w - t_size1[0]) // 2
        ty1 = btn_y1 + 20
        cv2.putText(ui_frame, label_1, (tx1, ty1), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 2, cv2.LINE_AA)

        t_size2 = cv2.getTextSize(label_2, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)[0]
        tx2 = bx1 + (btn_w - t_size2[0]) // 2
        ty2 = btn_y1 + 36
        cv2.putText(ui_frame, label_2, (tx2, ty2), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 220, 220), 1, cv2.LINE_AA)

        buttons.append({"rect": (bx1, btn_y1, bx2, btn_y2), "action": btn["action"]})

    return ui_frame, buttons



def main():
    parser = argparse.ArgumentParser(description="Dobot Vision Auto Sorting")
    parser.add_argument("--cam", type=int, default=1, help="ID camera (default: 1)")
    parser.add_argument("--engine", choices=["auto", "yolo", "opencv"], default="auto",
                        help="Engine nhận diện: 'yolo', 'opencv' hoặc 'auto' (default: auto)")
    parser.add_argument("--model", type=str, default=None,
                        help="Mô hình YOLO chỉ định (Mặc định: ưu tiên best_v8_more_augmentation.pt)")
    parser.add_argument("--width", type=int, default=1280, help="Độ rộng khung hình (1280)")
    parser.add_argument("--height", type=int, default=720, help="Độ cao khung hình (720)")
    parser.add_argument("--drop_x", type=float, default=None, help="Tọa độ X điểm thả (mặc định lấy từ drop_targets.json)")
    parser.add_argument("--drop_y", type=float, default=None, help="Tọa độ Y điểm thả (mặc định lấy từ drop_targets.json)")
    parser.add_argument("--drop_z", type=float, default=None, help="Tọa độ Z_Flange điểm thả (mặc định lấy từ drop_targets.json)")
    parser.add_argument("--pick_z", type=float, default=Z_PICK_FLANGE,
                        help=f"Độ cao Z_Flange khi hút (default: {Z_PICK_FLANGE} mm)")
    parser.add_argument("--offset_x", type=float, default=OFFSET_PICK_X,
                        help=f"Độ bù trừ trục X lúc hút (mm, default: {OFFSET_PICK_X} mm = 0.5 cm)")
    parser.add_argument("--offset_y", type=float, default=OFFSET_PICK_Y,
                        help=f"Độ bù trừ trục Y lúc hút (mm, default: {OFFSET_PICK_Y} mm)")
    parser.add_argument("--port", type=int, default=None,
                        help="Cổng HTTP của Dobot Live Server (mặc định: tự động dò)")
    args = parser.parse_args()

    drop_x = args.drop_x if args.drop_x is not None else DEFAULT_DROP_TARGET["x"]
    drop_y = args.drop_y if args.drop_y is not None else DEFAULT_DROP_TARGET["y"]
    drop_z = args.drop_z if args.drop_z is not None else DEFAULT_DROP_TARGET["z"]

    drop_target = {
        "x": drop_x,
        "y": drop_y,
        "z": drop_z,
        "name": f"Khay Thả ({drop_x:.1f}, {drop_y:.1f})"
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
                is_onnx = model_path.suffix.lower() == ".onnx"
                tag = "⚡ ONNX Siêu Nhẹ" if is_onnx else "PyTorch"
                print(f"[*] Đang nạp mô hình AI: {model_path.name} [{tag}]")
                if is_onnx:
                    yolo_model = YOLO(str(model_path), task="detect")
                else:
                    yolo_model = YOLO(str(model_path))
                loaded_model_name = model_path.name
        except Exception as e:
            print(f"[!] Không thể khởi động YOLO ({e}), chuyển sang OpenCV HSV.")

    engine_name = f"YOLO ({loaded_model_name})" if yolo_model is not None else "OpenCV HSV"
    print(f"[*] Chế độ nhận diện đang chạy: {engine_name}")
    print(f"[*] Điểm thả phôi đã cài đặt: X={drop_target['x']:.1f}, Y={drop_target['y']:.1f}, Z_Flange={drop_target['z']:.1f}")
    print(f"[*] Độ cao hút phôi: Z_Flange={args.pick_z:.1f} mm (Z_TCP={args.pick_z - 59.5:.1f} mm)")
    print(f"[*] Độ bù vị trí hút: Offset X = +{args.offset_x:.1f} mm, Offset Y = {args.offset_y:.1f} mm")

    # Kết nối Dobot (tự động nhận diện port 8080/8081)
    executor = DobotExecutor(drop_target=drop_target, pick_z=args.pick_z, server_port=args.port)

    # Mở Camera và tìm kiếm camera sẵn có
    available_cams = detect_available_cameras()
    available_indices = [idx for idx, _ in available_cams]
    if not available_indices:
        available_indices = [args.cam, 0] if args.cam != 0 else [0]
    if args.cam not in available_indices:
        available_indices.append(args.cam)

    current_cam_idx = args.cam
    cap = open_camera(current_cam_idx, args.width, args.height)
    if not cap.isOpened() and current_cam_idx != 0:
        print(f"[!] Không thể mở camera {current_cam_idx}, đang thử camera 0...")
        current_cam_idx = 0
        cap = open_camera(current_cam_idx, args.width, args.height)
    if not cap.isOpened():
        print(f"[!] Không thể mở bất kỳ camera nào! Vui lòng kiểm tra lại thiết bị.")
        return

    win_name = "Camera AI & Auto-Sorting - DOBOT FabLab"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    try:
        cv2.setWindowProperty(win_name, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass

    current_detected_cubes = []
    current_buttons = []
    mouse_action = None
    alert_info = {"msg": "", "expire": 0.0}
    flash_msg = ""
    flash_time = 0.0
    auto_sort_enabled = False

    # Khởi tạo Trợ lý giọng nói AI (Push-To-Talk trên camera)
    voice_mgr = VoiceAssistantManager()

    def execute_voice_command(cmd):
        nonlocal auto_sort_enabled, flash_msg, flash_time
        act = cmd.get("action")
        if act == "pick_color":
            target_color = cmd["color"]
            color_vn = cmd.get("color_vn", "màu")
            matched = [c for c in current_detected_cubes if c["name"] == target_color]
            valid = [c for c in matched if is_safe_workspace(c["rx"], c["ry"]) or (executor.is_rail_mode and solve_rail_kinematics(c["rx"], c["ry"], executor.rail_current_pos) is not None)]
            if valid:
                cube = valid[0]
                print(f"[VoiceAI] 🚀 Thực hiện gắp khối {cube['name']} tại ({cube['rx']:.1f}, {cube['ry']:.1f})")
                flash_msg = f"Dang gap {cube['name']}..."
                flash_time = time.time()
                voice_mgr.speak(f"Đang thực hiện gắp khối {color_vn}.")
                def _on_done():
                    voice_mgr.speak("Đã hoàn thành yêu cầu.")
                executor.pick_and_place_async(cube["rx"], cube["ry"], cube["name"], on_complete=_on_done)
            elif matched:
                print(f"[VoiceAI] ⚠️ Khối {target_color} nằm ngoài vùng an toàn.")
                flash_msg = f"Khoi {target_color} ngoai vung an toan!"
                flash_time = time.time()
                voice_mgr.speak(f"Không thể thực hiện yêu cầu. Khối {color_vn} nằm ngoài vùng an toàn.")
            else:
                print(f"[VoiceAI] ⚠️ Không tìm thấy khối {target_color} trên bàn.")
                flash_msg = f"Khong tim thay khoi {target_color}!"
                flash_time = time.time()
                voice_mgr.speak(f"Không thể thực hiện yêu cầu. Không tìm thấy khối {color_vn} trên bàn.")

        elif act == "pick_one":
            valid = [c for c in current_detected_cubes if is_safe_workspace(c["rx"], c["ry"]) or (executor.is_rail_mode and solve_rail_kinematics(c["rx"], c["ry"], executor.rail_current_pos) is not None)]
            if valid:
                cube = valid[0]
                voice_mgr.speak("Đang thực hiện gắp khối.")
                def _on_done():
                    voice_mgr.speak("Đã hoàn thành yêu cầu.")
                executor.pick_and_place_async(cube["rx"], cube["ry"], cube["name"], on_complete=_on_done)
            else:
                voice_mgr.speak("Không thể thực hiện yêu cầu. Không có khối nào trong vùng an toàn.")

        elif act == "enable_auto":
            auto_sort_enabled = True
            flash_msg = "Giong noi: Bat tu dong phan loai"
            flash_time = time.time()
            voice_mgr.speak("Đã bật chế độ tự động phân loại.")

        elif act == "disable_auto":
            auto_sort_enabled = False
            flash_msg = "Giong noi: Dung tu dong phan loai"
            flash_time = time.time()
            voice_mgr.speak("Đã dừng chế độ tự động phân loại.")

        elif act == "safe_home":
            flash_msg = "Giong noi: Ve vi tri an toan"
            flash_time = time.time()
            executor.recover_to_safe_pose()
            voice_mgr.speak("Đã đưa robot về vị trí an toàn.")

        elif act == "emergency_stop":
            auto_sort_enabled = False
            flash_msg = "Giong noi: DUNG KHAN CAP"
            flash_time = time.time()
            executor.recover_to_safe_pose()
            voice_mgr.speak("Đã kích hoạt dừng khẩn cấp.")

        elif act == "count":
            n = len(current_detected_cubes)
            flash_msg = f"Phat hien: {n} khoi"
            flash_time = time.time()
            voice_mgr.speak(f"Hệ thống phát hiện được {n} khối màu trên bàn.")

        else:
            voice_mgr.speak("Không thể thực hiện yêu cầu. Lệnh không hợp lệ.")

    def handle_voice_command(cmd, raw_text):
        nonlocal flash_msg, flash_time
        if not cmd or cmd.get("action") == "unknown":
            voice_mgr.speak("Không thể thực hiện yêu cầu. Xin vui lòng nói lại.")
            return

        voice_mgr.reload_config()
        # Kiểm tra chế độ yêu cầu xác nhận an toàn trước khi di chuyển
        if voice_mgr.confirm_required and cmd.get("action") in ["pick_color", "pick_one", "enable_auto", "safe_home"]:
            prompt = cmd.get("prompt", "thực hiện lệnh")
            voice_mgr.set_pending_confirm(cmd, prompt)
            flash_msg = f"Xac nhan: {prompt}? [SPACE]: Dong y | [ESC]: Huy"
            flash_time = time.time() + 12.0
            voice_mgr.speak(f"Bạn có muốn {prompt.lower()} không? Bấm phím SPACE để xác nhận hoặc ESC để hủy.")
        else:
            execute_voice_command(cmd)

    # Khởi tạo dữ liệu hình học Vùng Làm Việc An Toàn (ROI 140 <= R <= 330 mm, X >= 70 mm)
    roi_poly, roi_arc_outer, roi_arc_inner, roi_lbl_outer, roi_lbl_inner = transformer.get_workspace_roi()
    show_workspace_roi = True

    def on_mouse(event, x, y, flags, param):
        nonlocal mouse_action
        if event == cv2.EVENT_LBUTTONDOWN:
            # 1. Kiểm tra click vào nút bấm dưới thanh action bar
            for btn in current_buttons:
                bx1, by1, bx2, by2 = btn["rect"]
                if bx1 <= x <= bx2 and by1 <= y <= by2:
                    if btn["action"] == "voice_hold":
                        voice_mgr.start_recording()
                        return
                    else:
                        mouse_action = btn["action"]
                        return

            # 2. Kiểm tra click vào khối màu để gắp
            if not executor.is_busy:
                for cube in current_detected_cubes:
                    bx, by, bw, bh = cube["box"]
                    if bx <= x <= bx + bw and by <= y <= by + bh:
                        rx, ry = cube["rx"], cube["ry"]
                        r_dist = math.hypot(rx, ry)
                        sol_rail = None
                        can_pick = is_safe_workspace(rx, ry)
                        if not can_pick and executor.is_rail_mode:
                            sol_rail = solve_rail_kinematics(rx, ry, current_rail_l=executor.rail_current_pos)
                            if sol_rail is not None:
                                can_pick = True

                        if not can_pick:
                            print(f"\n[!] TỪ CHỐI GẮP: {cube['name']} nằm ngoài vùng an toàn (X={rx:.1f}, Y={ry:.1f}, R={r_dist:.1f}mm)!")
                            alert_info["msg"] = f"CANH BAO: {cube['name']} NGOAI VUNG AN TOAN! (R={r_dist:.1f}mm | YEU CAU 140 <= R <= 330 mm)"
                            alert_info["expire"] = time.time() + 3.0
                            break

                        if sol_rail is not None:
                            print(f"\n[+] BẠN ĐÃ CLICK VÀO: {cube['name']} tại ({cube['rx']:.1f}, {cube['ry']:.1f}) | CẦN DI CHUYỂN RAY ĐẾN L={sol_rail['optimal_l']:.1f}mm")
                        else:
                            print(f"\n[+] BẠN ĐÃ CLICK VÀO: {cube['name']} tại ({cube['rx']:.1f}, {cube['ry']:.1f}) | R={r_dist:.1f}mm")
                        executor.pick_and_place_async(cube["rx"], cube["ry"], cube["name"])
                        break

        elif event == cv2.EVENT_LBUTTONUP:
            if voice_mgr.is_recording:
                voice_mgr.stop_and_process(handle_voice_command)

    cv2.setMouseCallback(win_name, on_mouse)

    last_auto_pick_time = 0
    kernel = np.ones((5, 5), np.uint8)

    print("\n" + "=" * 65)
    print(" HƯỚNG DẪN ĐIỀU KHIỂN AUTO SORT & TRỢ LÝ GIỌNG NÓI AI:")
    print(" - NHẤN GIỮ NÚT [GIỮ ĐỂ NÓI] (hoặc Phím [V]): Ra lệnh giọng nói tiếng Việt")
    print(" - CLICK CHUỘT vào bất kỳ khối màu nào trên màn hình để gắp tức thì")
    print(" - Nhấn [SPACE] : Gắp khối đầu tiên (hoặc Đồng ý xác nhận lệnh giọng nói)")
    print(" - Nhấn [A]     : Bật / Tắt chế độ Tự Động Hoàn Toàn (Auto Sorting)")
    print(" - Nhấn [W]     : Bật / Tắt hiển thị Vùng Làm Việc An Toàn (ROI)")
    print(" - Nhấn [Q/ESC] : Thoát chương trình (hoặc Hủy lệnh xác nhận an toàn)")
    print("=" * 65 + "\n")

    # Xóa lệnh Tab 6 còn sót từ phiên trước để robot không tự chạy khi vừa mở tool
    try: (BASE_DIR / ".auto_sort_cmd.json").unlink(missing_ok=True)
    except Exception: pass

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

        # Ghi danh sách khối màu phát hiện ra file chia sẻ để Web Studio và Tab 6 dùng chung
        try:
            shared_tmp = BASE_DIR / ".detected_cubes.json.tmp"
            with open(shared_tmp, "w", encoding="utf-8") as f_det:
                json.dump({
                    "timestamp": time.time(),
                    "count": len(detected_cubes),
                    "auto_sort_enabled": auto_sort_enabled,
                    "is_busy": executor.is_busy,
                    "task_status": getattr(executor, "current_task_status", None),
                    "cubes": [
                        {
                            "class_name": c["name"],
                            "rx": float(c["rx"]),
                            "ry": float(c["ry"]),
                            "dobot_coord": {"x": float(c["rx"]), "y": float(c["ry"])},
                            "dobot_x": float(c["rx"]),
                            "dobot_y": float(c["ry"]),
                            "confidence": 0.95
                        }
                        for c in detected_cubes
                    ]
                }, f_det)
            os.replace(shared_tmp, BASE_DIR / ".detected_cubes.json")
        except Exception:
            pass


        # 3. Vẽ Lớp Phủ Vùng Làm Việc An Toàn (Workspace ROI: 140 <= R <= 330 mm)
        if show_workspace_roi and roi_poly is not None and len(roi_poly) > 0:
            overlay = frame.copy()
            cv2.fillPoly(overlay, [roi_poly], (20, 60, 20))
            cv2.addWeighted(overlay, 0.20, frame, 0.80, 0, frame)
            if roi_arc_inner is not None and len(roi_arc_inner) > 0:
                cv2.polylines(frame, [roi_arc_inner], False, (0, 165, 255), 2, cv2.LINE_AA)
                cv2.putText(frame, "R_MIN 140mm", (roi_lbl_inner[0] - 40, roi_lbl_inner[1] + 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 165, 255), 1, cv2.LINE_AA)

        # 4. Vẽ thông tin các phôi phát hiện
        for cube in detected_cubes:
            x, y, w, h = cube["box"]
            name = cube["name"]
            color = cube["color"]
            rx, ry = cube["rx"], cube["ry"]
            r_dist = math.hypot(rx, ry)
            safe = is_safe_workspace(rx, ry)
            sol_rail = None
            if not safe and executor.is_rail_mode:
                sol_rail = solve_rail_kinematics(rx, ry, current_rail_l=executor.rail_current_pos)

            if safe:
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.circle(frame, cube["center"], 4, (0, 255, 0), -1)

                label = f"{name} [SAFE] | X={rx:.1f}, Y={ry:.1f} (R={r_dist:.0f})"
                t_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0]
                cv2.rectangle(frame, (x, y - 22), (x + t_size[0] + 6, y), color, -1)
                cv2.putText(frame, label, (x + 3, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            elif sol_rail is not None:
                rail_color = (255, 215, 0)
                cv2.rectangle(frame, (x, y), (x + w, y + h), rail_color, 2)
                cv2.circle(frame, cube["center"], 4, (255, 255, 0), -1)

                opt_l = sol_rail["optimal_l"]
                label = f"{name} [CAN RAY L={opt_l:.0f}mm] | X={rx:.1f}, Y={ry:.1f}"
                t_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0]
                cv2.rectangle(frame, (x, y - 22), (x + t_size[0] + 6, y), (180, 100, 0), -1)
                cv2.putText(frame, label, (x + 3, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            else:
                red_color = (0, 0, 240)
                cv2.rectangle(frame, (x, y), (x + w, y + h), red_color, 2)
                cv2.line(frame, (x, y), (x + w, y + h), red_color, 2, cv2.LINE_AA)
                cv2.line(frame, (x, y + h), (x + w, y), red_color, 2, cv2.LINE_AA)
                cv2.circle(frame, cube["center"], 4, red_color, -1)

                label = f"{name} [OUT OF BOUNDS: R={r_dist:.0f}mm] (BLOCKED)"
                t_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0]
                cv2.rectangle(frame, (x, y - 22), (x + t_size[0] + 6, y), red_color, -1)
                cv2.putText(frame, label, (x + 3, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

        # 5. Vẽ giao diện Header & Bottom Action Bar chuẩn đẹp với nút Giữ Để Nói (Voice Assistant)
        display_frame, current_buttons = draw_dobot_ui(
            frame=frame,
            engine_name=engine_name,
            cam_idx=current_cam_idx,
            detected_cubes=detected_cubes,
            auto_sort_enabled=auto_sort_enabled,
            is_busy=executor.is_busy,
            is_rail_mode=executor.is_rail_mode,
            rail_pos=executor.rail_current_pos,
            show_workspace_roi=show_workspace_roi,
            flash_msg=flash_msg if (time.time() - flash_time <= 1.5) else "",
            alert_info=alert_info,
            voice_mgr=voice_mgr,
        )

        # 6. Xử lý chế độ Tự Động (Auto Sort)
        if auto_sort_enabled and not executor.is_busy:
            if time.time() - last_auto_pick_time > 2.0 and len(detected_cubes) > 0:
                valid_cubes = [c for c in detected_cubes if is_safe_workspace(c["rx"], c["ry"]) or (executor.is_rail_mode and solve_rail_kinematics(c["rx"], c["ry"], executor.rail_current_pos) is not None)]
                if valid_cubes:
                    target = valid_cubes[0]
                    print(f"[*] AUTO TRIGGER: Gắp {target['name']} tại X={target['rx']:.1f}, Y={target['ry']:.1f}")
                    executor.pick_and_place_async(target["rx"], target["ry"], target["name"])
                    last_auto_pick_time = time.time()

        cv2.imshow(win_name, display_frame)

        key = cv2.waitKey(10) & 0xFF

        action = None
        if mouse_action is not None:
            action = mouse_action
            mouse_action = None
        elif key in [ord('v'), ord('V')]:
            # Phím tắt V để thu âm giọng nói
            if not voice_mgr.is_recording:
                voice_mgr.start_recording()
            else:
                voice_mgr.stop_and_process(handle_voice_command)
        elif key in [ord('a'), ord('A')]:
            action = "toggle_auto"
        elif key == 32:  # SPACE
            if voice_mgr.pending_confirm and time.time() < voice_mgr.confirm_expire:
                confirmed_cmd = voice_mgr.pending_confirm
                voice_mgr.clear_pending_confirm()
                execute_voice_command(confirmed_cmd)
            else:
                action = "pick_one"
        elif key in [ord('s'), ord('S'), 9]:  # S / TAB
            action = "switch_cam"
        elif key in [ord('q'), ord('Q'), 27]:  # Q / ESC
            if voice_mgr.pending_confirm and time.time() < voice_mgr.confirm_expire and key == 27:
                voice_mgr.clear_pending_confirm()
                voice_mgr.speak("Đã hủy yêu cầu.")
                flash_msg = "Da huy lenh xac nhan giong noi."
                flash_time = time.time()
            else:
                action = "quit"
        elif key in [ord('w'), ord('W')]:
            action = "toggle_roi"

        # 6.5. Tiếp nhận lệnh điều khiển đồng bộ từ Tab 6 (Cử chỉ tay) & Web Studio
        cmd_file = BASE_DIR / ".auto_sort_cmd.json"
        if cmd_file.exists():
            try:
                with open(cmd_file, "r", encoding="utf-8") as f_cmd:
                    ext_cmd = json.load(f_cmd)
                try: cmd_file.unlink(missing_ok=True)
                except Exception: pass
                cmd_ts = float(ext_cmd.get("ts", 0))
                # Bỏ qua lệnh cũ (quá 3 giây nếu có ts)
                if cmd_ts > 0 and (time.time() - cmd_ts) > 3.0:
                    ext_act = None
                else:
                    ext_act = ext_cmd.get("action")
                if ext_act == "toggle_auto":
                    req_enable = ext_cmd.get("enable")
                    if req_enable is not None:
                        auto_sort_enabled = bool(req_enable)
                    else:
                        auto_sort_enabled = not auto_sort_enabled
                    status_str = "BẬT" if auto_sort_enabled else "TẮT"
                    flash_msg = f"Tu dong phan loai: {status_str}"
                    flash_time = time.time()
                    print(f"[*] [Cử chỉ Tab 6 🤟] Chế độ Tự Động Phân Loại (Auto Sort): {status_str}")
                elif ext_act == "pick_color":
                    target_color = str(ext_cmd.get("color", "")).lower().strip()
                    matched = [c for c in detected_cubes if target_color in c["name"].lower() or c["name"].lower() in target_color]
                    valid = [c for c in matched if is_safe_workspace(c["rx"], c["ry"]) or (executor.is_rail_mode and solve_rail_kinematics(c["rx"], c["ry"], executor.rail_current_pos) is not None)]
                    if valid and not executor.is_busy:
                        target = valid[0]
                        print(f"[+] [Cử chỉ Tab 6] LỆNH GẮP: {target['name']} tại X={target['rx']:.1f}, Y={target['ry']:.1f}")
                        executor.pick_and_place_async(target["rx"], target["ry"], target["name"])
                        flash_msg = f"Dang gap {target['name']}..."
                        flash_time = time.time()
                    elif not matched:
                        flash_msg = f"Khong thay khoi {target_color}!"
                        flash_time = time.time()
                        print(f"[!] [Cử chỉ Tab 6] Camera không thấy khối {target_color} trên bàn!")
                    elif not valid:
                        flash_msg = f"Khoi {target_color} ngoai tam an toan!"
                        flash_time = time.time()
                        print(f"[!] [Cử chỉ Tab 6] Không tìm thấy phôi {target_color} trong tầm với an toàn!")
                elif ext_act == "emergency_stop":
                    auto_sort_enabled = False
                    executor.recover_to_safe_pose()
                    flash_msg = "Dung khan cap!"
                    flash_time = time.time()
            except Exception as e:
                try: cmd_file.unlink(missing_ok=True)
                except Exception: pass

        # 7. Xử lý các tác vụ điều khiển
        if action == "toggle_auto":
            auto_sort_enabled = not auto_sort_enabled
            status_str = "BAT" if auto_sort_enabled else "TAT"
            flash_msg = f"Tu dong phan loai: {status_str}"
            flash_time = time.time()
            print(f"[*] Chế độ Tự Động Phân Loại (Auto Sort): {status_str}")

        elif action == "pick_one":
            if not executor.is_busy and len(detected_cubes) > 0:
                safe_candidates = [c for c in detected_cubes if is_safe_workspace(c["rx"], c["ry"]) or (executor.is_rail_mode and solve_rail_kinematics(c["rx"], c["ry"], executor.rail_current_pos) is not None)]
                if safe_candidates:
                    target = safe_candidates[0]
                    print(f"[+] LỆNH GẮP: {target['name']} tại X={target['rx']:.1f}, Y={target['ry']:.1f}")
                    executor.pick_and_place_async(target["rx"], target["ry"], target["name"])
                    flash_msg = f"Dang gap {target['name']}..."
                    flash_time = time.time()
                else:
                    flash_msg = "Khong co khoi an toan trong tam voi!"
                    flash_time = time.time()
                    print("[!] Không có phôi nào nằm trong tầm với của Robot (kể cả ray trượt) để gắp!")

        elif action == "switch_cam":
            if len(available_indices) > 1:
                cur_pos = available_indices.index(current_cam_idx) if current_cam_idx in available_indices else 0
                next_pos = (cur_pos + 1) % len(available_indices)
                current_cam_idx = available_indices[next_pos]
                print(f"[*] Chuyển sang Camera [{current_cam_idx}]...")
                cap.release()
                time.sleep(0.2)
                cap = open_camera(current_cam_idx, args.width, args.height)
                flash_msg = f"Da doi sang Camera [{current_cam_idx}]"
                flash_time = time.time()
            else:
                flash_msg = "Chi co 1 camera ket noi!"
                flash_time = time.time()

        elif action == "toggle_roi":
            show_workspace_roi = not show_workspace_roi
            status_str = "BAT" if show_workspace_roi else "TAT"
            flash_msg = f"Vung ROI: {status_str}"
            flash_time = time.time()
            print(f"[*] Hiển thị Vùng Làm Việc An Toàn ROI: {status_str}")

        elif action == "quit":
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
