#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dobot Magician Live Digital Twin Server (Bản sao số 3D thời gian thực)
Hỗ trợ đầy đủ: Đọc tọa độ thời gian thực, gửi lệnh PTP di chuyển XYZ và điều khiển giác hút.
"""

import os
import sys
import time
import json
import struct
import threading
import glob
import math
import subprocess
from pathlib import Path

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.gen
import tornado.iostream

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[-] Cần thư viện pyserial: pip install pyserial")
    sys.exit(1)

# Import các phân hệ Web Studio (Vision, Dataset, Trainer)
try:
    from web_vision_engine import WebVisionEngine
    from web_dataset_manager import (
        get_dataset_stats, save_captured_frame, delete_captured_image,
        add_new_class, get_recent_captures, DATASET_RAW_DIR
    )
    from web_trainer import web_trainer, COLAB_ZIP_PATH, MODELS_DIR
    try:
        from kaggle_trainer import kaggle_trainer
    except Exception as e_k:
        kaggle_trainer = None
        print(f"[!] Cảnh báo nạp module Kaggle Trainer: {e_k}")
    HAS_WEB_STUDIO = True
except Exception as e:
    HAS_WEB_STUDIO = False
    kaggle_trainer = None
    print(f"[!] Cảnh báo nạp module Web Studio: {e}")


ALARM_DICT = {
    0x00: "Lỗi khởi động lại hệ thống (Reset Alarm)",
    0x01: "Lệnh giao thức không hợp lệ (Undefined Instruction)",
    0x02: "Lỗi bộ nhớ lưu trữ (File System Error)",
    0x10: "Lỗi quy hoạch quỹ đạo (Planning Error)",
    0x11: "Lỗi giải động học nghịch / Vượt tầm với hoặc điểm kỳ dị (IK Singularity Error)",
    0x12: "Lỗi vượt giới hạn tọa độ chuyển động (Planning Limit Error)",
    0x20: "Lỗi thực thi động học (Kinematics Motion Error)",
    0x21: "Lỗi hành trình Khớp 1 (Joint 1 Limit)",
    0x22: "Lỗi hành trình Khớp 2 (Joint 2 Limit)",
    0x23: "Lỗi hành trình Khớp 3 (Joint 3 Limit)",
    0x24: "Lỗi hành trình Khớp 4 (Joint 4 Limit)",
    0x30: "Lỗi quá tốc độ chuyển động (Overspeed Alarm)",
    0x40: "Lỗi cảm biến công tắc hành trình (Sensor/Limit Switch Alarm)",
}

# --- CẤU HÌNH HỆ THỐNG RAY TRƯỢT DOBOT (SLIDING RAIL KIT 1000mm) ---
RAIL_INDEX = 0             # Stepper 1 = index 0
PULSES_PER_MM = 80.0       # Chuẩn Pulley GT2 20T: 80 xung = 1 mm
RAIL_MAX_MM = 1000.0       # Hành trình ray tối đa 1000 mm
DEFAULT_SPEED_MM_S = 40.0  # Vận tốc ray tiêu chuẩn 40 mm/s
SWITCH_PIN = 14            # Cảm biến công tắc hành trình GP2 (EIO 14, Chân 3)

RAIL_STATE_FILE = BASE_DIR / ".rail_state.json"
WORKSPACE_SAFETY_FILE = BASE_DIR / "workspace_safety.json"


class DobotController:
    def __init__(self):
        self.ser = None
        self.port = None
        self.lock = threading.Lock()
        self.connected = False
        self.buf = bytearray()
        self.cached_alarms = []
        self.last_pose = None
        self.alarm_poll_counter = 0

        # Khởi tạo trạng thái ray trượt và vùng an toàn
        self.is_rail_mode = True
        self.rail_current_pos = self._load_rail_state()
        self.rail_switch_active = False
        self.rail_is_homing = False
        self.rail_is_moving = False
        self.rail_homed = False
        self.rail_lock = threading.Lock()
        self.stop_requested = False
        self.last_reconnect_time = 0.0
        self.rail_motion = {"active": False, "start_time": 0.0, "duration": 0.0, "start_pos": 0.0, "target_pos": 0.0}
        self.safety_limits = self._load_safety_limits()

    def _load_rail_state(self):
        if RAIL_STATE_FILE.exists():
            try:
                with open(RAIL_STATE_FILE, "r", encoding="utf-8") as f:
                    return float(json.load(f).get("current_pos", 0.0))
            except Exception:
                pass
        return 0.0

    def _save_rail_state(self, pos):
        self.rail_current_pos = max(0.0, min(float(RAIL_MAX_MM), float(pos)))
        try:
            with open(RAIL_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({"current_pos": self.rail_current_pos, "updated_at": time.time()}, f, indent=4)
        except Exception:
            pass

    def _load_safety_limits(self):
        default_limits = {
            "z_min_standalone": -65.0,
            "z_min_rail": -180.0,
            "z_max": 165.0,
            "safe_travel_z": 30.0,
            "r_min": 140.0,
            "r_max": 330.0
        }
        if WORKSPACE_SAFETY_FILE.exists():
            try:
                with open(WORKSPACE_SAFETY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_limits.update(data)
            except Exception:
                pass
        return default_limits

    def update_safety_limits(self, new_limits: dict):
        for k in ["z_min_standalone", "z_min_rail", "z_max", "safe_travel_z", "r_min", "r_max"]:
            if k in new_limits:
                try:
                    self.safety_limits[k] = float(new_limits[k])
                except (ValueError, TypeError):
                    pass
        try:
            with open(WORKSPACE_SAFETY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.safety_limits, f, indent=4)
        except Exception as e:
            print(f"[-] Lỗi ghi file cấu hình an toàn: {e}")
        return self.safety_limits

    def auto_detect_port(self):
        # Ưu tiên các cổng USB có CP2102, CH340, FTDI
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = f"{p.description} {p.manufacturer} {p.hwid}".lower()
            if any(k in desc for k in ["cp210", "silicon", "ch340", "ch341", "ftdi", "usb serial"]):
                return p.device
        if ports:
            return ports[0].device
        devs = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        if devs:
            return devs[-1] # Lấy cổng mới nhất
        return None

    def connect(self, port=None):
        with self.lock:
            if self.connected and self.ser and self.ser.is_open:
                return True
            now = time.time()
            if now - self.last_reconnect_time < 2.0:
                return False
            self.last_reconnect_time = now
            target_port = port or self.auto_detect_port()
            if not target_port:
                self.connected = False
                return False
            self.port = target_port
            try:
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=115200,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.2
                )
                self.ser.setDTR(True)
                self.ser.setRTS(True)
                time.sleep(0.2)
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self.buf.clear()

                # 1. Xóa cờ lỗi phần cứng
                self._send_raw_cmd(id=20, ctrl=1)

                # 2. Xóa hàng đợi lệnh cũ và kích hoạt thực thi
                self._send_raw_cmd(id=245, ctrl=1) # SetQueuedCmdClear (ID 245)
                self._send_raw_cmd(id=240, ctrl=1) # SetQueuedCmdStartExec (ID 240)

                # 3. THIẾT LẬP THÔNG SỐ VẬN TỐC & GIA TỐC PTP (Bắt buộc để robot di chuyển)
                self._send_raw_cmd(id=80, ctrl=1, params=struct.pack('<8f', *([200.0]*8)))
                self._send_raw_cmd(id=81, ctrl=1, params=struct.pack('<4f', 200.0, 200.0, 200.0, 200.0))
                self._send_raw_cmd(id=83, ctrl=1, params=struct.pack('<2f', 50.0, 50.0))

                # 4. CẤU HÌNH CHÂN CÔNG TẮC HÀNH TRÌNH GP2 (EIO 14) THÀNH DIGITAL INPUT (ID 131)
                # address=14 (SWITCH_PIN), mode=4 (DI), isQueued=0
                self._send_raw_cmd(id=131, ctrl=1, params=bytes([SWITCH_PIN, 4, 0]))

                self.connected = True
                print(f"[+] Kết nối thành công với Dobot tại cổng: {self.port} (Đã bật EIO {SWITCH_PIN} làm cữ hành trình)")
                return True
            except Exception as e:
                print(f"[-] Không thể kết nối Dobot tại {self.port}: {e}")
                self.connected = False
                if self.ser:
                    try:
                        self.ser.close()
                    except Exception:
                        pass
                self.ser = None
                return False

    def disconnect(self):
        with self.lock:
            self.connected = False
            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
            self.port = None
            print("[+] Đã ngắt kết nối Dobot Magician.")
            return True

    def _calc_checksum(self, payload: bytes) -> int:
        return (0x100 - (sum(payload) % 0x100)) % 0x100

    def _send_raw_cmd(self, id: int, ctrl: int, params: bytes = b""):
        if not self.ser or not self.ser.is_open:
            return
        length = 2 + len(params)
        payload = bytes([id, ctrl]) + params
        checksum = self._calc_checksum(payload)
        packet = bytes([0xAA, 0xAA, length]) + payload + bytes([checksum])
        self.ser.write(packet)
        self.ser.flush()

    def _read_response(self, expected_id=10, timeout=0.1):
        if not self.ser or not self.ser.is_open:
            return None, None
        start = time.time()
        while time.time() - start < timeout:
            if self.ser.in_waiting > 0:
                self.buf.extend(self.ser.read(self.ser.in_waiting))
            while True:
                idx = self.buf.find(b"\xAA\xAA")
                if idx == -1:
                    self.buf.clear()
                    break
                if len(self.buf) < idx + 4:
                    break
                length = self.buf[idx + 2]
                total_packet_len = 3 + length + 1
                if len(self.buf) < idx + total_packet_len:
                    break
                packet = self.buf[idx : idx + total_packet_len]
                self.buf = self.buf[idx + total_packet_len :]
                resp_id = packet[3]
                resp_params = packet[5:-1]
                if expected_id is None or resp_id == expected_id:
                    return resp_id, resp_params
            time.sleep(0.005)
        return None, None

    def get_pose(self):
        with self.lock:
            if not self.connected or not self.ser or not self.ser.is_open:
                return None
            try:
                self.ser.reset_input_buffer()
                self._send_raw_cmd(id=10, ctrl=0) # GetPose: AA AA 02 0A 00 F6
                resp_id, params = self._read_response(expected_id=10, timeout=0.08)
                if params and len(params) >= 32:
                    x, y, z, r, j1, j2, j3, j4 = struct.unpack("<8f", params[:32])
                    pose = {
                        "x": round(x, 2), "y": round(y, 2), "z": round(z, 2), "r": round(r, 2),
                        "j1": round(j1, 2), "j2": round(j2, 2), "j3": round(j3, 2), "j4": round(j4, 2)
                    }
                    self.last_pose = pose
                    return pose
            except Exception as e:
                self.connected = False
                if self.ser:
                    try:
                        self.ser.close()
                    except Exception:
                        pass
                self.ser = None
                return None
        return None

    def get_alarms(self):
        """Đọc và giải mã danh sách cờ lỗi hiện tại từ Dobot (ID 20, Ctrl=0)"""
        with self.lock:
            if not self.connected:
                return self.cached_alarms
            try:
                self._send_raw_cmd(id=20, ctrl=0)
                resp_id, params = self._read_response(expected_id=20, timeout=0.1)
                if params:
                    active = []
                    for byte_idx, b in enumerate(params):
                        for bit_idx in range(8):
                            if (b >> bit_idx) & 1:
                                code = byte_idx * 8 + bit_idx
                                desc = ALARM_DICT.get(code, f"Mã lỗi 0x{code:02X}")
                                active.append({"code": code, "hex": f"0x{code:02X}", "desc": desc})
                    self.cached_alarms = active
                    return active
            except Exception:
                pass
        return self.cached_alarms

    def move_to_xyz(self, x, y, z, r, mode=1):
        """
        Gửi lệnh di chuyển PTP tới tọa độ Cartesian (X, Y, Z, R)
        mode=1: MOVJ_XYZ (nội suy góc khớp - chống kẹt điểm kỳ dị)
        mode=2: MOVL_XYZ (chuyển động thẳng)
        """
        with self.lock:
            if not self.connected:
                self.connect()
            if self.connected:
                # Đảm bảo hàng đợi đang chạy
                self._send_raw_cmd(id=240, ctrl=1)
                
                # ID 84: SetPTPCmd, ctrl=3 (Queued write)
                params = bytes([mode]) + struct.pack("<4f", float(x), float(y), float(z), float(r))
                self._send_raw_cmd(id=84, ctrl=3, params=params)
                print(f"[+] ĐÃ GỬI LỆNH DI CHUYỂN PTP (mode={mode}): X={x:.1f}, Y={y:.1f}, Z={z:.1f}, R={r:.1f}")
                return True
        return False

    def move_relative(self, dx, dy, dz, dr):
        """
        Di chuyển tương đối (JOG) an toàn:
        Tính toán tọa độ đích tuyệt đối từ vị trí hiện tại và dùng PTPMOVJXYZ (mode=1)
        Hoàn toàn miễn nhiễm với điểm kỳ dị IK, ngăn chặn tuyệt đối lỗi đèn đỏ!
        """
        cur = self.get_pose() or self.last_pose
        if not cur:
            return False, "Không đọc được tọa độ hiện tại của robot"

        target_x = cur["x"] + dx
        target_y = cur["y"] + dy
        target_z = cur["z"] + dz
        target_r = cur["r"] + dr

        # Kiểm tra giới hạn an toàn vùng làm việc của Dobot Magician (hỗ trợ Ray trượt)
        r_horiz = math.hypot(target_x, target_y)
        r_min = self.safety_limits.get("r_min", 140.0)
        r_max = self.safety_limits.get("r_max", 330.0)
        z_min_key = "z_min_rail" if self.is_rail_mode else "z_min_standalone"
        z_min_limit = float(self.safety_limits.get(z_min_key, -180.0 if self.is_rail_mode else -65.0))
        z_max_limit = float(self.safety_limits.get("z_max", 165.0))

        if r_horiz < r_min:
            return False, f"⚠️ Quá gần chân robot ({r_horiz:.1f}mm < {r_min:.1f}mm)! Dừng để tránh va chạm."
        if r_horiz > r_max:
            return False, f"⚠️ Vượt quá tầm với tối đa ({r_horiz:.1f}mm > {r_max:.1f}mm)!"
        if target_z < z_min_limit:
            return False, f"⚠️ Độ cao quá thấp ({target_z - 59.5:.1f}mm < {z_min_limit - 59.5:.1f}mm)! Nguy cơ đâm mặt bàn/ray."
        if target_z > z_max_limit:
            return False, f"⚠️ Vượt quá độ cao tối đa ({target_z - 59.5:.1f}mm > {z_max_limit - 59.5:.1f}mm)!"

        ok = self.move_to_xyz(target_x, target_y, target_z, target_r, mode=1)
        if ok:
            return True, f"⚡ Jog tới: X={target_x:.1f}, Y={target_y:.1f}, Z_đầu_hút={target_z - 59.5:.1f} mm"
        return False, "Không thể gửi lệnh tới robot"

    def move_joint(self, j1, j2, j3, j4, mode=4):
        """
        Di chuyển tới các góc khớp tuyệt đối (J1, J2, J3, J4 theo độ)
        mode=4: MOVJ_ANGLE
        """
        with self.lock:
            if not self.connected:
                self.connect()
            if self.connected:
                self._send_raw_cmd(id=240, ctrl=1)
                params = bytes([mode]) + struct.pack("<4f", float(j1), float(j2), float(j3), float(j4))
                self._send_raw_cmd(id=84, ctrl=3, params=params)
                print(f"[+] ĐÃ GỬI LỆNH DI CHUYỂN GÓC KHỚP: J1={j1:.1f}°, J2={j2:.1f}°, J3={j3:.1f}°, J4={j4:.1f}°")
                return True
        return False

    def emergency_stop(self):
        """
        Dừng khẩn cấp & Khôi phục: Dừng thực thi (242) + Xóa Queue (245) + Xóa Lỗi (20) + Mở lại Queue (240)
        """
        with self.lock:
            if self.connected:
                self._send_raw_cmd(id=242, ctrl=1) # SetQueuedCmdForceStopExec (ID 242)
                self._send_raw_cmd(id=245, ctrl=1) # SetQueuedCmdClear (ID 245)
                self._send_raw_cmd(id=20, ctrl=1)  # ClearAlarm (ID 20, Ctrl 1)
                self._send_raw_cmd(id=240, ctrl=1) # SetQueuedCmdStartExec (ID 240)
                self.cached_alarms = []
                print("[!] ĐÃ DỪNG KHẨN CẤP & XÓA HÀNG ĐỢI LỆNH")
                return True
        return False

    def clear_alarms(self):
        """
        Xóa toàn bộ cờ lỗi và mở lại hàng đợi lệnh bị đóng băng:
        1. ID 20, Ctrl=1: ClearAllAlarmsState
        2. ID 245, Ctrl=1: SetQueuedCmdClear (Xóa sạch lệnh đang kẹt trong queue)
        3. ID 240, Ctrl=1: SetQueuedCmdStartExec (Kích hoạt lại thực thi lệnh)
        """
        with self.lock:
            if self.connected:
                self._send_raw_cmd(id=20, ctrl=1)
                self._send_raw_cmd(id=245, ctrl=1)
                self._send_raw_cmd(id=240, ctrl=1)
                self.cached_alarms = []
                print("[+] ĐÃ GỬI BỘ 3 LỆNH KHÔI PHỤC (ID 20 + 245 + 240): XÓA LỖI & MỞ KHÓA QUEUE")
                return True
        return False

    def home(self):
        """
        Đưa robot về gốc Home (SetHOMECmd, ID 31):
        1. Xóa cờ lỗi & kích hoạt queue (ID 20 + 245 + 240)
        2. Gửi lệnh Homing (ID 31, Ctrl 1)
        """
        with self.lock:
            if not self.connected:
                self.connect()
            if self.connected:
                self._send_raw_cmd(id=20, ctrl=1)
                self._send_raw_cmd(id=245, ctrl=1)
                self._send_raw_cmd(id=240, ctrl=1)
                params = struct.pack("<I", 0)
                self._send_raw_cmd(id=31, ctrl=1, params=params)
                self.cached_alarms = []
                print("[+] ĐÃ GỬI LỆNH HOMING (ID 31)")
                return True
        return False

    def move_safe_jump(self, target_x, target_y, target_z, target_r=0.0, safe_z=None):
        """
        Di chuyển an toàn dạng cổng (Safe Jump):
        1. Nhấc lên độ cao an toàn (Safe Z)
        2. Bay ngang tới (X_đích, Y_đích) ở độ cao Safe Z
        3. Hạ xuống (Z_đích)
        """
        with self.lock:
            if not self.connected:
                self.connect()
            if self.connected:
                # Đọc vị trí hiện tại
                self.ser.reset_input_buffer()
                self._send_raw_cmd(id=10, ctrl=0)
                _, params = self._read_response(expected_id=10, timeout=0.15)
                if params and len(params) >= 16:
                    cur_x, cur_y, cur_z, cur_r = struct.unpack("<4f", params[:16])
                else:
                    cur_x, cur_y, cur_z, cur_r = target_x, target_y, target_z, target_r

                if safe_z is None:
                    safe_flange_z = max(cur_z, float(target_z)) + 25.0
                    safe_flange_z = min(140.0, max(safe_flange_z, 90.0))
                else:
                    safe_flange_z = float(safe_z)

                self._send_raw_cmd(id=240, ctrl=1)
                # 1. Nhấc lên (mode 1: MOVJ)
                self._send_raw_cmd(id=84, ctrl=3, params=bytes([1]) + struct.pack("<4f", float(cur_x), float(cur_y), float(safe_flange_z), float(cur_r)))
                # 2. Bay ngang (mode 1: MOVJ)
                self._send_raw_cmd(id=84, ctrl=3, params=bytes([1]) + struct.pack("<4f", float(target_x), float(target_y), float(safe_flange_z), float(target_r)))
                # 3. Hạ xuống (mode 1: MOVJ)
                self._send_raw_cmd(id=84, ctrl=3, params=bytes([1]) + struct.pack("<4f", float(target_x), float(target_y), float(target_z), float(target_r)))
                print(f"[+] ĐÃ GỬI LỆNH SAFE JUMP: Đích X={target_x:.1f}, Y={target_y:.1f}, Z={target_z:.1f} (Safe Z={safe_flange_z:.1f})")
                return True
        return False

    def set_suction(self, enable: bool):
        with self.lock:
            if not self.connected:
                self.connect()
            if self.connected:
                self._send_raw_cmd(id=240, ctrl=1)
                # ID 62: SetEndEffectorSuctionCup, ctrl=3 (Queued)
                params = bytes([1, 1 if enable else 0])
                self._send_raw_cmd(id=62, ctrl=3, params=params)
                # Gửi thêm bản immediate để tác động tức thì
                self._send_raw_cmd(id=62, ctrl=1, params=params)
                print(f"[+] Giác hút: {'BẬT' if enable else 'TẮT'}")

    # =========================================================================
    # CÁC HÀM ĐIỀU KHIỂN HỆ THỐNG RAY TRƯỢT DOBOT (SLIDING RAIL KIT)
    # =========================================================================
    def get_rail_switch(self) -> bool:
        """Đọc cảm biến cữ hành trình GP2 EIO 14 (True = Chạm cữ, False = Nhả)"""
        with self.lock:
            if not self.connected or not self.ser or not self.ser.is_open:
                return self.rail_switch_active
            try:
                self._send_raw_cmd(id=133, ctrl=0, params=bytes([SWITCH_PIN]))
                rid, par = self._read_response(expected_id=133, timeout=0.08)
                if par and len(par) >= 2 and par[0] == SWITCH_PIN:
                    self.rail_switch_active = (par[1] == 1)
                    return self.rail_switch_active
            except Exception:
                pass
        return self.rail_switch_active

    def _stop_stepper_pulses(self):
        """Chỉ dừng xung động cơ bước mà KHÔNG gán cờ stop_requested = True"""
        with self.lock:
            if self.connected:
                params = struct.pack("<B B i I", RAIL_INDEX, 0, 0, 0)
                self._send_raw_cmd(id=20, ctrl=1)
                self._send_raw_cmd(id=245, ctrl=1)
                self._send_raw_cmd(id=240, ctrl=1)
                self._send_raw_cmd(id=136, ctrl=3, params=params)
                self._send_raw_cmd(id=240, ctrl=1)

    def rail_stop(self):
        """Dừng khẩn cấp động cơ ray trượt do người dùng yêu cầu"""
        self.stop_requested = True
        self._stop_stepper_pulses()
        self.rail_is_moving = False
        self.rail_is_homing = False
        self.rail_motion["active"] = False
        self._save_rail_state(self.rail_current_pos)
        print("[!] ĐÃ DỪNG KHẨN CẤP ĐỘNG CƠ RAY TRƯỢT")
        return True

    def rail_jog(self, dist_mm: float, speed_mm_s: float = DEFAULT_SPEED_MM_S):
        """
        Di chuyển ray tương đối dist_mm với tốc độ speed_mm_s (mm/s)
        dist_mm > 0: Chạy ra xa switch (tăng L)
        dist_mm < 0: Chạy về hướng switch (giảm L)
        """
        with self.rail_lock:
            target_pos = max(0.0, min(RAIL_MAX_MM, self.rail_current_pos + float(dist_mm)))
            clamped_dist = target_pos - self.rail_current_pos
            if abs(clamped_dist) < 0.1:
                return True, f"⚠️ Ray đã ở giới hạn biên ({self.rail_current_pos:.1f} mm), không thể di chuyển thêm!"

            self.stop_requested = False
            self.rail_is_moving = True
            pulses = int(abs(clamped_dist) * PULSES_PER_MM)
            safe_speed = max(5.0, min(80.0, float(speed_mm_s)))
            speed_pulses = int(safe_speed * PULSES_PER_MM)
            dir_speed = -speed_pulses if clamped_dist >= 0 else speed_pulses

            if clamped_dist < 0 and self.get_rail_switch():
                self.rail_is_moving = False
                return False, "⚠️ Công tắc hành trình đang chạm, không thể lùi thêm!"

            if self.connected:
                with self.lock:
                    self._send_raw_cmd(id=240, ctrl=1)
                    params = struct.pack("<B B i I", RAIL_INDEX, 1, dir_speed, pulses)
                    self._send_raw_cmd(id=136, ctrl=3, params=params)
                    self._send_raw_cmd(id=240, ctrl=1)

            t_duration = pulses / float(speed_pulses)
            t0 = time.time()
            interrupted = False
            start_p = self.rail_current_pos
            sign = 1 if clamped_dist >= 0 else -1

            while time.time() - t0 < t_duration:
                if self.stop_requested:
                    self._stop_stepper_pulses()
                    interrupted = True
                    break
                elapsed = time.time() - t0
                fraction = min(1.0, elapsed / t_duration)
                self.rail_current_pos = max(0.0, min(RAIL_MAX_MM, start_p + sign * fraction * abs(clamped_dist)))
                if clamped_dist < 0 and self.connected and self.get_rail_switch():
                    self._stop_stepper_pulses()
                    self.rail_current_pos = 0.0
                    self._save_rail_state(0.0)
                    interrupted = True
                    break
                time.sleep(0.04)

            if not interrupted:
                self.rail_current_pos = max(0.0, min(RAIL_MAX_MM, start_p + clamped_dist))
                self._save_rail_state(self.rail_current_pos)
            else:
                self._save_rail_state(self.rail_current_pos)
                self.rail_is_moving = False
                return False, f"🛑 Đã dừng ray tại L = {self.rail_current_pos:.1f} mm"

            self.rail_is_moving = False
            return True, f"✅ Ray đã tới vị trí L = {self.rail_current_pos:.1f} mm"

    def rail_move_to(self, target_mm: float, speed_mm_s: float = DEFAULT_SPEED_MM_S):
        """Di chuyển ray tới tọa độ tuyệt đối target_mm (0.0 -> 1000.0 mm)"""
        target_mm = max(0.0, min(RAIL_MAX_MM, float(target_mm)))
        dist_mm = target_mm - self.rail_current_pos
        return self.rail_jog(dist_mm, speed_mm_s)

    def rail_home(self):
        """
        Dò gốc chuẩn xác cho ray trượt (4 giai đoạn an toàn theo Dobot-Fablab):
        1. Nhả switch nếu lúc bắt đầu đang bị đè (chạy ra xa switch)
        2. Coarse search về hướng switch (25 mm/s)
        3. Fine search nhả switch xác định điểm 0.0mm (8 mm/s)
        4. Thoát cữ an toàn (Retreat): nhích ra 5.0mm để giải phóng hoàn toàn công tắc,
           đảm bảo không bị kẹt hay chạm cữ cơ học sau khi về gốc.
        Hỗ trợ ngắt dừng khẩn cấp tức thời (self.stop_requested).
        """
        with self.rail_lock:
            self.stop_requested = False
            self.rail_is_moving = True
            self.rail_is_homing = True

            if not self.connected:
                duration = max(1.0, self.rail_current_pos / 35.0)
                time.sleep(duration + 0.1)
                retreat_mm = 5.0
                self.rail_current_pos = retreat_mm
                self.rail_switch_active = False
                self.rail_homed = True
                self.rail_is_moving = False
                self.rail_is_homing = False
                self._save_rail_state(retreat_mm)
                return True, f"🎉 [Mô phỏng] Homing ray trượt thành công! Đã thoát cữ ra L = {retreat_mm:.1f} mm."

            with self.lock:
                self._send_raw_cmd(20, 1)
                self._send_raw_cmd(245, 1)
                self._send_raw_cmd(240, 1)

            if self.stop_requested:
                self.rail_is_moving = False
                self.rail_is_homing = False
                return False, "🛑 Đã hủy Homing ray trượt do người dùng nhấn Dừng!"

            # 1. Nhả switch nếu lúc bắt đầu đang bị đè (chạy ra xa switch)
            if self.get_rail_switch():
                print("[*] Cữ đang chạm, nhích ra xa trước...")
                release_speed = int(8.0 * PULSES_PER_MM)
                release_pulses = int(12.0 * PULSES_PER_MM)
                params = struct.pack("<B B i I", RAIL_INDEX, 1, -release_speed, release_pulses)
                with self.lock:
                    self._send_raw_cmd(136, 3, params=params)
                    self._send_raw_cmd(240, 1)
                t_end = time.time() + (release_pulses / release_speed)
                while time.time() < t_end:
                    if self.stop_requested:
                        self._stop_stepper_pulses()
                        self.rail_is_moving = False
                        self.rail_is_homing = False
                        return False, "🛑 Đã hủy Homing ray trượt do người dùng nhấn Dừng!"
                    if not self.get_rail_switch():
                        break
                    time.sleep(0.02)
                self._stop_stepper_pulses()
                time.sleep(0.2)

            if self.stop_requested:
                self.rail_is_moving = False
                self.rail_is_homing = False
                return False, "🛑 Đã hủy Homing ray trượt do người dùng nhấn Dừng!"

            # 2. Dò cữ bước ngắn êm ái (bước 4.0mm, tốc độ 10 mm/s chống va đập cơ khí & mất bước)
            print("[*] Dò cữ bước ngắn êm ái (bước 4.0mm, tốc độ 10 mm/s về hướng switch)...")
            step_mm = 4.0
            step_pulses = int(step_mm * PULSES_PER_MM)
            step_speed = int(10.0 * PULSES_PER_MM)
            params = struct.pack("<B B i I", RAIL_INDEX, 1, step_speed, step_pulses)

            found = False
            max_steps = int(RAIL_MAX_MM / step_mm) + 30
            for step_idx in range(max_steps):
                if self.stop_requested:
                    self._stop_stepper_pulses()
                    self.rail_is_moving = False
                    self.rail_is_homing = False
                    return False, "🛑 Đã hủy Homing ray trượt do người dùng nhấn Dừng!"
                if self.get_rail_switch():
                    found = True
                    break
                with self.lock:
                    self._send_raw_cmd(136, 3, params=params)
                    self._send_raw_cmd(240, 1)
                t_start = time.time()
                t_duration = step_pulses / step_speed
                while time.time() - t_start < t_duration:
                    if self.stop_requested:
                        self._stop_stepper_pulses()
                        self.rail_is_moving = False
                        self.rail_is_homing = False
                        return False, "🛑 Đã hủy Homing ray trượt do người dùng nhấn Dừng!"
                    self.rail_current_pos = max(0.0, self.rail_current_pos - (10.0 * 0.02))
                    if self.get_rail_switch():
                        self._stop_stepper_pulses()
                        found = True
                        break
                    time.sleep(0.015)
                if found:
                    break

            if self.stop_requested:
                self._stop_stepper_pulses()
                self.rail_is_moving = False
                self.rail_is_homing = False
                return False, "🛑 Đã hủy Homing ray trượt do người dùng nhấn Dừng!"

            self._stop_stepper_pulses()
            time.sleep(0.2)

            if not found and not self.get_rail_switch():
                self.rail_is_moving = False
                self.rail_is_homing = False
                return False, "⚠️ Không tìm thấy công tắc hành trình sau hành trình tối đa (1300mm)!"

            # Khi đã chạm cữ, thiết lập mốc 0.0mm tạm thời
            self.rail_current_pos = 0.0

            if self.stop_requested:
                self.rail_is_moving = False
                self.rail_is_homing = False
                return False, "🛑 Đã hủy Homing ray trượt do người dùng nhấn Dừng!"

            # 3. Fine search nhả cữ siêu mịn (bước 0.5mm, tốc độ 5 mm/s: dir_speed < 0)
            print("[*] Tinh chỉnh nhả cữ siêu mịn (bước 0.5mm, tốc độ 5 mm/s)...")
            fine_step = int(0.5 * PULSES_PER_MM)
            fine_speed = int(5.0 * PULSES_PER_MM)
            fine_params = struct.pack("<B B i I", RAIL_INDEX, 1, -fine_speed, fine_step)
            for _ in range(50):
                if self.stop_requested:
                    self._stop_stepper_pulses()
                    self.rail_is_moving = False
                    self.rail_is_homing = False
                    return False, "🛑 Đã hủy Homing ray trượt do người dùng nhấn Dừng!"
                if not self.get_rail_switch():
                    break
                with self.lock:
                    self._send_raw_cmd(136, 3, params=fine_params)
                    self._send_raw_cmd(240, 1)
                t_end = time.time() + (fine_step / fine_speed + 0.02)
                while time.time() < t_end:
                    if self.stop_requested:
                        self._stop_stepper_pulses()
                        self.rail_is_moving = False
                        self.rail_is_homing = False
                        return False, "🛑 Đã hủy Homing ray trượt do người dùng nhấn Dừng!"
                    time.sleep(0.01)

            if self.stop_requested:
                self._stop_stepper_pulses()
                self.rail_is_moving = False
                self.rail_is_homing = False
                return False, "🛑 Đã hủy Homing ray trượt do người dùng nhấn Dừng!"

            self._stop_stepper_pulses()
            time.sleep(0.2)

            # 4. Thoát cữ an toàn (Retreat): Nhích ra xa cữ 5.0mm (tốc độ 10 mm/s êm dịu)
            print("[*] Thoát cữ an toàn (+5.0mm) để giải phóng hoàn toàn công tắc...")
            self.stop_requested = False
            retreat_mm = 5.0
            retreat_pulses = int(retreat_mm * PULSES_PER_MM)
            retreat_speed = int(10.0 * PULSES_PER_MM)
            retreat_params = struct.pack("<B B i I", RAIL_INDEX, 1, -retreat_speed, retreat_pulses)
            with self.lock:
                self._send_raw_cmd(136, 3, params=retreat_params)
                self._send_raw_cmd(240, 1)
            t_start = time.time()
            t_duration = retreat_pulses / retreat_speed
            while time.time() - t_start < t_duration + 0.05:
                if self.stop_requested:
                    self._stop_stepper_pulses()
                    self.rail_is_moving = False
                    self.rail_is_homing = False
                    return False, "🛑 Đã hủy Homing ray trượt do người dùng nhấn Dừng!"
                fraction = min(1.0, (time.time() - t_start) / t_duration)
                self.rail_current_pos = round(fraction * retreat_mm, 1)
                time.sleep(0.02)

            self._stop_stepper_pulses()
            time.sleep(0.1)

            # Cập nhật tọa độ chuẩn: điểm 0.0mm là ngay mép nhả cữ, hiện tại ray đang ở 5.0mm
            self.rail_current_pos = retreat_mm
            self.rail_homed = True
            self._save_rail_state(self.rail_current_pos)
            self.rail_is_moving = False
            self.rail_is_homing = False
            print("=" * 70)
            print(f"🎉 [HOMING HOÀN TẤT] >>> Vị trí hiện tại: {self.rail_current_pos:.1f} mm (Đã thoát cữ an toàn)!")
            print("=" * 70)
            return True, f"🎉 Homing ray trượt thành công! Đã tự động thoát cữ ra L = {self.rail_current_pos:.1f} mm an toàn."

    def set_rail_mode(self, enabled: bool):
        self.is_rail_mode = bool(enabled)
        print(f"[+] Đã chuyển chế độ: {'Ray trượt 1000mm' if self.is_rail_mode else 'Để bàn độc lập'}")
        return self.is_rail_mode



robot = DobotController()
vision_engine = WebVisionEngine(robot_controller=robot) if HAS_WEB_STUDIO else None
connected_clients = set()


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.set_header("Pragma", "no-cache")
        self.set_header("Expires", "0")
        file_path = os.path.join(os.path.dirname(__file__), "dobot_visualizer.html")
        with open(file_path, "r", encoding="utf-8") as f:
            self.write(f.read())


class StaticFileHandler(tornado.web.RequestHandler):
    def get(self, filename):
        file_path = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(file_path):
            if filename.endswith(".js"):
                self.set_header("Content-Type", "application/javascript")
            elif filename.endswith(".ico"):
                self.set_header("Content-Type", "image/x-icon")
            elif filename.endswith(".png"):
                self.set_header("Content-Type", "image/png")
            with open(file_path, "rb") as f:
                self.write(f.read())
        else:
            self.set_status(404)


class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        connected_clients.add(self)
        print(f"[+] Web Client kết nối: {self.request.remote_ip} (Tổng: {len(connected_clients)})")

    def on_message(self, message):
        try:
            cmd = json.loads(message)
            action = cmd.get("action")
            if action == "clear_alarms":
                robot.clear_alarms()
                self.write_message(json.dumps({"type": "feedback", "msg": "✅ Đã xóa cờ lỗi & khôi phục hàng đợi lệnh Dobot!"}))
            elif action == "emergency_stop":
                robot.emergency_stop()
                self.write_message(json.dumps({"type": "feedback", "msg": "🛑 Đã Dừng Khẩn Cấp & Xóa Hàng Đợi"}))
            elif action == "home":
                ok = robot.home()
                if ok:
                    self.write_message(json.dumps({"type": "feedback", "msg": "🏠 Robot đang tự động chạy Homing về gốc tọa độ chuẩn..."}))
                else:
                    self.write_message(json.dumps({"type": "feedback", "msg": "❌ Không thể gửi lệnh Homing (Robot chưa kết nối)"}))
            elif action == "suction":
                val = bool(cmd.get("value", False))
                robot.set_suction(val)
                self.write_message(json.dumps({"type": "feedback", "msg": f"Giác hút: {'BẬT' if val else 'TẮT'}"}))
            elif action == "jog":
                axis = cmd.get("axis", "z").lower()
                step = float(cmd.get("step", 10.0))
                dx = step if axis == "x" else 0.0
                dy = step if axis == "y" else 0.0
                dz = step if axis == "z" else 0.0
                dr = step if axis == "r" else 0.0
                ok, msg = robot.move_relative(dx, dy, dz, dr)
                self.write_message(json.dumps({"type": "feedback", "msg": msg}))
            elif action == "move_xyz":
                x = float(cmd.get("x", 200))
                y = float(cmd.get("y", 0))
                z = float(cmd.get("z", 100))
                r = float(cmd.get("r", 0))
                mode = int(cmd.get("mode", 1))
                robot.move_to_xyz(x, y, z, r, mode=mode)
                self.write_message(json.dumps({"type": "feedback", "msg": f"🚀 Đang di chuyển tới X={x:.0f}, Y={y:.0f}, Z={z - 59.5:.0f}"}))
            elif action == "safe_jump":
                x = float(cmd.get("x", 200))
                y = float(cmd.get("y", 0))
                z = float(cmd.get("z", 100))
                r = float(cmd.get("r", 0))
                safe_z = cmd.get("safe_z", None)
                if safe_z is not None:
                    safe_z = float(safe_z)
                robot.move_safe_jump(x, y, z, r, safe_z=safe_z)
                self.write_message(json.dumps({"type": "feedback", "msg": f"📦 Đang Safe Jump tới X={x:.0f}, Y={y:.0f}, Z={z - 59.5:.0f}"}))
            elif action == "move_joint":
                j1 = float(cmd.get("j1", 0))
                j2 = float(cmd.get("j2", 0))
                j3 = float(cmd.get("j3", 0))
                j4 = float(cmd.get("j4", 0))
                mode = int(cmd.get("mode", 4))
                robot.move_joint(j1, j2, j3, j4, mode=mode)
                self.write_message(json.dumps({"type": "feedback", "msg": f"🔄 Đang xoay khớp: J1={j1:.1f}°, J2={j2:.1f}°, J3={j3:.1f}°"}))
            # --- CÁC LỆNH ĐIỀU KHIỂN RAY TRƯỢT & VÙNG AN TOÀN ---
            elif action == "rail_jog":
                dist = float(cmd.get("dist", 10.0))
                speed = float(cmd.get("speed", DEFAULT_SPEED_MM_S))
                def _do_jog():
                    ok, res_msg = robot.rail_jog(dist, speed)
                    for c in list(connected_clients):
                        try:
                            c.write_message(json.dumps({"type": "feedback", "msg": res_msg}))
                        except Exception:
                            pass
                threading.Thread(target=_do_jog, daemon=True).start()
                self.write_message(json.dumps({"type": "feedback", "msg": f"🛤️ Đang jog ray {dist:+.1f} mm..."}))
            elif action == "rail_move":
                pos = float(cmd.get("pos") if cmd.get("pos") is not None else cmd.get("l", 0.0))
                speed = float(cmd.get("speed", DEFAULT_SPEED_MM_S))
                def _do_move():
                    ok, res_msg = robot.rail_move_to(pos, speed)
                    for c in list(connected_clients):
                        try:
                            c.write_message(json.dumps({"type": "feedback", "msg": res_msg}))
                        except Exception:
                            pass
                threading.Thread(target=_do_move, daemon=True).start()
                self.write_message(json.dumps({"type": "feedback", "msg": f"🛤️ Ray trượt đang di chuyển tới L={pos:.1f} mm..."}))
            elif action == "rail_home":
                def _do_home():
                    ok, res_msg = robot.rail_home()
                    for c in list(connected_clients):
                        try:
                            c.write_message(json.dumps({"type": "feedback", "msg": res_msg}))
                        except Exception:
                            pass
                threading.Thread(target=_do_home, daemon=True).start()
                self.write_message(json.dumps({"type": "feedback", "msg": "🏠 Bắt đầu dò gốc Home cho ray trượt..."}))
            elif action == "rail_stop":
                ok = robot.rail_stop()
                self.write_message(json.dumps({"type": "feedback", "msg": "🛑 Đã phát lệnh dừng khẩn cấp ray trượt!"}))
            elif action == "set_rail_mode":
                val = bool(cmd.get("enabled", True))
                robot.set_rail_mode(val)
                self.write_message(json.dumps({"type": "feedback", "msg": f"Chế độ: {'Ray trượt 1000mm' if val else 'Để bàn độc lập'}"}))
            elif action == "update_safety_limits":
                limits = cmd.get("limits", {})
                robot.update_safety_limits(limits)
                self.write_message(json.dumps({"type": "feedback", "msg": "💾 Đã cập nhật & lưu thông số vùng an toàn!"}))
        except Exception as e:
            print("[-] Lỗi xử lý lệnh từ client:", e)

    def on_close(self):
        connected_clients.discard(self)
        print(f"[-] Web Client ngắt kết nối (Còn lại: {len(connected_clients)})")


class ApiCmdHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def options(self):
        self.set_status(204)
        self.finish()

    def get(self):
        pose = robot.get_pose() or robot.last_pose or {}
        self.write({
            "status": "ok",
            "pose": pose,
            "connected": robot.connected,
            "rail": {
                "mode": robot.is_rail_mode,
                "pos": robot.rail_current_pos,
                "switch": robot.rail_switch_active,
                "is_homing": robot.rail_is_homing,
                "is_moving": robot.rail_is_moving,
            },
            "safety": robot.safety_limits
        })

    def post(self):
        try:
            cmd = json.loads(self.request.body)
            action = cmd.get("action")
            if action == "move_xyz":
                x = float(cmd.get("x", 200))
                y = float(cmd.get("y", 0))
                z = float(cmd.get("z", 100))
                r = float(cmd.get("r", 0))
                mode = int(cmd.get("mode", 1))
                ok = robot.move_to_xyz(x, y, z, r, mode=mode)
                self.write({"status": "ok" if ok else "fail"})
            elif action == "safe_jump":
                x = float(cmd.get("x", 200))
                y = float(cmd.get("y", 0))
                z = float(cmd.get("z", 100))
                r = float(cmd.get("r", 0))
                safe_z = cmd.get("safe_z")
                if safe_z is not None:
                    safe_z = float(safe_z)
                ok = robot.move_safe_jump(x, y, z, r, safe_z=safe_z)
                self.write({"status": "ok" if ok else "fail"})
            elif action == "suction":
                val = bool(cmd.get("value", False))
                robot.set_suction(val)
                self.write({"status": "ok", "suction": val})
            elif action == "clear_alarms":
                robot.clear_alarms()
                self.write({"status": "ok"})
            elif action == "home":
                ok = robot.home()
                self.write({"status": "ok" if ok else "fail"})
            elif action == "rail_jog":
                dist = float(cmd.get("dist", 10.0) or cmd.get("delta", 0.0))
                speed = float(cmd.get("speed", DEFAULT_SPEED_MM_S))
                threading.Thread(target=robot.rail_jog, args=(dist, speed), daemon=True).start()
                self.write({"status": "ok", "msg": f"Đang jog ray {dist:+.1f} mm"})
            elif action == "rail_move":
                pos = float(cmd.get("pos", 0.0) or cmd.get("l", 0.0))
                speed = float(cmd.get("speed", DEFAULT_SPEED_MM_S))
                threading.Thread(target=robot.rail_move_to, args=(pos, speed), daemon=True).start()
                self.write({"status": "ok", "msg": f"Đang di chuyển ray tới L={pos:.1f} mm"})
            elif action == "rail_home":
                threading.Thread(target=robot.rail_home, daemon=True).start()
                self.write({"status": "ok", "msg": "Homing ray trượt đã bắt đầu"})
            elif action == "rail_stop":
                ok = robot.rail_stop()
                self.write({"status": "ok" if ok else "fail"})
            elif action == "set_rail_mode":
                val = bool(cmd.get("enabled", True))
                robot.set_rail_mode(val)
                self.write({"status": "ok", "is_rail_mode": robot.is_rail_mode})
            elif action == "update_safety_limits":
                limits = cmd.get("limits", {})
                updated = robot.update_safety_limits(limits)
                self.write({"status": "ok", "limits": updated})
            else:
                self.write({"status": "error", "msg": f"Unknown action: {action}"})
        except Exception as e:
            self.set_status(400)
            self.write({"status": "error", "error": str(e)})


class ApiWorkspaceSafetyHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def options(self):
        self.set_status(204)
        self.finish()

    def get(self):
        cur_pose = robot.get_pose() or robot.last_pose or {}
        self.write({
            "status": "ok",
            "is_rail_mode": robot.is_rail_mode,
            "rail_pos": round(robot.rail_current_pos, 1),
            "current_pose": cur_pose,
            "limits": robot.safety_limits
        })

    def post(self):
        try:
            data = json.loads(self.request.body)
            if "is_rail_mode" in data:
                robot.set_rail_mode(bool(data["is_rail_mode"]))
            if "limits" in data:
                robot.update_safety_limits(data["limits"])
            self.write({
                "status": "ok",
                "is_rail_mode": robot.is_rail_mode,
                "limits": robot.safety_limits,
                "message": "Cập nhật vùng an toàn thành công!"
            })
        except Exception as e:
            self.set_status(400)
            self.write({"status": "error", "error": str(e)})


class ApiRobotConnectHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body) if self.request.body else {}
            target_port = data.get("port", None)
            ok = robot.connect(port=target_port)
            if ok:
                self.write({"success": True, "connected": True, "port": robot.port, "message": f"Kết nối Dobot thành công ({robot.port})"})
            else:
                self.write({"success": False, "connected": False, "error": "Không tìm thấy Dobot Magician qua cổng USB. Vui lòng cắm cáp và bấm thử lại!"})
        except Exception as e:
            self.write({"success": False, "connected": False, "error": str(e)})


class ApiRobotDisconnectHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def post(self):
        robot.disconnect()
        self.write({"success": True, "connected": False, "message": "Đã ngắt kết nối Dobot"})


class ApiRobotPortsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        try:
            ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            ports = []
        self.write({"ports": ports, "connected": robot.connected, "current_port": robot.port})


poll_counter = 0

def poll_robot_pose():
    global poll_counter
    # 1. Cập nhật chuyển động ray trượt nội suy nếu đang di chuyển
    if robot.rail_motion.get("active", False):
        now = time.time()
        elapsed = now - robot.rail_motion["start_time"]
        dur = robot.rail_motion["duration"]
        if elapsed >= dur:
            robot.rail_motion["active"] = False
            robot.rail_is_moving = False
            robot._save_rail_state(robot.rail_motion["target_pos"])
        else:
            prog = min(1.0, max(0.0, elapsed / dur))
            interp = robot.rail_motion["start_pos"] + prog * (robot.rail_motion["target_pos"] - robot.rail_motion["start_pos"])
            robot.rail_current_pos = round(interp, 2)

    if not connected_clients:
        return

    poll_counter += 1
    # 2. Đọc trạng thái switch cữ hành trình định kỳ mỗi 20 chu kỳ (~1s) khi KHÔNG di chuyển ray
    if robot.connected and (poll_counter % 20 == 0):
        if not robot.rail_is_moving and not robot.rail_is_homing:
            robot.get_rail_switch()

    rail_telemetry = {
        "mode": robot.is_rail_mode,
        "pos": round(robot.rail_current_pos, 1),
        "switch": robot.rail_switch_active,
        "is_homing": robot.rail_is_homing,
        "is_moving": robot.rail_is_moving,
    }

    if robot.connected:
        # Nếu ray trượt đang chạy homing/jogging, hạn chế gửi GetPose liên tục để tránh nghẽn bus serial
        if robot.rail_is_moving or robot.rail_is_homing:
            pose = robot.last_pose
        else:
            pose = robot.get_pose()
        alarms = robot.cached_alarms
        if poll_counter % 10 == 0:
            if not robot.rail_is_moving and not robot.rail_is_homing:
                alarms = robot.get_alarms()
        has_alarm = bool(alarms and len(alarms) > 0)
        msg = json.dumps({
            "type": "pose",
            "connected": True,
            "port": robot.port,
            "data": pose or robot.last_pose,
            "alarms": alarms,
            "has_alarm": has_alarm,
            "rail": rail_telemetry,
            "safety": robot.safety_limits
        })
    else:
        # Nếu đang di chuyển ray hoặc homing (kể cả mô phỏng), gửi liên tục mỗi chu kỳ 50ms; nếu nghỉ thì gửi mỗi 20 chu kỳ (~1s)
        if not robot.rail_is_moving and not robot.rail_is_homing and (poll_counter % 20 != 0):
            return
        msg = json.dumps({
            "type": "pose",
            "connected": False,
            "port": "Chưa kết nối",
            "alarms": [],
            "has_alarm": False,
            "rail": rail_telemetry,
            "safety": robot.safety_limits
        })

    for client in list(connected_clients):
        try:
            client.write_message(msg)
        except Exception:
            connected_clients.discard(client)

        if HAS_WEB_STUDIO and poll_counter % 10 == 0:
            tr_stat = web_trainer.get_status()
            if tr_stat.get("status") in ("preparing", "training", "completed"):
                tr_msg = json.dumps({"type": "train_status", "data": tr_stat})
                for client in list(connected_clients):
                    try:
                        client.write_message(tr_msg)
                    except Exception:
                        pass


# ==============================================================================
# BỘ QUẢN LÝ TIẾN TRÌNH CÔNG CỤ CHUYÊN DỤNG (CAPTURE & AUTO SORT NATIVE TOOLS)
# ==============================================================================

class ToolProcessManager:
    """Quản lý các công cụ Native GUI độc lập (capture_from_camera.py, dobot_auto_sort.py)."""
    def __init__(self):
        self.proc = None
        self.active_tool = None
        self.lock = threading.Lock()

    def launch(self, tool_name, **kwargs):
        with self.lock:
            # Nếu tool cũ còn đang chạy
            if self.proc and self.proc.poll() is None:
                return {
                    "success": False,
                    "error": f"Công cụ '{self.active_tool}' đang chạy! Vui lòng dừng công cụ này trước để giải phóng camera.",
                    "active_tool": self.active_tool
                }

            cmd = [sys.executable]
            if tool_name == "capture":
                script = PROJECT_ROOT / "capture_from_camera.py"
                cmd.append(str(script))
                cls_name = kwargs.get("class_name", "cube_red")
                cmd.extend(["--class", str(cls_name)])
                cmd.extend(["--output", "dataset_raw"])
                if "cam_id" in kwargs and kwargs["cam_id"] is not None:
                    cmd.extend(["--camera", str(kwargs["cam_id"])])

            elif tool_name == "sort":
                script = BASE_DIR / "dobot_auto_sort.py"
                cmd.append(str(script))
                if "cam_id" in kwargs and kwargs["cam_id"] is not None:
                    cmd.extend(["--cam", str(kwargs["cam_id"])])
                if "model" in kwargs and kwargs["model"]:
                    cmd.extend(["--model", str(kwargs["model"])])

            elif tool_name == "calib":
                script = BASE_DIR / "calibrate_camera_to_dobot.py"
                cmd.append(str(script))
                if "cam_id" in kwargs and kwargs["cam_id"] is not None:
                    cmd.extend(["--cam", str(kwargs["cam_id"])])

            else:
                return {"success": False, "error": f"Không hỗ trợ công cụ '{tool_name}'"}

            try:
                creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
                self.proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), creationflags=creationflags)
                self.active_tool = tool_name
                print(f"[ToolManager] 🚀 Đã mở công cụ '{tool_name}' (PID: {self.proc.pid})")
                return {"success": True, "active_tool": tool_name, "pid": self.proc.pid}
            except Exception as e:
                print(f"[ToolManager] ❌ Lỗi khởi chạy: {e}")
                return {"success": False, "error": str(e)}

    def stop(self, tool_name=None):
        with self.lock:
            if not self.proc:
                self.proc = None
                self.active_tool = None
                return {"success": True, "message": "Không có công cụ nào đang chạy"}

            try:
                pid = self.proc.pid
                tool_label = self.active_tool
                if sys.platform == "win32":
                    # taskkill /F /T /PID tiêu diệt toàn bộ cây tiến trình (console window + python + opencv)
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
                else:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()

                print(f"[ToolManager] ⏹️ Đã dừng công cụ '{tool_label}' (PID: {pid}) và giải phóng Camera thành công!")
                self.proc = None
                self.active_tool = None
                return {"success": True, "message": "Đã đóng công cụ & giải phóng camera thành công"}
            except Exception as e:
                print(f"[ToolManager] ❌ Lỗi khi dừng công cụ: {e}")
                return {"success": False, "error": str(e)}

    def get_status(self):
        with self.lock:
            if self.proc:
                if self.proc.poll() is None:
                    return {"is_running": True, "active_tool": self.active_tool, "pid": self.proc.pid}
                else:
                    self.proc = None
                    self.active_tool = None
            return {"is_running": False, "active_tool": None}

tool_manager = ToolProcessManager()


class ApiToolLaunchHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body) if self.request.body else {}
            tool_name = data.get("tool", "capture")
            res = tool_manager.launch(tool_name, **data)
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiToolStopHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body) if self.request.body else {}
            tool_name = data.get("tool", None)
            res = tool_manager.stop(tool_name)
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiToolStatusHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        self.write(tool_manager.get_status())


# ==============================================================================
# BỘ XỬ LÝ VIDEO & WEB STUDIO APIS (CAMERA, DATASET, TRAINER, AUTO SORT)
# ==============================================================================

class VideoWsHandler(tornado.websocket.WebSocketHandler):
    """WebSocket stream camera frames (JPEG binary) - đáng tin cậy hơn MJPEG HTTP."""

    def check_origin(self, origin):
        return True  # Cho phép mọi origin

    def open(self):
        mode = self.get_argument("mode", "raw")
        self._mode = mode
        self._running = True
        tornado.ioloop.IOLoop.current().spawn_callback(self._push_frames)

    async def _push_frames(self):
        if not HAS_WEB_STUDIO or not vision_engine:
            return

        # 1. Gửi ngay khung hình hiện có đầu tiên để Client không bị trễ/màn hình đen
        try:
            _, initial_jpeg = vision_engine.get_jpeg_with_id(self._mode)
            if initial_jpeg and self._running:
                await self.write_message(initial_jpeg, binary=True)
        except Exception:
            pass

        # 2. Vòng lặp đẩy các khung hình mới liên tục (~30 FPS)
        last_id = -1
        while self._running:
            try:
                cur_id, jpeg = vision_engine.get_jpeg_with_id(self._mode)
                if jpeg and cur_id != last_id:
                    last_id = cur_id
                    await self.write_message(jpeg, binary=True)
                await tornado.gen.sleep(0.033)  # ~30 fps
            except tornado.websocket.WebSocketClosedError:
                break
            except Exception:
                break
        self._running = False

    def on_message(self, message):
        pass  # Không nhận message từ client

    def on_close(self):
        self._running = False


class ApiCameraHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def get(self):
        # Trả về ngay danh sách camera khả dụng mà không mở lại thiết bị đang quay
        if HAS_WEB_STUDIO and vision_engine:
            devices = vision_engine.get_camera_devices()
            status = vision_engine.get_status()
            active_cam = vision_engine.cam_id if devices else None
            is_cam_open = status.get("camera_online", False)
        else:
            devices = []
            active_cam = None
            is_cam_open = False

        self.write({
            "status": "ok",
            "success": True,
            "devices": devices,
            "available_cameras": devices,
            "active_cam": active_cam,
            "current_cam": active_cam,
            "camera_online": is_cam_open,
            "is_opened": is_cam_open
        })

    def post(self):
        try:
            data = json.loads(self.request.body) if self.request.body else {}
            if data.get("refresh", False) and HAS_WEB_STUDIO and vision_engine:
                # Quét lại danh sách camera
                cams = vision_engine.scan_cameras()
                self.write({"status": "ok", "success": True, "devices": cams, "available_cameras": cams})
            elif "cam_id" in data and HAS_WEB_STUDIO and vision_engine:
                ok = vision_engine.start_camera(int(data["cam_id"]))
                self.write({"status": "ok", "success": ok, "cam_id": vision_engine.cam_id})
            else:
                self.write({"status": "error", "success": False, "error": "Tham số không hợp lệ"})
        except Exception as e:
            self.write({"status": "error", "success": False, "error": str(e)})


class ApiDatasetStatsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        if HAS_WEB_STUDIO:
            self.write(get_dataset_stats())
        else:
            self.write({"classes": {}, "total_images": 0})


class ApiDatasetCaptureHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        if not HAS_WEB_STUDIO or not vision_engine:
            self.write({"success": False, "error": "Vision Engine chưa khởi động"})
            return

        try:
            data = json.loads(self.request.body)
            class_name = data.get("class_name", "cube_red")
            frame = vision_engine.get_raw_frame()
            if frame is None:
                self.write({"success": False, "error": "Chưa nhận được frame từ Camera"})
                return

            res = save_captured_frame(class_name, frame)
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiDatasetDeleteHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body)
            res = delete_captured_image(data.get("class_name", ""), data.get("filename", ""))
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiDatasetAddClassHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body)
            res = add_new_class(data.get("class_name", ""))
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiDatasetRecentHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        if HAS_WEB_STUDIO:
            self.write({"images": get_recent_captures(limit=16)})
        else:
            self.write({"images": []})


class DatasetImageHandler(tornado.web.RequestHandler):
    def get(self, path):
        full_path = os.path.join(str(DATASET_RAW_DIR), path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            self.set_header("Content-Type", "image/jpeg")
            with open(full_path, "rb") as f:
                self.write(f.read())
        else:
            self.set_status(404)


class ApiTrainStartHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        if not HAS_WEB_STUDIO:
            self.write({"success": False, "error": "Module huấn luyện chưa sẵn sàng"})
            return

        try:
            data = json.loads(self.request.body)
            model_name = data.get("model") or data.get("model_name", "yolov8n.pt")
            epochs = int(data.get("epochs", 30))
            batch = int(data.get("batch", 16))
            output_model_name = data.get("output_model_name") or data.get("output_name") or "best_trained.pt"
            res = web_trainer.start(base_model=model_name, epochs=epochs, batch=batch, output_model_name=output_model_name)
            res["status"] = "ok" if res.get("success") else "error"
            self.write(res)
        except Exception as e:
            self.write({"status": "error", "success": False, "error": str(e), "message": str(e)})


class ApiTrainStatusHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        if HAS_WEB_STUDIO:
            self.write(web_trainer.get_status())
        else:
            self.write({"status": "idle"})


class ApiTrainStopHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def post(self):
        if HAS_WEB_STUDIO:
            web_trainer.stop()
            self.write({"status": "ok", "success": True, "message": "Đã gửi lệnh dừng tiến trình huấn luyện thành công!"})
        else:
            self.write({"status": "error", "success": False, "message": "Chưa hỗ trợ"})


class ApiTrainExportColabHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    async def post(self):
        if HAS_WEB_STUDIO:
            loop = tornado.ioloop.IOLoop.current()
            res = await loop.run_in_executor(None, web_trainer.export_colab_zip)
            if res.get("success"):
                res["status"] = "ok"
                res["download_url"] = "/api/train/download_zip"
                res["zip_name"] = res.get("filename", "yolo_dataset.zip")
            else:
                res["status"] = "error"
                res["message"] = res.get("error", "Lỗi tạo file zip")
            self.write(res)
        else:
            self.write({"status": "error", "success": False, "message": "Chưa hỗ trợ"})


class ApiTrainDownloadZipHandler(tornado.web.RequestHandler):
    def get(self):
        if COLAB_ZIP_PATH.exists():
            self.set_header('Content-Type', 'application/zip')
            self.set_header('Content-Disposition', 'attachment; filename="yolo_dataset.zip"')
            with open(COLAB_ZIP_PATH, 'rb') as f:
                self.write(f.read())
        else:
            self.set_status(404)
            self.write("Chưa có file zip. Hãy bấm xuất gói trước.")


class ApiKaggleCredsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def get(self):
        if kaggle_trainer:
            self.write(kaggle_trainer.get_credentials())
        else:
            self.write({"configured": False, "error": "Module Kaggle chưa sẵn sàng"})

    def post(self):
        if not kaggle_trainer:
            self.write({"success": False, "error": "Module Kaggle chưa sẵn sàng"})
            return
        try:
            data = json.loads(self.request.body)
            username = data.get("username", "")
            key = data.get("key", "")
            res = kaggle_trainer.save_credentials(username, key)
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiKaggleStartHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        if not kaggle_trainer:
            self.write({"success": False, "error": "Module Kaggle chưa sẵn sàng"})
            return
        try:
            data = json.loads(self.request.body) if self.request.body else {}
            model_name = data.get("model") or data.get("model_name", "yolo11n.pt")
            epochs = int(data.get("epochs", 30))
            batch = int(data.get("batch", 16))
            output_model_name = data.get("output_model_name") or data.get("output_name") or "best_trained.pt"
            res = kaggle_trainer.start(base_model=model_name, epochs=epochs, batch=batch, output_model_name=output_model_name)
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiKaggleStatusHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        if kaggle_trainer:
            self.write(kaggle_trainer.get_status())
        else:
            self.write({"status": "idle"})


class ApiKaggleStopHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def post(self):
        if kaggle_trainer:
            kaggle_trainer.stop()
            self.write({"success": True, "message": "Đã gửi lệnh dừng tiến trình Cloud GPU!"})
        else:
            self.write({"success": False, "error": "Chưa hỗ trợ"})



class ApiVisionStatusHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        if HAS_WEB_STUDIO and vision_engine:
            self.write(vision_engine.get_status())
        else:
            self.write({"camera_online": False})


class ApiVisionPickHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        if not HAS_WEB_STUDIO or not vision_engine:
            self.write({"success": False, "error": "Vision Engine chưa khởi động"})
            return

        try:
            data = json.loads(self.request.body)
            pick_x = data.get("pick_x") or data.get("dobot_x")
            pick_y = data.get("pick_y") or data.get("dobot_y")
            cube_name = data.get("cube_name") or data.get("class_name", "cube")

            # Nếu gửi tọa độ pixel nhấp chuột (x, y)
            if pick_x is None and "x" in data and "y" in data:
                px = float(data["x"])
                py = float(data["y"])
                
                # Tìm xem pixel này có nằm trong bbox của vật thể nào không
                matched_cube = None
                with vision_engine.lock:
                    for c in vision_engine.detected_cubes:
                        bbox = c.get("bbox", [])
                        if len(bbox) == 4:
                            x1, y1, x2, y2 = bbox
                            if x1 <= px <= x2 and y1 <= py <= y2:
                                matched_cube = c
                                break

                if matched_cube and matched_cube.get("dobot_coord", {}).get("x") is not None:
                    pick_x = matched_cube["dobot_coord"]["x"]
                    pick_y = matched_cube["dobot_coord"]["y"]
                    cube_name = matched_cube.get("class_name", cube_name)
                else:
                    # Nếu không trúng bbox, thử chuyển pixel sang dobot bằng Homography trực tiếp
                    dx, dy = vision_engine.pixel_to_dobot(px, py)
                    if dx is not None and dy is not None:
                        pick_x = dx
                        pick_y = dy
                    else:
                        self.write({"success": False, "message": "Không thể đổi tọa độ pixel sang tọa độ Dobot (chưa nạp Calib)"})
                        return

            if pick_x is None or pick_y is None:
                self.write({"success": False, "message": "Thiếu tọa độ gắp Dobot"})
                return

            res = vision_engine.execute_pick_and_place(float(pick_x), float(pick_y), str(cube_name))
            self.write(res)
        except Exception as e:
            self.write({"success": False, "message": str(e)})


class ApiVisionAutoSortHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        if not HAS_WEB_STUDIO or not vision_engine:
            self.write({"success": False, "error": "Vision Engine chưa khởi động"})
            return

        try:
            data = json.loads(self.request.body) if self.request.body else {}
            enable = data.get("enable", None)
            res = vision_engine.toggle_auto_sort(enable)
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiVisionModelsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def get(self):
        candidates = ["yolov8n.pt", "yolo11n.pt"]
        if MODELS_DIR.exists():
            for f in sorted(MODELS_DIR.glob("*.pt")):
                if f.name not in candidates:
                    candidates.append(f.name)
        model_objs = []
        for name in candidates:
            p = MODELS_DIR / name
            size_mb = round(p.stat().st_size / (1024 * 1024), 1) if p.exists() else 6.2
            label = "YOLOv8 Nano (Khuyến nghị)" if name == "yolov8n.pt" else ("YOLO11 Nano" if name == "yolo11n.pt" else f"Mô hình ({name})")
            model_objs.append({
                "name": name,
                "label": label,
                "size_mb": size_mb,
                "exists": p.exists()
            })
        active = vision_engine.active_model_name if HAS_WEB_STUDIO and vision_engine else "yolov8n.pt"
        self.write({
            "status": "ok",
            "models": model_objs,
            "current_model": active,
            "active_model": active
        })

    def post(self):
        try:
            data = json.loads(self.request.body)
            model_name = data.get("model", "")
            target_path = MODELS_DIR / model_name
            if target_path.exists() and HAS_WEB_STUDIO and vision_engine:
                ok = vision_engine.load_best_yolo_model(target_path)
                self.write({"status": "ok", "success": ok, "active_model": vision_engine.active_model_name, "message": f"Đã nạp mô hình {vision_engine.active_model_name}"})
            else:
                self.write({"status": "error", "success": False, "error": "Không tìm thấy file model", "message": "Không tìm thấy file model"})
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiCalibInfoHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def get(self):
        calib_file = BASE_DIR / "homography_dobot.json"
        if calib_file.exists():
            try:
                with open(calib_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.write({"status": "ok", "calibrated": True, "data": data})
                return
            except Exception as e:
                self.write({"status": "error", "calibrated": False, "error": str(e)})
                return
        self.write({"status": "ok", "calibrated": False, "message": "Chưa có file homography_dobot.json"})


class ApiDropTargetsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def get(self):
        drop_file = BASE_DIR / "drop_targets.json"
        if drop_file.exists():
            try:
                with open(drop_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.write({"status": "ok", "data": data})
                return
            except Exception:
                pass
        default_data = {
            "mode": "all",
            "default": {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Mặc Định"},
            "by_color": {
                "cube_red":    {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Đỏ"},
                "cube_green":  {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Xanh Lục"},
                "cube_blue":   {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Xanh Dương"},
                "cube_yellow": {"x": 49.2, "y": -230.1, "z": -44.0, "name": "Khay Vàng"}
            }
        }
        self.write({"status": "ok", "data": default_data})

    def post(self):
        try:
            data = json.loads(self.request.body)
            drop_file = BASE_DIR / "drop_targets.json"
            with open(drop_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            if HAS_WEB_STUDIO and vision_engine:
                try:
                    import web_vision_engine
                    web_vision_engine.load_drop_targets()
                except Exception:
                    pass
            print(f"[LiveServer] 💾 Đã lưu cấu hình khay thả: {drop_file}")
            self.write({"status": "ok", "message": "Đã lưu vị trí thả đồ thành công!"})
        except Exception as e:
            self.write({"status": "error", "message": str(e)})


def find_available_port(preferred_port=8080):
    import socket
    for p in [preferred_port, 8081, 8082, 8088]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', p))
            s.close()
            return p
        except OSError:
            continue
    return preferred_port


def main():
    preferred = int(os.environ.get("PORT", 8080))
    port = find_available_port(preferred)
    app = tornado.web.Application([
        (r"/", MainHandler),
        (r"/dobot_visualizer.html", MainHandler),
        (r"/index.html", MainHandler),
        (r"/ws", WebSocketHandler),
        (r"/api/cmd", ApiCmdHandler),
        (r"/api/robot/connect", ApiRobotConnectHandler),
        (r"/api/robot/disconnect", ApiRobotDisconnectHandler),
        (r"/api/robot/ports", ApiRobotPortsHandler),
        (r"/(.*\.(?:js|ico|png))", StaticFileHandler),
        # Web Studio Streaming & APIs
        (r"/ws/video", VideoWsHandler),
        (r"/api/tool/launch", ApiToolLaunchHandler),
        (r"/api/tool/stop", ApiToolStopHandler),
        (r"/api/tool/status", ApiToolStatusHandler),
        (r"/api/camera", ApiCameraHandler),
        (r"/api/dataset/stats", ApiDatasetStatsHandler),
        (r"/api/dataset/capture", ApiDatasetCaptureHandler),
        (r"/api/dataset/delete", ApiDatasetDeleteHandler),
        (r"/api/dataset/add_class", ApiDatasetAddClassHandler),
        (r"/api/dataset/recent", ApiDatasetRecentHandler),
        (r"/api/dataset/image/(.*)", DatasetImageHandler),
        (r"/api/train/start", ApiTrainStartHandler),
        (r"/api/train/status", ApiTrainStatusHandler),
        (r"/api/train/stop", ApiTrainStopHandler),
        (r"/api/train/export_colab", ApiTrainExportColabHandler),
        (r"/api/train/download_zip", ApiTrainDownloadZipHandler),
        (r"/api/train/kaggle/creds", ApiKaggleCredsHandler),
        (r"/api/train/kaggle/start", ApiKaggleStartHandler),
        (r"/api/train/kaggle/status", ApiKaggleStatusHandler),
        (r"/api/train/kaggle/stop", ApiKaggleStopHandler),
        (r"/api/vision/status", ApiVisionStatusHandler),
        (r"/api/vision/pick", ApiVisionPickHandler),
        (r"/api/vision/auto_sort", ApiVisionAutoSortHandler),
        (r"/api/vision/models", ApiVisionModelsHandler),
        (r"/api/vision/drop_targets", ApiDropTargetsHandler),
        (r"/api/calib/info", ApiCalibInfoHandler),
        (r"/api/workspace/safety", ApiWorkspaceSafetyHandler),
        (r"/dobot_description/(.*)", tornado.web.StaticFileHandler, {"path": str(BASE_DIR / "dobot_description")}),
    ])
    
    app.listen(port, address="0.0.0.0")
    print("=" * 60)
    print(f"  DOBOT MAGICIAN 3D LIVE DIGITAL TWIN SERVER")
    print(f"  Giao diện Web: http://localhost:{port}")
    print("=" * 60)
    print("[*] Dobot Magician: Chế độ kết nối qua Web UI (Bấm nút 'Kết Nối Dobot' khi cắm USB)")

    # Tần số đọc 50ms (~20 lần/giây)
    tornado.ioloop.PeriodicCallback(poll_robot_pose, 50).start()

    # Tự động mở trình duyệt web khi máy chủ đã sẵn sàng
    import webbrowser
    def _open_browser_auto():
        target_url = f"http://localhost:{port}/dobot_visualizer.html"
        print(f"[*] Dang tu dong mo trinh duyet: {target_url}")
        try:
            webbrowser.open(target_url)
        except Exception as e:
            print(f"[-] Khong the tu mo trinh duyet: {e}")

    tornado.ioloop.IOLoop.current().call_later(0.8, _open_browser_auto)

    try:
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        print("\n[!] Dừng server.")


if __name__ == "__main__":
    main()
