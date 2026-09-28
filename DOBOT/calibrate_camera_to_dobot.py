#!/usr/bin/env python3
"""
calibrate_camera_to_dobot.py
FABLAB - Dobot Magician Hand-Eye Calibration (Camera-to-Robot Homography)

Công cụ trực quan hóa hỗ trợ ghép nối Camera và Dobot Magician:
1. Tự động đọc dữ liệu tọa độ (X, Y) thời gian thực của Dobot (qua Dobot Live Server hoặc cổng Serial).
2. Quy trình Calib 4 điểm thông minh:
   - Bước 1: Click chuột vào điểm mốc trên ảnh Camera.
   - Bước 2: Di chuyển Dobot tới điểm đó trên mặt bàn. Tọa độ (X, Y) cập nhật trực tiếp trên màn hình.
   - Bước 3: Nhấn phím [ENTER] hoặc [SPACE] để CHỐT ĐIỂM.
3. Hỗ trợ phím [D] hoặc [BACKSPACE] để XÓA ĐIỂM không ưng ý và chọn lại ngay lập tức.
4. Tự động tính ma trận Homography (H), lưu vào homography_dobot.json và homography_dobot.npy.
5. Chế độ kiểm chứng tức thời (Live Verification): Rê chuột trên ảnh để xem tọa độ Dobot tương ứng.
"""

import os
import sys
import json
import time
import struct
import argparse
import urllib.request
from pathlib import Path
import numpy as np
import cv2

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DEFAULT_CALIB_PATH = str(BASE_DIR / "calib_data_mono.json")
OUTPUT_HOMOGRAPHY_JSON = str(BASE_DIR / "homography_dobot.json")
OUTPUT_HOMOGRAPHY_NPY = str(BASE_DIR / "homography_dobot.npy")


def parse_args():
    parser = argparse.ArgumentParser(description="Calibrate Camera sang Hệ tọa độ Dobot Magician bằng Homography.")
    parser.add_argument("--cam", type=int, default=1, help="ID camera (default: 1)")
    parser.add_argument("--width", type=int, default=1280, help="Chiều rộng khung hình (default: 1280)")
    parser.add_argument("--height", type=int, default=720, help="Chiều cao khung hình (default: 720)")
    parser.add_argument("--fps", type=int, default=60, help="FPS camera (default: 60)")
    parser.add_argument("--calib", type=str, default=DEFAULT_CALIB_PATH,
                        help=f"File JSON thông số calib camera (default: {DEFAULT_CALIB_PATH})")
    parser.add_argument("--image", type=str, default=None,
                        help="Ảnh tĩnh để test nếu không có camera trực tiếp")
    parser.add_argument("--server", type=str, default="http://localhost:8080",
                        help="Địa chỉ Dobot Live Server để đọc tọa độ thời gian thực")
    parser.add_argument("--output", type=str, default=OUTPUT_HOMOGRAPHY_JSON,
                        help="Đường dẫn file lưu ma trận Homography")
    return parser.parse_args()


