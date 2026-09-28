#!/usr/bin/env python3
"""
calibrate_camera_to_dobot.py
FABLAB - Dobot Magician Hand-Eye Calibration (Camera-to-Robot Homography)

Công cụ trực quan hóa hỗ trợ ghép nối Camera và Dobot Magician:
1. Tự động nạp ma trận K và hệ số méo D từ calib_data_mono.json để khử méo thấu kính (cv2.undistort).
2. Cho phép người dùng click 4 điểm mốc (Calibration Markers) trên ảnh và nhập tọa độ thực của Dobot (X, Y).
3. Tự động tính toán ma trận Homography (H) chuyển đổi từ Pixel (u, v) sang Robot (X, Y) tính bằng mm.
4. Chế độ kiểm chứng tức thời (Live Verification): Di chuyển chuột trên ảnh để xem tọa độ Dobot tương ứng theo thời gian thực.
"""

import os
import sys
import json
import time
import argparse
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

# Thử import driver Dobot nếu có
try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CALIB_PATH = str(BASE_DIR / "calib_data_mono.json")
OUTPUT_HOMOGRAPHY_JSON = str(BASE_DIR / "homography_dobot.json")
OUTPUT_HOMOGRAPHY_NPY = str(BASE_DIR / "homography_dobot.npy")


def parse_args():
    parser = argparse.ArgumentParser(description="Calibrate Camera sang Hệ tọa độ Dobot Magician bằng Homography.")
    parser.add_argument("--cam", type=int, default=1, help="ID camera (default: 0)")
    parser.add_argument("--width", type=int, default=1280, help="Chiều rộng khung hình (default: 1280)")
    parser.add_argument("--height", type=int, default=720, help="Chiều cao khung hình (default: 720)")
    parser.add_argument("--fps", type=int, default=60, help="FPS camera (default: 60)")
    parser.add_argument("--calib", type=str, default=DEFAULT_CALIB_PATH,
                        help=f"File JSON thông số calib camera (default: {DEFAULT_CALIB_PATH})")
    parser.add_argument("--image", type=str, default=None,
                        help="Ảnh tĩnh để test nếu không có camera trực tiếp")
    parser.add_argument("--output", type=str, default=OUTPUT_HOMOGRAPHY_JSON,
                        help="Đường dẫn file lưu ma trận Homography")
    return parser.parse_args()


def load_camera_intrinsics(calib_path):
    """Nạp ma trận K và hệ số méo D từ file JSON."""
    if not os.path.exists(calib_path):
        print(f"[!] CẢNH BÁO: Không tìm thấy file calib tại: {calib_path}")
        print("    -> Sẽ chạy chế độ ảnh gốc (không khử méo).")
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
            raise KeyError("Không tìm thấy trường 'matrix' hoặc 'left' trong JSON")

        print(f"[+] Đã nạp thành công thông số camera từ: {calib_path}")
        print(f"    - Tiêu cự fx={K[0,0]:.1f}, fy={K[1,1]:.1f}")
        print(f"    - Tâm quang học cx={K[0,2]:.1f}, cy={K[1,2]:.1f}")
        return K, D
    except Exception as e:
        print(f"[!] Lỗi khi đọc file calib JSON: {e}")
        return None, None


