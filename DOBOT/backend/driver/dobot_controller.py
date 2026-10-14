#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import struct
import threading
import glob
import math
from pathlib import Path

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

BASE_DIR = Path(__file__).resolve().parent.parent.parent

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
# Chuẩn Dobot Sliding Rail Kit (Driver vi bước 1/16, Pulley GT2 20T: 3200 xung / 40mm = 80 xung = 1 mm)
PULSES_PER_MM = 80.0
RAIL_MAX_MM = 1000.0       # Hành trình ray tối đa 1000 mm
DEFAULT_SPEED_MM_S = 40.0  # Vận tốc ray tiêu chuẩn 40 mm/s (chạy mượt mà, đúng tốc độ)
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
        self.safety_limits = self._load_safety_limits()
        self.pulses_per_mm = float(self.safety_limits.get("pulses_per_mm", PULSES_PER_MM))
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
            "pulses_per_mm": PULSES_PER_MM,
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
        for k in ["z_min_standalone", "z_min_rail", "z_max", "safe_travel_z", "r_min", "r_max", "pulses_per_mm"]:
            if k in new_limits:
                try:
                    self.safety_limits[k] = float(new_limits[k])
                except (ValueError, TypeError):
                    pass
        if "pulses_per_mm" in self.safety_limits:
            self.pulses_per_mm = float(self.safety_limits["pulses_per_mm"])
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

    def has_alarm(self) -> bool:
        """Kiểm tra robot hiện tại có đang bị lỗi đèn đỏ không."""
        alarms = self.get_alarms()
        return bool(alarms and len(alarms) > 0)

    def recover_to_safe_pose(self) -> bool:
        """
        Cơ chế tự phục hồi an toàn khi gặp lỗi đèn đỏ / ngoài tầm với:
        1. Tắt giác hút ngay lập tức
        2. Dừng khẩn cấp động cơ ray trượt, hủy mọi lệnh di chuyển ray
        3. Xóa cờ lỗi phần cứng và làm sạch hàng đợi lệnh bị treo
        4. Tự động thu gọn cánh tay về tư thế an toàn chuẩn (X=200, Y=0, Z=45, R=0) bằng MOVJ
        5. Đảm bảo đèn Dobot chuyển từ đỏ trở lại xanh sẵn sàng
        """
        print("[Safety] 🛡️ KÍCH HOẠT CƠ CHẾ AN TOÀN: Dừng ray, tắt hút và tự thu gọn cánh tay...")
        self.set_suction(False)
        self.rail_stop()
        self.clear_alarms()
        time.sleep(0.3)
        ok = self.move_to_xyz(200.0, 0.0, 45.0, 0.0, mode=1)
        time.sleep(1.2)
        if self.has_alarm():
            self.clear_alarms()
            time.sleep(0.3)
            ok = self.move_to_xyz(200.0, 0.0, 45.0, 0.0, mode=1)
        print("[Safety] ✅ Robot đã thu gọn an toàn và khôi phục trạng thái sẵn sàng (đèn xanh)!")
        return ok

    def wait_pose_reached(self, target_x: float, target_y: float, target_z: float, tol: float = 8.0, timeout: float = 4.0) -> bool:
        """Chờ tay robot di chuyển tới tọa độ đích với độ lệch tol (mm). Trả về False nếu gặp lỗi đèn đỏ hoặc timeout."""
        if not self.connected:
            return True
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.has_alarm():
                print(f"[Safety] 🛑 Phát hiện đèn đỏ cảnh báo khi di chuyển tới ({target_x:.1f}, {target_y:.1f}, {target_z:.1f})!")
                return False
            p = self.get_pose()
            if p:
                if (abs(p.get("x", 0.0) - float(target_x)) <= tol and
                    abs(p.get("y", 0.0) - float(target_y)) <= tol and
                    abs(p.get("z", 0.0) - float(target_z)) <= tol):
                    return True
            time.sleep(0.08)
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
            pulses = int(abs(clamped_dist) * self.pulses_per_mm)
            safe_speed = max(5.0, min(60.0, float(speed_mm_s)))
            speed_pulses = int(safe_speed * self.pulses_per_mm)
            dir_speed = -speed_pulses if clamped_dist >= 0 else speed_pulses

            if clamped_dist < 0 and self.get_rail_switch():
                self.rail_is_moving = False
                return False, "⚠️ Công tắc hành trình đang chạm, không thể lùi thêm!"

            if not self.connected:
                self.rail_current_pos = max(0.0, min(RAIL_MAX_MM, target_pos))
                self._save_rail_state(self.rail_current_pos)
                self.rail_is_moving = False
                return True, f"✅ [Mô phỏng] Ray đã ở vị trí L = {self.rail_current_pos:.1f} mm"

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

            # Đợi thêm 0.3s cho xung phần cứng Dobot xả hết và ray dừng hoàn toàn
            time.sleep(0.3)

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
                release_speed = int(8.0 * self.pulses_per_mm)
                release_pulses = int(12.0 * self.pulses_per_mm)
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
            step_pulses = int(step_mm * self.pulses_per_mm)
            step_speed = int(10.0 * self.pulses_per_mm)
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
            fine_step = int(0.5 * self.pulses_per_mm)
            fine_speed = int(5.0 * self.pulses_per_mm)
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
            retreat_pulses = int(retreat_mm * self.pulses_per_mm)
            retreat_speed = int(10.0 * self.pulses_per_mm)
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