def load_camera_intrinsics(calib_path):
    """Nạp ma trận K và hệ số méo D từ file JSON."""
    if not os.path.exists(calib_path):
        return None, None

    try:
        with open(calib_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "matrix" in data and "distortion" in data:
            K = np.array(data["matrix"], dtype=np.float64)
            D = np.array(data["distortion"], dtype=np.float64)
        elif "left" in data:
            K = np.array(data["left"]["matrix"], dtype=np.float64)
            D = np.array(data["left"]["distortion"], dtype=np.float64)
        else:
            return None, None

        print(f"[+] Đã nạp thông số khử méo camera từ: {calib_path}")
        return K, D
    except Exception as e:
        print(f"[!] Lỗi khi đọc file calib JSON: {e}")
        return None, None


class DobotPoseReader:
    """Đọc tọa độ thời gian thực của Dobot qua HTTP Server hoặc cổng Serial trực tiếp."""
    def __init__(self, server_url="http://localhost:8080"):
        self.server_url = server_url.rstrip("/") + "/api/cmd"
        self.last_pose = None
        self.is_connected = False
        self.direct_ser = None
        self.last_poll_time = 0
        self.connection_source = "None"
        self._init_connection()

    def _init_connection(self):
        if self._check_http_server():
            self.connection_source = "Live Server (HTTP)"
            return
        self._init_serial()

    def _check_http_server(self):
        try:
            req = urllib.request.Request(self.server_url, method="GET")
            with urllib.request.urlopen(req, timeout=0.3) as resp:
                data = json.loads(resp.read().decode())
                if data.get("status") == "ok":
                    pose = data.get("pose")
                    connected = bool(data.get("connected", False))
                    if pose and connected:
                        self.last_pose = pose
                        self.is_connected = True
                        self.connection_source = "Live Server (HTTP)"
                        return True
        except Exception:
            pass
        return False

    def _init_serial(self):
        try:
            import serial
            import serial.tools.list_ports
            for p in serial.tools.list_ports.comports():
                desc = f"{p.description} {p.manufacturer} {p.hwid}".lower()
                if any(k in desc for k in ["cp210", "silicon labs", "ch340", "ftdi", "usb serial"]):
                    self.direct_ser = serial.Serial(p.device, 115200, timeout=0.1)
                    self.is_connected = True
                    self.connection_source = f"Serial ({p.device})"
                    print(f"[+] Đã kết nối Serial Dobot trực tiếp: {p.device}")
                    break
        except Exception:
            pass

    def get_pose(self):
        now = time.time()
        # Thăm dò 30ms một lần
        if now - self.last_poll_time > 0.03:
            self.last_poll_time = now
            if self._check_http_server():
                return self.last_pose

        if self.direct_ser and self.direct_ser.is_open:
            try:
                self.direct_ser.reset_input_buffer()
                self.direct_ser.write(bytes([0xAA, 0xAA, 0x02, 0x0A, 0x00, 0xF6]))
                time.sleep(0.02)
                data = self.direct_ser.read(48)
                if len(data) >= 38:
                    idx = data.find(bytes([0xAA, 0xAA]))
                    if idx >= 0 and len(data[idx:]) >= 38:
                        payload = data[idx+3:idx+35]
                        x, y, z, r = struct.unpack("<4f", payload[:16])
                        self.last_pose = {"x": round(x, 2), "y": round(y, 2), "z": round(z, 2), "r": round(r, 2)}
                        self.is_connected = True
                        self.connection_source = "Serial"
                        return self.last_pose
            except Exception:
                self.direct_ser = None
                self.is_connected = False

        return self.last_pose


class HomographyCalibrator:
    def __init__(self, K=None, D=None, pose_reader=None):
        self.K = K
        self.D = D
        self.pose_reader = pose_reader
        self.pts_image = []    # [(u, v), ...]
        self.pts_robot = []    # [(X, Y), ...]
        self.pending_pixel = None  # (u, v) vừa click nhưng chưa bấm Enter
        self.H = None
        self.hover_pixel = (0, 0)
        self.hover_robot = None
        self.mode = "COLLECT"  # "COLLECT" hoặc "VERIFY"
        self.buttons = []      # Danh sách nút bấm trên màn hình OpenCV
        self.message = "BUOC 1/4: Click chuot vao Diem 1 tren mat ban"
        self.message_color = (0, 220, 255)
        self.flash_timer = 0

    def click_event(self, event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEMOVE:
            self.hover_pixel = (x, y)
            if self.H is not None:
                self.hover_robot = self.transform_pixel_to_robot(x, y)

        elif event == cv2.EVENT_LBUTTONDOWN:
            # 1. Kiểm tra xem người dùng có click trúng nút bấm UI ở cạnh dưới không
            for btn in self.buttons:
                bx1, by1, bx2, by2 = btn["rect"]
                if bx1 <= x <= bx2 and by1 <= y <= by2:
                    self.handle_action(btn["action"])
                    return

            # 2. Xử lý click chọn điểm trên khung hình camera
            if self.mode == "COLLECT" and len(self.pts_image) < 4:
                # Tránh click vào vùng thanh nút bấm dưới đáy
                param_h = param.get("height", 720) if isinstance(param, dict) else 720
                if y > param_h - 75:
                    return

                idx = len(self.pts_image) + 1
                self.pending_pixel = (x, y)
                self.message = f"DIEM {idx}: Da chon Pixel({x},{y}) -> Di chuyen Dobot toi do roi bam [ENTER]"
                self.message_color = (0, 255, 255)
                print(f"\n[+] ĐÃ CLICK ĐIỂM {idx}: Pixel (u={x}, v={y})")
                print("    -> Hãy di chuyển mũi hút Dobot tới vị trí này trên mặt bàn.")
                print("    -> Nhấn [ENTER] hoặc [SPACE] trên cửa sổ ảnh để CHỐT ĐIỂM (hoặc [D] để xóa chọn lại).")

    def handle_action(self, action):
        """Xử lý hành động từ nút bấm chuột hoặc phím tắt."""
        if action == "confirm_point":
            self.confirm_current_point()
        elif action == "delete_point":
            self.delete_point()
        elif action == "reset":
            self.reset_calib()
        elif action == "quit":
            pass

    def confirm_current_point(self):
        """Chốt điểm hiện tại: liên kết Pixel với tọa độ Dobot thực tế."""
        if self.mode != "COLLECT" or self.pending_pixel is None:
            return

        idx = len(self.pts_image) + 1
        current_pose = self.pose_reader.get_pose() if self.pose_reader else None

        if current_pose and self.pose_reader.is_connected:
            rx = float(current_pose.get("x", 0.0))
            ry = float(current_pose.get("y", 0.0))
            rz = float(current_pose.get("z", 0.0))
        else:
            # Fallback: Nhập tay nếu Dobot chưa kết nối
            print(f"\n[!] Dobot chưa kết nối trực tiếp. Vui lòng nhập tọa độ tay cho Điểm {idx}:")
            try:
                rx = float(input(f"    Nhập X_{idx} của Dobot (mm): ").strip())
                ry = float(input(f"    Nhập Y_{idx} của Dobot (mm): ").strip())
            except Exception:
                print("    [!] Tọa độ không hợp lệ!")
                return

        u, v = self.pending_pixel
        self.pts_image.append((u, v))
        self.pts_robot.append((rx, ry))
        self.pending_pixel = None

        print(f"🎉 ĐÃ CHỐT THÀNH CÔNG ĐIỂM {idx}: Pixel ({u}, {v}) ➔ Dobot (X={rx:.1f}, Y={ry:.1f})")

        if len(self.pts_image) == 4:
            self.compute_homography()
        else:
            next_idx = len(self.pts_image) + 1
            self.message = f"BUOC {next_idx}/4: Click chuot vao Diem {next_idx} tren mat ban"
            self.message_color = (0, 220, 255)

    def delete_point(self):
        """Xóa điểm calib không ưng ý (Hủy điểm đang chọn hoặc xóa lùi điểm trước)."""
        if self.pending_pixel is not None:
            # Đang có điểm vừa click nhưng chưa chốt -> Hủy điểm này
            self.pending_pixel = None
            idx = len(self.pts_image) + 1
            self.message = f"Da huy diem dang chon. Click lai Diem {idx} tren anh"
            self.message_color = (0, 165, 255)
            print(f"[!] Đã hủy điểm đang chọn. Mời bạn click lại Điểm {idx}.")
        elif len(self.pts_image) > 0:
            # Đã chốt ít nhất 1 điểm -> Xóa lùi điểm gần nhất (Undo)
            del_u, del_v = self.pts_image.pop()
            del_x, del_y = self.pts_robot.pop()
            self.mode = "COLLECT"
            self.H = None
            idx = len(self.pts_image) + 1
            self.message = f"Da xoa Diem {idx} ({del_u},{del_v}). Moi click chon lai Diem {idx}"
            self.message_color = (0, 165, 255)
            print(f"[-] Đã xóa Điểm {idx} [Pixel ({del_u}, {del_v}) <-> Dobot ({del_x:.1f}, {del_y:.1f})]. Mời chọn lại Điểm {idx}.")
        else:
            self.message = "Chua co diem nao de xoa!"
            self.message_color = (120, 120, 120)

    def reset_calib(self):
        """Reset toàn bộ điểm và thực hiện lại từ Điểm 1."""
        self.pts_image.clear()
        self.pts_robot.clear()
        self.pending_pixel = None
        self.H = None
        self.mode = "COLLECT"
        self.message = "BUOC 1/4: Click chuot vao Diem 1 tren mat ban"
        self.message_color = (0, 220, 255)
        print("\n[*] Đã xóa toàn bộ điểm mốc, bắt đầu calib lại từ Điểm 1.")

    def transform_pixel_to_robot(self, u, v):
        """Ánh xạ từ tọa độ pixel sang tọa độ Đề-các của Dobot (mm)."""
        if self.H is None:
            return None
        pt = np.array([[[float(u), float(v)]]], dtype=np.float32)
        dst = cv2.perspectiveTransform(pt, self.H)
        rx = float(dst[0][0][0])
        ry = float(dst[0][0][1])
        return rx, ry

    def compute_homography(self):
        """Tính toán ma trận H và sai số khớp."""
        src = np.array(self.pts_image, dtype=np.float32)
        dst = np.array(self.pts_robot, dtype=np.float32)

        H, status = cv2.findHomography(src, dst)
        self.H = H

        # Tính sai số ước lượng (Reprojection error)
        pred = cv2.perspectiveTransform(src.reshape(-1, 1, 2), H).reshape(-1, 2)
        errors = np.linalg.norm(pred - dst, axis=1)
        mean_error = float(np.mean(errors))

        print("\n" + "=" * 65)
        print("🎉 TÍNH TOÁN MA TRẬN HOMOGRAPHY THÀNH CÔNG!")
        print("=" * 65)
        for i in range(4):
            print(f"  Điểm {i+1}: Pixel ({src[i][0]:.0f}, {src[i][1]:.0f}) ➔ Thực tế: ({dst[i][0]:.1f}, {dst[i][1]:.1f}) ➔ Dự đoán: ({pred[i][0]:.1f}, {pred[i][1]:.1f}) [Lệch: {errors[i]:.2f} mm]")
        print(f"\n👉 Sai số trung bình (Mean Error): {mean_error:.2f} mm")

        # Lưu kết quả
        self.save_homography(OUTPUT_HOMOGRAPHY_JSON, OUTPUT_HOMOGRAPHY_NPY, mean_error)
        self.mode = "VERIFY"
        self.message = f"HOAN TAT! Sai so: {mean_error:.2f}mm | Di chuot de kiem chung | [R]: Calib lai | [Q]: Thoat"
        self.message_color = (74, 222, 128)

    def save_homography(self, json_path, npy_path, mean_error):
        data = {
            "homography_matrix": self.H.tolist(),
            "mean_error_mm": round(mean_error, 3),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "calibration_points": [
                {"point_id": i + 1, "pixel_u": float(self.pts_image[i][0]), "pixel_v": float(self.pts_image[i][1]),
                 "dobot_x": float(self.pts_robot[i][0]), "dobot_y": float(self.pts_robot[i][1])}
                for i in range(4)
            ]
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        np.save(npy_path, self.H)
        print(f"[+] Đã lưu ma trận Homography vào:\n    - JSON: {json_path}\n    - NPY:  {npy_path}\n")

    def draw_ui(self, frame):
        """Vẽ toàn bộ giao diện overlay, HUD robot và các nút bấm tương tác."""
        h, w = frame.shape[:2]
        overlay = frame.copy()
        self.flash_timer = (self.flash_timer + 1) % 30

        # 1. Thanh tiêu đề trên cùng
        cv2.rectangle(overlay, (0, 0), (w, 52), (18, 22, 31), -1)
        cv2.line(overlay, (0, 52), (w, 52), (56, 189, 248), 1)

        # Trạng thái hướng dẫn chính
        cv2.putText(overlay, self.message, (14, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.62, self.message_color, 2, cv2.LINE_AA)

        # Huy hiệu tiến độ (Ví dụ: 2/4 ĐIỂM)
        step_badge = f"{len(self.pts_image)}/4 DIEM" if self.mode == "COLLECT" else "VERIFY"
        badge_col = (0, 200, 255) if self.mode == "COLLECT" else (74, 222, 128)
        cv2.rectangle(overlay, (w - 125, 10), (w - 12, 42), (30, 41, 59), -1)
        cv2.rectangle(overlay, (w - 125, 10), (w - 12, 42), badge_col, 1)
        cv2.putText(overlay, step_badge, (w - 118, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.55, badge_col, 2, cv2.LINE_AA)

        # 2. Vẽ các điểm đã chốt
        colors = [(0, 100, 255), (0, 220, 0), (255, 120, 0), (0, 220, 255)]
        for i, (u, v) in enumerate(self.pts_image):
            c = colors[i % len(colors)]
            cv2.circle(overlay, (u, v), 10, c, 2)
            cv2.circle(overlay, (u, v), 4, c, -1)
            rx, ry = self.pts_robot[i]
            lbl = f"P{i+1}: ({u},{v}) -> ({rx:.1f}, {ry:.1f})"
            cv2.putText(overlay, lbl, (u + 14, v - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.52, c, 2, cv2.LINE_AA)

        # 3. Nối đa giác vùng làm việc nếu đã đủ 4 điểm
        if len(self.pts_image) == 4:
            pts = np.array(self.pts_image, np.int32).reshape((-1, 1, 2))
            cv2.polylines(overlay, [pts], isClosed=True, color=(255, 200, 0), thickness=2)

        # 4. Hiệu ứng điểm vừa click đang chờ chốt (Pending Point)
        if self.pending_pixel is not None:
            pu, pv = self.pending_pixel
            # Vòng tròn nhấp nháy
            ring_r = 14 + (self.flash_timer // 6) * 3
            cv2.circle(overlay, (pu, pv), ring_r, (0, 255, 255), 2)
            cv2.circle(overlay, (pu, pv), 4, (0, 255, 255), -1)
            cv2.drawMarker(overlay, (pu, pv), (0, 255, 255), cv2.MARKER_CROSS, 28, 2)
            cv2.putText(overlay, f"Diem {len(self.pts_image)+1} (Cho Enter)", (pu + 18, pv + 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2, cv2.LINE_AA)

        # 5. Chế độ kiểm chứng tức thời (VERIFY MODE)
        if self.mode == "VERIFY":
            ux, uy = self.hover_pixel
            cv2.drawMarker(overlay, (ux, uy), (200, 200, 200), cv2.MARKER_CROSS, 20, 1)

        # 6. Thanh HUD thông tin Robot và Nút bấm tương tác ở cạnh dưới
        bar_h = 75
        bar_y1 = h - bar_h
        cv2.rectangle(overlay, (0, bar_y1), (w, h), (15, 19, 26), -1)
        cv2.line(overlay, (0, bar_y1), (w, bar_y1), (255, 255, 255, 0.1), 1)

        # Dòng hiển thị tọa độ Dobot Live
        pose = self.pose_reader.get_pose() if self.pose_reader else None
        is_conn = bool(self.pose_reader and self.pose_reader.is_connected)
        src_lbl = self.pose_reader.connection_source if self.pose_reader else "None"

        if is_conn and pose:
            cur_x = pose.get("x", 0.0)
            cur_y = pose.get("y", 0.0)
            cur_z = pose.get("z", 0.0)
            robot_txt = f"ROBOT LIVE: X = {cur_x:.1f} mm | Y = {cur_y:.1f} mm | Z = {cur_z:.1f} mm  [{src_lbl}: ONLINE]"
            robot_col = (74, 222, 128)
        else:
            robot_txt = f"ROBOT: Chua ket noi realtime (Se nhap toa do bang tay khi Enter)"
            robot_col = (250, 204, 21)

        if self.mode == "VERIFY" and self.hover_robot:
            hr_x, hr_y = self.hover_robot
            r_dist = np.hypot(hr_x, hr_y)
            robot_txt = f"CON TRO: X = {hr_x:.1f} mm | Y = {hr_y:.1f} mm | R = {r_dist:.1f} mm"
            robot_col = (56, 189, 248)

        cv2.putText(overlay, robot_txt, (14, bar_y1 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, robot_col, 2, cv2.LINE_AA)

        # Vẽ 4 nút bấm tương tác (Clickable Buttons)
        margin = 14
        btn_y1 = bar_y1 + 32
        btn_h = 34
        btn_y2 = btn_y1 + btn_h
        btn_gap = 10
        btn_w = (w - margin * 2 - btn_gap * 3) // 4

        # Nút 1: Chốt Điểm (Sáng màu xanh lá khi có điểm đang chờ)
        can_confirm = (self.pending_pixel is not None and self.mode == "COLLECT")
        c1 = (34, 197, 94) if can_confirm else (45, 55, 72)
        btn1_lbl = "1. CHOT DIEM [ENTER]"

        # Nút 2: Xóa Điểm (Sáng màu cam/đỏ khi có thể xóa)
        can_delete = (self.pending_pixel is not None or len(self.pts_image) > 0)
        c2 = (0, 140, 255) if can_delete else (45, 55, 72)
        btn2_lbl = "2. XOA DIEM [D]"

        # Nút 3: Reset
        c3 = (75, 85, 99)
        btn3_lbl = "3. RESET [R]"

        # Nút 4: Thoát
        c4 = (220, 38, 38)
        btn4_lbl = "4. THOAT [Q]"

        buttons_def = [
            {"action": "confirm_point", "label": btn1_lbl, "color": c1, "enabled": can_confirm},
            {"action": "delete_point", "label": btn2_lbl, "color": c2, "enabled": can_delete},
            {"action": "reset", "label": btn3_lbl, "color": c3, "enabled": True},
            {"action": "quit", "label": btn4_lbl, "color": c4, "enabled": True},
        ]

        self.buttons = []
        for i, b in enumerate(buttons_def):
            bx1 = margin + i * (btn_w + btn_gap)
            bx2 = bx1 + btn_w
            cv2.rectangle(overlay, (bx1, btn_y1), (bx2, btn_y2), b["color"], -1)
            cv2.rectangle(overlay, (bx1, btn_y1), (bx2, btn_y2), (255, 255, 255), 1)

            t_size = cv2.getTextSize(b["label"], cv2.FONT_HERSHEY_SIMPLEX, 0.45, 2)[0]
            tx = bx1 + (btn_w - t_size[0]) // 2
            ty = btn_y1 + (btn_h + t_size[1]) // 2
            text_col = (255, 255, 255) if b["enabled"] else (160, 160, 160)
            cv2.putText(overlay, b["label"], (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.45, text_col, 1, cv2.LINE_AA)

            self.buttons.append({"rect": (bx1, btn_y1, bx2, btn_y2), "action": b["action"]})

        return overlay


def main():
    args = parse_args()
    K, D = load_camera_intrinsics(args.calib)
    pose_reader = DobotPoseReader(server_url=args.server)
    calibrator = HomographyCalibrator(K, D, pose_reader=pose_reader)

    # Khởi tạo camera hoặc đọc ảnh
    cap = None
    static_frame = None

    if args.image and os.path.exists(args.image):
        print(f"[*] Chạy với ảnh tĩnh: {args.image}")
        static_frame = cv2.imread(args.image)
        if static_frame is None:
            print("[!] Không đọc được ảnh!")
            return
    else:
        print(f"[*] Đang mở Camera ID: {args.cam}...")
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_V4L2
        cap = cv2.VideoCapture(args.cam, backend)
        if not cap.isOpened():
            cap = cv2.VideoCapture(args.cam)
        if not cap.isOpened() and args.cam != 0:
            print(f"[!] Không thể mở camera {args.cam}, thử camera 0...")
            cap = cv2.VideoCapture(0, backend)
        if not cap.isOpened():
            print(f"[!] Không thể mở camera ID {args.cam}. Bạn có thể truyền --image <đường_dẫn_ảnh> để chạy thử!")
            return

        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        cap.set(cv2.CAP_PROP_FPS, min(30, args.fps))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    win_name = "FABLAB - Dobot Hand-Eye Homography Calibration"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

    # Lấy kích thước thực tế của frame để truyền cho chuột
    frame_w = args.width
    frame_h = args.height
    cv2.setMouseCallback(win_name, calibrator.click_event, param={"width": frame_w, "height": frame_h})

    print("\n" + "=" * 65)
    print(" HƯỚNG DẪN HIỆU CHUẨN HOMOGRAPHY TỰ ĐỘNG:")
    print(" 1. Click chuột trái vào điểm mốc trên cửa sổ Camera OpenCV.")
    print(" 2. Di chuyển tay robot Dobot chạm vào điểm đó trên mặt bàn.")
    print(" 3. Nhấn [ENTER] hoặc [SPACE] trên cửa sổ ảnh để LƯU/CHỐT ĐIỂM.")
    print(" 4. Nhấn phím [D] hoặc [BACKSPACE] nếu muốn XÓA ĐIỂM không ưng ý.")
    print(" 5. Lặp lại 4 điểm, hệ thống sẽ tự động tính ma trận Homography!")
    print("=" * 65 + "\n")

    while True:
        if static_frame is not None:
            raw_frame = static_frame.copy()
        else:
            ret, raw_frame = cap.read()
            if not ret or raw_frame is None:
                time.sleep(0.01)
                continue

        # Khử méo thấu kính nếu có K và D
        if K is not None and D is not None:
            frame = cv2.undistort(raw_frame, K, D)
        else:
            frame = raw_frame

        display_frame = calibrator.draw_ui(frame)
        cv2.imshow(win_name, display_frame)

        # Bắt phím bấm (10ms)
        key = cv2.waitKey(10) & 0xFF

        if key == ord('q') or key == ord('Q') or key == 27:  # 'q' hoặc ESC
            break
        elif key == 13 or key == 10 or key == 32:  # ENTER (13/10) hoặc SPACE (32)
            calibrator.confirm_current_point()
        elif key == ord('d') or key == ord('D') or key == 8 or key == 127:  # 'd' hoặc BACKSPACE
            calibrator.delete_point()
        elif key == ord('r') or key == ord('R'):  # Reset
            calibrator.reset_calib()

    if cap:
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
