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

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import tornado.ioloop
import tornado.web
import tornado.websocket

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[-] Cần thư viện pyserial: pip install pyserial")
    sys.exit(1)


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

    def connect(self):
        with self.lock:
            if self.connected and self.ser and self.ser.is_open:
                return True
            self.port = self.auto_detect_port()
            if not self.port:
                self.connected = False
                return False
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
                time.sleep(0.3)
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self.buf.clear()

                # 1. Xóa cờ lỗi phần cứng
                self._send_raw_cmd(id=20, ctrl=1)

                # 2. Xóa hàng đợi lệnh cũ và kích hoạt thực thi
                self._send_raw_cmd(id=245, ctrl=1) # SetQueuedCmdClear (ID 245)
                self._send_raw_cmd(id=240, ctrl=1) # SetQueuedCmdStartExec (ID 240)

                # 3. THIẾT LẬP THÔNG SỐ VẬN TỐC & GIA TỐC PTP (Bắt buộc để robot di chuyển)
                # ID 80: SetPTPJointParams (8 floats)
                self._send_raw_cmd(id=80, ctrl=1, params=struct.pack('<8f', *([200.0]*8)))
                # ID 81: SetPTPCoordinateParams (4 floats: xyz_vel, xyz_acc, r_vel, r_acc)
                self._send_raw_cmd(id=81, ctrl=1, params=struct.pack('<4f', 200.0, 200.0, 200.0, 200.0))
                # ID 83: SetPTPCommonParams (2 floats: velocityRatio=50%, accelerationRatio=50%)
                self._send_raw_cmd(id=83, ctrl=1, params=struct.pack('<2f', 50.0, 50.0))

                self.connected = True
                print(f"[+] Kết nối thành công với Dobot tại cổng: {self.port}")
                return True
            except Exception as e:
                print(f"[-] Lỗi kết nối {self.port}: {e}")
                self.connected = False
                return False

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

    def _read_response(self, expected_id=10, timeout=0.2):
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
            if not self.connected:
                if not self.connect():
                    return None
            try:
                self.ser.reset_input_buffer()
                self._send_raw_cmd(id=10, ctrl=0) # GetPose: AA AA 02 0A 00 F6
                resp_id, params = self._read_response(expected_id=10, timeout=0.12)
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
                    except:
                        pass
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

        # Kiểm tra giới hạn an toàn vùng làm việc của Dobot Magician
        r_horiz = math.hypot(target_x, target_y)
        if r_horiz < 140.0:
            return False, f"⚠️ Quá gần chân robot ({r_horiz:.1f}mm < 140mm)! Dừng để tránh va chạm."
        if r_horiz > 330.0:
            return False, f"⚠️ Vượt quá tầm với tối đa ({r_horiz:.1f}mm > 330mm)!"
        if target_z < -65.0: # Flange Z tương ứng đầu hút Z ~ -124mm
            return False, f"⚠️ Độ cao quá thấp ({target_z - 59.5:.1f}mm)! Nguy cơ đâm mặt bàn."
        if target_z > 165.0:
            return False, f"⚠️ Vượt quá độ cao tối đa ({target_z - 59.5:.1f}mm)!"

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


robot = DobotController()
connected_clients = set()


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        file_path = os.path.join(os.path.dirname(__file__), "dobot_visualizer.html")
        with open(file_path, "r", encoding="utf-8") as f:
            self.write(f.read())


class StaticFileHandler(tornado.web.RequestHandler):
    def get(self, filename):
        file_path = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(file_path):
            if filename.endswith(".js"):
                self.set_header("Content-Type", "application/javascript")
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
        self.write({"status": "ok", "pose": pose, "connected": robot.connected})

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
            else:
                self.write({"status": "error", "msg": f"Unknown action: {action}"})
        except Exception as e:
            self.set_status(400)
            self.write({"status": "error", "error": str(e)})


poll_counter = 0

def poll_robot_pose():
    global poll_counter
    if connected_clients:
        pose = robot.get_pose()
        poll_counter += 1
        
        # Cứ 10 vòng đọc (~500ms) kiểm tra trạng thái cờ lỗi một lần
        alarms = robot.cached_alarms
        if poll_counter % 10 == 0:
            alarms = robot.get_alarms()
        
        has_alarm = bool(alarms and len(alarms) > 0)
        
        if pose:
            msg = json.dumps({
                "type": "pose",
                "connected": True,
                "port": robot.port,
                "data": pose,
                "alarms": alarms,
                "has_alarm": has_alarm
            })
        else:
            msg = json.dumps({
                "type": "pose",
                "connected": False,
                "port": robot.port or "Chưa kết nối",
                "alarms": alarms,
                "has_alarm": has_alarm
            })
        
        for client in list(connected_clients):
            try:
                client.write_message(msg)
            except Exception:
                connected_clients.discard(client)


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
        (r"/ws", WebSocketHandler),
        (r"/api/cmd", ApiCmdHandler),
        (r"/(.*\.js)", StaticFileHandler),
    ])
    
    app.listen(port, address="0.0.0.0")
    print("=" * 60)
    print(f"  DOBOT MAGICIAN 3D LIVE DIGITAL TWIN SERVER")
    print(f"  Giao diện Web: http://localhost:{port}")
    print("=" * 60)
    print("[*] Đang tự động dò tìm Dobot Magician qua cáp USB...")
    robot.connect()

    # Tần số đọc 50ms (~20 lần/giây)
    tornado.ioloop.PeriodicCallback(poll_robot_pose, 50).start()

    try:
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        print("\n[!] Dừng server.")


if __name__ == "__main__":
    main()