class HomographyCalibrator:
    def __init__(self, K=None, D=None):
        self.K = K
        self.D = D
        self.pts_image = []   # [(u, v), ...]
        self.pts_robot = []   # [(X, Y), ...]
        self.current_idx = 0
        self.H = None
        self.hover_pixel = (0, 0)
        self.hover_robot = None
        self.mode = "COLLECT" # "COLLECT" hoặc "VERIFY"

    def click_event(self, event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEMOVE:
            self.hover_pixel = (x, y)
            if self.H is not None:
                self.hover_robot = self.transform_pixel_to_robot(x, y)

        elif event == cv2.EVENT_LBUTTONDOWN:
            if self.mode == "COLLECT" and self.current_idx < 4:
                idx = self.current_idx + 1
                print(f"\n[+] ĐÃ CLICK ĐIỂM {idx}: Pixel (u={x}, v={y})")
                print(f"    -> Vui lòng nhập tọa độ Dobot tương ứng cho Điểm {idx}:")
                try:
                    rx_str = input(f"       Nhập X_{idx} của Dobot (mm): ").strip()
                    ry_str = input(f"       Nhập Y_{idx} của Dobot (mm): ").strip()
                    rx = float(rx_str)
                    ry = float(ry_str)
                except ValueError:
                    print("    [!] Giá trị nhập không hợp lệ! Vui lòng click lại điểm này.")
                    return

                self.pts_image.append((x, y))
                self.pts_robot.append((rx, ry))
                self.current_idx += 1

                if self.current_idx == 4:
                    self.compute_homography()

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

        print("\n" + "=" * 60)
        print("🎉 TÍNH TOÁN MA TRẬN HOMOGRAPHY THÀNH CÔNG!")
        print("=" * 60)
        for i in range(4):
            print(f"  Điểm {i+1}: Pixel ({src[i][0]:.0f}, {src[i][1]:.0f}) ➔ Thực tế: ({dst[i][0]:.1f}, {dst[i][1]:.1f}) ➔ Dự đoán: ({pred[i][0]:.1f}, {pred[i][1]:.1f}) [Lệch: {errors[i]:.2f} mm]")
        print(f"\n👉 Sai số trung bình (Mean Error): {mean_error:.2f} mm")

        # Lưu kết quả
        self.save_homography(OUTPUT_HOMOGRAPHY_JSON, OUTPUT_HOMOGRAPHY_NPY, mean_error)
        self.mode = "VERIFY"
        print("\n[*] ĐÃ CHUYỂN SANG CHẾ ĐỘ KIỂM CHỨNG TỨC THỜI (VERIFY MODE):")
        print("    - Di chuyển chuột trên ảnh để xem tọa độ thực tế của Dobot.")
        print("    - Nhấn phím 'r' nếu muốn calib lại từ đầu.")
        print("    - Nhấn phím 'q' để kết thúc.")

    def save_homography(self, json_path, npy_path, mean_error):
        data = {
            "homography_matrix": self.H.tolist(),
            "mean_error_mm": mean_error,
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
        print(f"[+] Đã lưu ma trận Homography vào:\n    - JSON: {json_path}\n    - NPY:  {npy_path}")

    def draw_overlay(self, frame):
        """Vẽ hướng dẫn, điểm mốc và tọa độ lên khung hình."""
        h, w = frame.shape[:2]
        overlay = frame.copy()

        # Thanh tiêu đề trên cùng
        cv2.rectangle(overlay, (0, 0), (w, 50), (30, 30, 30), -1)

        if self.mode == "COLLECT":
            idx = self.current_idx + 1
            if idx <= 4:
                msg = f"BUOC {idx}/4: Ha mui hut Dobot vao Diem {idx} tren ban -> CLICK CHUOT vao diem do tren anh"
                color = (0, 220, 255)
            else:
                msg = "Dang tinh toan ma tran..."
                color = (0, 255, 0)
        else:
            msg = "CHE DO KIEM CHUNG: Di chuot de xem toa do Dobot | Bam 'r' de Calib lai | 'q' de thoat"
            color = (100, 255, 100)

        cv2.putText(overlay, msg, (15, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)

        # Vẽ 4 điểm đã chọn
        colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (0, 255, 255)]
        for i, (u, v) in enumerate(self.pts_image):
            c = colors[i % len(colors)]
            cv2.circle(overlay, (u, v), 9, c, 2)
            cv2.circle(overlay, (u, v), 3, c, -1)
            label = f"P{i+1}: ({u},{v})"
            if i < len(self.pts_robot):
                rx, ry = self.pts_robot[i]
                label += f" -> Dobot({rx:.1f},{ry:.1f})"
            cv2.putText(overlay, label, (u + 12, v - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 2, cv2.LINE_AA)

        # Nối 4 điểm thành đa giác vùng làm việc
        if len(self.pts_image) == 4:
            pts = np.array(self.pts_image, np.int32).reshape((-1, 1, 2))
            cv2.polylines(overlay, [pts], isClosed=True, color=(255, 200, 0), thickness=2)

        # Hiển thị tọa độ theo con trỏ chuột
        ux, uy = self.hover_pixel
        cv2.drawMarker(overlay, (ux, uy), (200, 200, 200), cv2.MARKER_CROSS, 20, 1)

        info_box_y = h - 45
        cv2.rectangle(overlay, (0, info_box_y), (w, h), (20, 20, 20), -1)

        if self.hover_robot:
            rx, ry = self.hover_robot
            r_dist = np.hypot(rx, ry)
            status = "AN TOAN" if (140 <= r_dist <= 330) else "NGOAI TAM VOI!"
            status_color = (0, 255, 0) if (140 <= r_dist <= 330) else (0, 0, 255)

            coord_text = f"Con tro: Pixel({ux}, {uy})  ==>  DOBOT: X = {rx:.1f} mm | Y = {ry:.1f} mm | Ban kinh R = {r_dist:.1f} mm  [{status}]"
            cv2.putText(overlay, coord_text, (15, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2, cv2.LINE_AA)
        else:
            coord_text = f"Con tro: Pixel({ux}, {uy})"
            cv2.putText(overlay, coord_text, (15, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1, cv2.LINE_AA)

        return overlay


def main():
    args = parse_args()
    K, D = load_camera_intrinsics(args.calib)
    calibrator = HomographyCalibrator(K, D)

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
    cv2.setMouseCallback(win_name, calibrator.click_event)

    print("\n" + "=" * 60)
    print(" HƯỚNG DẪN THỰC HIỆN:")
    print(" 1. Chuẩn bị 4 điểm mốc đánh dấu trên mặt bàn (Điểm 1 -> 4).")
    print(" 2. Điều khiển mũi hút Dobot chạm vào Điểm 1 trên bàn.")
    print(" 3. Click chuột vào tâm Điểm 1 trên cửa sổ camera.")
    print(" 4. Nhập tọa độ X, Y của Dobot vào Terminal.")
    print(" 5. Lặp lại với các Điểm 2, 3, 4.")
    print("=" * 60 + "\n")

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

        display_frame = calibrator.draw_overlay(frame)
        cv2.imshow(win_name, display_frame)

        key = cv2.waitKey(10) & 0xFF
        if key == ord('q') or key == 27: # 'q' hoặc ESC
            break
        elif key == ord('r'): # Reset calib lại
            print("[*] Đã reset điểm mốc, bắt đầu calib lại từ Điểm 1.")
            calibrator.pts_image.clear()
            calibrator.pts_robot.clear()
            calibrator.current_idx = 0
            calibrator.H = None
            calibrator.mode = "COLLECT"

    if cap:
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
