#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script kiểm tra kết nối và điều khiển Dobot Magician trên Ubuntu
Sử dụng thư viện pyserial (sẵn có trên hệ thống)
"""

import sys
import time
import struct
import glob

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[-] Chưa có thư viện pyserial. Cài đặt bằng lệnh:")
    print("    pip install pyserial")
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
    def __init__(self, port=None):
        self.buf = bytearray()
        self.port = port or self.auto_detect_port()
        if not self.port:
            raise ConnectionError("Không tìm thấy cổng USB của Dobot Magician (/dev/ttyUSB* hoặc /dev/ttyACM*)!")
        
        print(f"[+] Đang mở kết nối tới cổng: {self.port} (Baudrate 115200)...")
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=115200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0
            )
        except serial.SerialException as e:
            if "Permission denied" in str(e):
                print("\n[!] LỖI PHÂN QUYỀN TRÊN UBUNTU:")
                print(f"    Chạy lệnh sau trên Terminal để cấp quyền: sudo chmod 666 {self.port}")
                print(f"    Hoặc: sudo usermod -a -G dialout $USER (sau đó đăng nhập lại)")
            raise e

        time.sleep(0.5)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        
        # 1. Xóa cờ báo lỗi phần cứng
        self._send_raw_cmd(id=20, ctrl=1)
        # 2. Xóa hàng đợi lệnh cũ và kích hoạt thực thi
        self._send_raw_cmd(id=245, ctrl=1) # SetQueuedCmdClear (ID 245)
        self._send_raw_cmd(id=240, ctrl=1) # SetQueuedCmdStartExec (ID 240)

        # 3. Khởi tạo thông số vận tốc & gia tốc PTP (Bắt buộc để robot di chuyển)
        self._send_raw_cmd(id=80, ctrl=1, params=struct.pack('<8f', *([200.0]*8)))
        self._send_raw_cmd(id=81, ctrl=1, params=struct.pack('<4f', 200.0, 200.0, 200.0, 200.0))
        self._send_raw_cmd(id=83, ctrl=1, params=struct.pack('<2f', 50.0, 50.0))

    @staticmethod
    def auto_detect_port():
        """Tự động tìm kiếm cổng USB của Dobot"""
        ports = [p.device for p in serial.tools.list_ports.comports()]
        dobot_ports = [p for p in ports if "ttyUSB" in p or "ttyACM" in p]
        if dobot_ports:
            return dobot_ports[0]
        if ports:
            return ports[0]
        
        devs = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        if devs:
            return devs[0]
        return None

    def _calc_checksum(self, payload: bytes) -> int:
        return (0x100 - (sum(payload) % 0x100)) % 0x100

    def _send_raw_cmd(self, id: int, ctrl: int, params: bytes = b""):
        """Đóng gói packet giao thức Dobot: AA AA [Len] [ID] [Ctrl] [Params...] [Checksum]"""
        length = 2 + len(params)
        payload = bytes([id, ctrl]) + params
        checksum = self._calc_checksum(payload)
        packet = bytes([0xAA, 0xAA, length]) + payload + bytes([checksum])
        self.ser.write(packet)
        self.ser.flush()

    def _read_response(self, expected_id=None, timeout=0.5):
        """Đọc và giải mã phản hồi từ Dobot, duy trì bộ đệm để không rơi rớt gói tin"""
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
                total = 3 + length + 1
                if len(self.buf) < idx + total:
                    break
                pkt = self.buf[idx : idx + total]
                self.buf = self.buf[idx + total :]
                resp_id = pkt[3]
                resp_params = pkt[5:-1]
                if expected_id is None or resp_id == expected_id:
                    return resp_id, resp_params
            time.sleep(0.005)
        return None, None

    def get_pose(self):
        """Lấy dữ liệu tọa độ hiện tại (X, Y, Z, R và 4 khớp J1-J4)"""
        # ID 10: GetPose, Ctrl=0 (Read)
        self._send_raw_cmd(id=10, ctrl=0)
        resp_id, params = self._read_response(expected_id=10)
        if params and len(params) >= 32:
            x, y, z, r, j1, j2, j3, j4 = struct.unpack("<8f", params[:32])
            return {
                "x": x, "y": y, "z": z, "r": r,
                "j1": j1, "j2": j2, "j3": j3, "j4": j4
            }
        return None

    def get_alarms(self):
        """Đọc bảng mã lỗi hiện tại (ID 20, Ctrl=0)"""
        self._send_raw_cmd(id=20, ctrl=0)
        resp_id, params = self._read_response(expected_id=20, timeout=0.3)
        if params:
            active_alarms = []
            for byte_idx, b in enumerate(params):
                for bit_idx in range(8):
                    if (b >> bit_idx) & 1:
                        code = byte_idx * 8 + bit_idx
                        desc = ALARM_DICT.get(code, f"Mã lỗi chưa định nghĩa 0x{code:02X}")
                        active_alarms.append({"code": code, "hex": f"0x{code:02X}", "desc": desc})
            return active_alarms
        return []

    def clear_alarms(self):
        """
        Khôi phục và xóa toàn bộ cảnh báo lỗi:
        1. ID 20, Ctrl=1: ClearAllAlarmsState
        2. ID 245, Ctrl=1: SetQueuedCmdClear (xóa lệnh kẹt trong queue)
        3. ID 240, Ctrl=1: SetQueuedCmdStartExec (kích hoạt lại hàng đợi)
        """
        self._send_raw_cmd(id=20, ctrl=1)
        self._send_raw_cmd(id=245, ctrl=1)
        self._send_raw_cmd(id=240, ctrl=1)
        time.sleep(0.05)
        print("[+] ĐÃ GỬI LỆNH KHÔI PHỤC: Xóa cờ lỗi (ID 20) + Xóa Queue (ID 245) + Khởi động Queue (ID 240).")

    def set_suction_cup(self, enable: bool):
        """Điều khiển giác hút (Suction Cup)"""
        # ID 62: SetEndEffectorSuctionCup
        self._send_raw_cmd(id=240, ctrl=1)
        params = bytes([1, 1 if enable else 0])
        self._send_raw_cmd(id=62, ctrl=3, params=params)
        self._send_raw_cmd(id=62, ctrl=1, params=params)

    def move_ptp(self, x, y, z, r, mode=1):
        """
        Di chuyển tới tọa độ đích:
        mode=1: MOVJ_XYZ (nội suy góc khớp - mượt mà, không kẹt điểm kỳ dị)
        mode=2: MOVL_XYZ (chuyển động thẳng)
        """
        self._send_raw_cmd(id=240, ctrl=1)
        # ID 84: SetPTPCmd, ctrl=3 (Queued write)
        params = bytes([mode]) + struct.pack("<4f", float(x), float(y), float(z), float(r))
        self._send_raw_cmd(id=84, ctrl=3, params=params)

    def home(self):
        """Đưa robot về gốc Home (Cần dọn dẹp vật cản xung quanh)"""
        # ID 31: SetHOMECmd
        params = struct.pack("<I", 0)
        self._send_raw_cmd(id=31, ctrl=1, params=params)

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("[+] Đã ngắt kết nối an toàn.")


def main():
    print("=" * 55)
    print("     CHƯƠNG TRÌNH KIỂM TRA DOBOT MAGICIAN (UBUNTU)")
    print("=" * 55)

    try:
        robot = DobotController()
    except Exception as e:
        print(f"\n[-] Không thể kết nối: {e}")
        return

    try:
        while True:
            print("\n---------------- MENU TEST ----------------")
            print("1. [ĐỌC] Lấy dữ liệu tọa độ hiện tại (Get Pose)")
            print("2. [TEST] Bật/tắt giác hút 1.5 giây (Suction Cup)")
            print("3. [TEST] Thử di chuyển nhẹ (+10mm trục Z rồi hạ lại)")
            print("4. [LỆNH] Xóa còi báo lỗi (Clear Alarms)")
            print("5. [LỆNH] Chạy về gốc (Homing)")
            print("6. [ĐIỂM] Di chuyển đầu hút tới 1 điểm chỉ định (X, Y, Z)")
            print("0. Thoát")
            print("-------------------------------------------")
            
            choice = input("Nhập lựa chọn của bạn (0-6): ").strip()
            
            if choice == "1":
                pose = robot.get_pose()
                if pose:
                    print("\n[+] DỮ LIỆU ĐỌC ĐƯỢC TỪ ROBOT:")
                    print(f"    - Tọa độ Flange:  X = {pose['x']:.2f} mm | Y = {pose['y']:.2f} mm | Z = {pose['z']:.2f} mm | R = {pose['r']:.2f}°")
                    print(f"    - Độ cao đầu hút: Z_tcp = {pose['z'] - 59.5:.2f} mm (Tool offset -59.5mm)")
                    print(f"    - Góc 4 khớp:     J1 = {pose['j1']:.2f}° | J2 = {pose['j2']:.2f}° | J3 = {pose['j3']:.2f}° | J4 = {pose['j4']:.2f}°")
                else:
                    print("[-] Không đọc được dữ liệu. Hãy kiểm tra nguồn và kết nối cáp USB.")

            elif choice == "2":
                print("[*] Đang bật bơm hút...")
                robot.set_suction_cup(True)
                time.sleep(1.5)
                print("[*] Đang tắt bơm hút...")
                robot.set_suction_cup(False)
                print("[+] Hoàn tất test giác hút!")

            elif choice == "3":
                pose = robot.get_pose()
                if not pose:
                    print("[-] Không lấy được tọa độ ban đầu để tính điểm di chuyển.")
                    continue
                
                cur_x, cur_y, cur_z, cur_r = pose['x'], pose['y'], pose['z'], pose['r']
                target_z = cur_z + 10.0
                print(f"[*] Nhấc trục Z từ {cur_z:.1f}mm lên {target_z:.1f}mm (mode 1: MOVJ)...")
                robot.move_ptp(cur_x, cur_y, target_z, cur_r, mode=1)
                time.sleep(1.5)
                
                print(f"[*] Hạ trục Z trở về {cur_z:.1f}mm ban đầu...")
                robot.move_ptp(cur_x, cur_y, cur_z, cur_r, mode=1)
                time.sleep(1.5)
                print("[+] Test di chuyển hoàn tất an toàn!")

            elif choice == "4":
                alarms = robot.get_alarms()
                if alarms:
                    print("\n[⚠️] CÁC MÃ LỖI ĐANG BÁO ĐỘNG TRÊN ROBOT:")
                    for a in alarms:
                        print(f"    - [{a['hex']}] {a['desc']}")
                else:
                    print("\n[i] Không có cờ lỗi active trong bộ nhớ.")
                
                print("[*] Đang gửi lệnh khôi phục hệ thống (Clear All Alarms + Reset Queue)...")
                robot.clear_alarms()
                time.sleep(0.2)
                
                new_alarms = robot.get_alarms()
                if not new_alarms:
                    print("[✅] THÀNH CÔNG: Đèn robot đã trở về MÀU XANH, hàng đợi lệnh đã sẵn sàng!")
                else:
                    print(f"[!] Vẫn còn cờ lỗi chưa tắt: {new_alarms}")

            elif choice == "5":
                confirm = input("[CẢNH BÁO] Cánh tay sẽ quay tìm cữ. Đảm bảo xung quanh thoáng đãng! Tiếp tục? (y/n): ")
                if confirm.lower() == 'y':
                    print("[*] Đang chạy Homing...")
                    robot.home()
                else:
                    print("[-] Đã hủy lệnh Homing.")

            elif choice == "6":
                pose = robot.get_pose()
                if not pose:
                    print("[-] Không đọc được vị trí hiện tại.")
                    continue
                cur_x, cur_y, cur_z_flange, cur_r = pose['x'], pose['y'], pose['z'], pose['r']
                cur_z_tcp = cur_z_flange - 59.5
                print(f"\n[📍] Vị trí đầu hút hiện tại: X={cur_x:.1f}, Y={cur_y:.1f}, Z_tcp={cur_z_tcp:.1f} mm")
                try:
                    tx_str = input(f"   - Nhập X (mm) [{cur_x:.1f}]: ").strip()
                    tx = float(tx_str) if tx_str else cur_x

                    ty_str = input(f"   - Nhập Y (mm) [{cur_y:.1f}]: ").strip()
                    ty = float(ty_str) if ty_str else cur_y

                    tz_str = input(f"   - Nhập Z đầu hút (mm) [{cur_z_tcp:.1f}]: ").strip()
                    tz_tcp = float(tz_str) if tz_str else cur_z_tcp
                    tz_flange = tz_tcp + 59.5

                    tr_str = input(f"   - Nhập góc R (độ) [{cur_r:.1f}]: ").strip()
                    tr = float(tr_str) if tr_str else cur_r

                    jump_opt = input("   - Dùng Safe Jump (nhấc lên cao tránh va quẹt)? (y/n) [y]: ").strip().lower()
                    use_jump = (jump_opt != 'n')
                except ValueError:
                    print("[-] Giá trị nhập không hợp lệ!")
                    continue

                if use_jump:
                    safe_flange_z = max(cur_z_flange, tz_flange) + 25.0
                    safe_flange_z = min(140.0, max(safe_flange_z, 90.0))
                    print(f"[*] Đang thực hiện Safe Jump tới X={tx:.1f}, Y={ty:.1f}, Z_tcp={tz_tcp:.1f}...")
                    robot._send_raw_cmd(240, 1)
                    robot.move_ptp(cur_x, cur_y, safe_flange_z, cur_r, mode=1)
                    robot.move_ptp(tx, ty, safe_flange_z, tr, mode=1)
                    robot.move_ptp(tx, ty, tz_flange, tr, mode=1)
                    time.sleep(3.0)
                else:
                    print(f"[*] Đang bay thẳng tới X={tx:.1f}, Y={ty:.1f}, Z_tcp={tz_tcp:.1f}...")
                    robot.move_ptp(tx, ty, tz_flange, tr, mode=1)
                    time.sleep(2.0)

                new_pose = robot.get_pose()
                if new_pose:
                    print(f"[+] ĐÃ TỚI ĐÍCH: X = {new_pose['x']:.2f} mm | Y = {new_pose['y']:.2f} mm | Z_đầu_hút = {new_pose['z'] - 59.5:.2f} mm")

            elif choice == "0":
                break
            else:
                print("Lựa chọn không hợp lệ, vui lòng chọn từ 0 đến 6.")

    except KeyboardInterrupt:
        print("\n[!] Đã dừng chương trình.")
    finally:
        robot.close()


if __name__ == "__main__":
    main()
