#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script di chuyển đầu hút Dobot Magician tới 1 điểm tọa độ chỉ định (X, Y, Z, R).
Hỗ trợ cả chế độ chạy tham số dòng lệnh (CLI args) lẫn chế độ nhập tay tương tác (Interactive).
Tích hợp sẵn:
- Bù trừ chiều dài giác hút (Tool offset 59.5mm): Tọa độ Z nhập vào là độ cao thực tế của đầu hút.
- Chế độ di chuyển an toàn Safe Jump (nhấc lên cao -> bay ngang -> hạ xuống) tránh va quẹt.
- Kiểm tra giới hạn không gian làm việc (Workspace Safety Check).
"""

import sys
import time
import struct
import argparse
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
    print("[-] Cần cài đặt thư viện pyserial: pip install pyserial")
    sys.exit(1)


TOOL_OFFSET_Z = 59.5  # Chiều dài đầu giác hút tính từ mặt bích (Flange)


class DobotPointController:
    def __init__(self, port=None):
        self.port = port or self.auto_detect_port()
        if not self.port:
            raise ConnectionError("Không tìm thấy cổng USB Dobot Magician (/dev/ttyUSB*)!")
        
        print(f"[+] Kết nối Dobot tại cổng: {self.port} (115200 baud)...")
        self.ser = serial.Serial(
            port=self.port,
            baudrate=115200,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.3
        )
        self.ser.setDTR(True)
        self.buf = bytearray()
        self.ser.setRTS(True)
        time.sleep(0.2)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

        # Khởi tạo các thông số vận tốc và hàng đợi
        self._send_raw_cmd(id=20, ctrl=1)  # ClearAlarm
        self._send_raw_cmd(id=245, ctrl=1) # SetQueuedCmdClear (ID 245)
        self._send_raw_cmd(id=240, ctrl=1) # SetQueuedCmdStartExec (ID 240)
        self._send_raw_cmd(id=80, ctrl=1, params=struct.pack('<8f', *([200.0]*8)))
        self._send_raw_cmd(id=81, ctrl=1, params=struct.pack('<4f', 200.0, 200.0, 200.0, 200.0))
        self._send_raw_cmd(id=83, ctrl=1, params=struct.pack('<2f', 50.0, 50.0))

    @staticmethod
    def auto_detect_port():
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = f"{p.description} {p.manufacturer} {p.hwid}".lower()
            if any(k in desc for k in ["cp210", "silicon", "ch340", "ch341", "ftdi", "usb serial"]):
                return p.device
        if ports:
            return ports[0].device
        devs = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        if devs:
            return devs[-1]
        return None

    def _calc_checksum(self, payload: bytes) -> int:
        return (0x100 - (sum(payload) % 0x100)) % 0x100

    def _send_raw_cmd(self, id: int, ctrl: int, params: bytes = b""):
        length = 2 + len(params)
        payload = bytes([id, ctrl]) + params
        checksum = self._calc_checksum(payload)
        packet = bytes([0xAA, 0xAA, length]) + payload + bytes([checksum])
        self.ser.write(packet)
        self.ser.flush()

    def _read_response(self, expected_id=10, timeout=0.3):
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
                pid = pkt[3]
                params = pkt[5:-1]
                if expected_id is None or pid == expected_id:
                    return pid, params
            time.sleep(0.005)
        return None, None

    def clear_alarms(self):
        """Khôi phục lỗi và mở khóa hàng đợi"""
        self._send_raw_cmd(id=20, ctrl=1)
        self._send_raw_cmd(id=245, ctrl=1)
        self._send_raw_cmd(id=240, ctrl=1)
        time.sleep(0.05)

    def get_current_pose(self):
        self.ser.reset_input_buffer()
        self._send_raw_cmd(id=10, ctrl=0)
        _, params = self._read_response(expected_id=10, timeout=0.2)
        if params and len(params) >= 32:
            x, y, z_flange, r, j1, j2, j3, j4 = struct.unpack("<8f", params[:32])
            z_tcp = z_flange - TOOL_OFFSET_Z
            return {
                "x": round(x, 2),
                "y": round(y, 2),
                "z_tcp": round(z_tcp, 2),
                "z_flange": round(z_flange, 2),
                "r": round(r, 2),
                "j1": round(j1, 2), "j2": round(j2, 2), "j3": round(j3, 2), "j4": round(j4, 2)
            }
        return None

    def set_suction(self, enable: bool):
        params = bytes([1, 1 if enable else 0])
        self._send_raw_cmd(id=240, ctrl=1)
        self._send_raw_cmd(id=62, ctrl=3, params=params)
        self._send_raw_cmd(id=62, ctrl=1, params=params)
        print(f"[+] Giác hút khí nén: {'BẬT' if enable else 'TẮT'}")

    def validate_coordinates(self, x, y, z_tcp):
        """Kiểm tra giới hạn an toàn vật lý của Dobot Magician"""
        import math
        r_horiz = math.sqrt(x * x + y * y)
        if r_horiz < 140.0:
            return False, f"Bán kính quá gần tâm robot ({r_horiz:.1f}mm < 140mm)! Có nguy cơ tự đâm vào thân."
        if r_horiz > 330.0:
            return False, f"Bán kính vượt quá tầm với ({r_horiz:.1f}mm > 330mm)!"
        if z_tcp < -120.0:
            return False, f"Độ cao Z quá thấp ({z_tcp:.1f}mm < -120mm)! Có nguy cơ đâm vào mặt bàn."
        if z_tcp > 150.0:
            return False, f"Độ cao Z quá cao ({z_tcp:.1f}mm > 150mm)!"
        return True, "Hợp lệ"

    def move_to_point(self, target_x, target_y, target_z_tcp, target_r=0.0, mode="safe"):
        """
        Di chuyển đầu hút tới điểm đích (X, Y, Z_tcp, R).
        mode='safe': Nhấc lên độ cao an toàn -> bay ngang -> hạ xuống Z đích (Safe Jump)
        mode='direct': Bay thẳng trực tiếp tới điểm đích
        """
        valid, msg = self.validate_coordinates(target_x, target_y, target_z_tcp)
        if not valid:
            print(f"[-] CẢNH BÁO AN TOÀN: {msg}")
            return False

        target_z_flange = target_z_tcp + TOOL_OFFSET_Z
        cur = self.get_current_pose()
        if not cur:
            print("[-] Không đọc được vị trí hiện tại của robot!")
            return False

        self._send_raw_cmd(id=240, ctrl=1) # Đảm bảo hàng đợi chạy

        if mode == "safe":
            # Tọa độ cao an toàn (Safe Z)
            safe_tcp_z = max(cur["z_tcp"], target_z_tcp) + 25.0
            safe_tcp_z = min(100.0, max(50.0, safe_tcp_z))
            safe_flange_z = safe_tcp_z + TOOL_OFFSET_Z

            print(f"[*] DI CHUYỂN AN TOÀN (SAFE JUMP):")
            print(f"    1. Nhấc đầu hút lên độ cao an toàn: Z = {safe_tcp_z:.1f} mm")
            p1 = bytes([1]) + struct.pack("<4f", cur["x"], cur["y"], safe_flange_z, cur["r"])
            self._send_raw_cmd(id=84, ctrl=3, params=p1)

            print(f"    2. Bay ngang tới vị trí: (X = {target_x:.1f}, Y = {target_y:.1f})")
            p2 = bytes([1]) + struct.pack("<4f", target_x, target_y, safe_flange_z, target_r)
            self._send_raw_cmd(id=84, ctrl=3, params=p2)

            print(f"    3. Hạ đầu hút xuống độ cao đích: Z = {target_z_tcp:.1f} mm")
            p3 = bytes([1]) + struct.pack("<4f", target_x, target_y, target_z_flange, target_r)
            self._send_raw_cmd(id=84, ctrl=3, params=p3)

            # Chờ chuyển động hoàn thành
            time.sleep(3.0)
        else:
            print(f"[*] DI CHUYỂN TRỰC TIẾP:")
            print(f"    Bay thẳng tới: X = {target_x:.1f}, Y = {target_y:.1f}, Z = {target_z_tcp:.1f}, R = {target_r:.1f}")
            p = bytes([1]) + struct.pack("<4f", target_x, target_y, target_z_flange, target_r)
            self._send_raw_cmd(id=84, ctrl=3, params=p)
            time.sleep(2.0)

        # Kiểm tra tọa độ thực tế đạt được
        final = self.get_current_pose()
        if final:
            dx = abs(final["x"] - target_x)
            dy = abs(final["y"] - target_y)
            dz = abs(final["z_tcp"] - target_z_tcp)
            print("\n[+] ĐÃ TỚI ĐIỂM ĐÍCH THÀNH CÔNG:")
            print(f"    - Tọa độ đầu hút thực tế: X = {final['x']:.2f} mm | Y = {final['y']:.2f} mm | Z = {final['z_tcp']:.2f} mm | R = {final['r']:.2f}°")
            print(f"    - Độ lệch (Sai số): ΔX = {dx:.2f}mm | ΔY = {dy:.2f}mm | ΔZ = {dz:.2f}mm")
            return True
        return False

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()


def main():
    parser = argparse.ArgumentParser(description="Di chuyển đầu hút Dobot Magician tới 1 điểm tọa độ chỉ định.")
    parser.add_argument("--x", type=float, default=None, help="Tọa độ X (mm) [140 -> 330]")
    parser.add_argument("--y", type=float, default=None, help="Tọa độ Y (mm) [-230 -> 230]")
    parser.add_argument("--z", type=float, default=None, help="Tọa độ Z đầu hút (mm) [-120 -> 150]")
    parser.add_argument("--r", type=float, default=0.0, help="Góc xoay R (độ) [-135 -> 135]")
    parser.add_argument("--direct", action="store_true", help="Bay thẳng trực tiếp thay vì Safe Jump")
    parser.add_argument("--suck", choices=["on", "off"], default=None, help="Bật hoặc tắt giác hút sau khi tới đích")

    args = parser.parse_args()

    print("=" * 60)
    print("      DOBOT MAGICIAN - ĐIỀU KHIỂN ĐẦU HÚT ĐẾN 1 ĐIỂM")
    print("=" * 60)

    try:
        robot = DobotPointController()
    except Exception as e:
        print(f"[-] Lỗi kết nối: {e}")
        return

    cur = robot.get_current_pose()
    if not cur:
        print("[-] Không đọc được dữ liệu từ Dobot. Kiểm tra nguồn và cáp USB.")
        robot.close()
        return

    print(f"\n[📍] VỊ TRÍ ĐẦU HÚT HIỆN TẠI:")
    print(f"    X = {cur['x']:.2f} mm | Y = {cur['y']:.2f} mm | Z = {cur['z_tcp']:.2f} mm | R = {cur['r']:.2f}°\n")

    # Nếu người dùng truyền qua dòng lệnh: python3 move_to_point.py --x 250 --y 0 --z 30
    if args.x is not None and args.y is not None and args.z is not None:
        target_x = args.x
        target_y = args.y
        target_z = args.z
        target_r = args.r
        mode = "direct" if args.direct else "safe"
        suck_opt = args.suck
    else:
        # Chế độ tương tác nhập tay
        print("👉 Nhập tọa độ đích bạn muốn đầu hút di chuyển tới (bấm Enter để giữ giá trị hiện tại):")
        try:
            val_x = input(f"   - Nhập X (mm) [{cur['x']:.1f}]: ").strip()
            target_x = float(val_x) if val_x else cur['x']

            val_y = input(f"   - Nhập Y (mm) [{cur['y']:.1f}]: ").strip()
            target_y = float(val_y) if val_y else cur['y']

            val_z = input(f"   - Nhập Z đầu hút (mm) [{cur['z_tcp']:.1f}]: ").strip()
            target_z = float(val_z) if val_z else cur['z_tcp']

            val_r = input(f"   - Nhập góc R (độ) [{cur['r']:.1f}]: ").strip()
            target_r = float(val_r) if val_r else cur['r']

            print("\n👉 Chọn kiểu di chuyển:")
            print("   1. [Khuyến nghị] Di chuyển an toàn (Safe Jump: nhấc lên cao rồi hạ xuống)")
            print("   2. Bay thẳng trực tiếp (Direct)")
            opt = input("   Lựa chọn (1/2) [mặc định: 1]: ").strip()
            mode = "direct" if opt == "2" else "safe"

            suck_opt = input("👉 Có bật giác hút tại điểm đích không? (y/n) [n]: ").strip().lower()
        except KeyboardInterrupt:
            print("\n[-] Đã hủy thao tác.")
            robot.close()
            return

    # Thực hiện di chuyển
    success = robot.move_to_point(target_x, target_y, target_z, target_r, mode=mode)

    if success:
        if args.suck == "on" or (args.x is None and suck_opt == "y"):
            print("[*] Đang kích hoạt giác hút...")
            robot.set_suction(True)
        elif args.suck == "off":
            robot.set_suction(False)

    robot.close()
    print("\n[+] Kết thúc chương trình.")


if __name__ == "__main__":
    main()
