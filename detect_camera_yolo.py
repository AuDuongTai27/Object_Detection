"""
Chạy nhận diện đa vật thể theo thời gian thực từ Camera sử dụng mô hình YOLOv8:
- Ngưỡng lọc cao (mặc định 88% - 90%) để loại bỏ hoàn toàn các vật thể cùng màu gây nhầm lẫn.
- Bộ lọc hình học Cube: kiểm tra tỉ lệ khung hình (Aspect Ratio ~ 1.0) và kích thước thực tế.
- Hỗ trợ thanh kéo (Trackbar) và phím [+] [-] để chỉnh trực tiếp độ nhạy % ngay trên màn hình.
- Vẽ màu sắc tương ứng chuẩn cho từng loại cube (xanh, đỏ, vàng, lục).
"""

import sys
import time
from pathlib import Path
import cv2
import numpy as np

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

WINDOW_NAME = "YOLOv8 Multi-Cube Detection (Real-time)"

# Màu sắc hiển thị BGR cho từng loại nhãn
CLASS_COLORS = {
    "cube_blue": (255, 120, 0),      # Xanh dương
    "cube_green": (0, 230, 0),       # Xanh lục
    "cube_red": (0, 0, 255),         # Đỏ
    "cube_yellow": (0, 230, 255),    # Vàng
}


def open_camera(cam_index=1):
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(cam_index, backend)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cap


def on_trackbar_change(val):
    pass


def main():
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[!] Chưa có thư viện ultralytics. Hãy chạy: pip install ultralytics")
        return

    # Tìm file mô hình best.pt
    possible_paths = [
        Path("best.pt"),
        Path("runs/detect/custom_cubes/weights/best.pt"),
        *list(Path("runs").glob("**/best.pt")),
    ]
    model_path = next((p for p in possible_paths if p.exists()), None)
    if model_path is None:
        print("[!] Không tìm thấy file 'best.pt' trong thư mục.")
        return

    print(f"[*] Đang tải mô hình YOLO: {model_path}...")
    model = YOLO(str(model_path))

    # Mở camera (ưu tiên camera ngoài 1)
    current_cam_idx = 1
    cap = open_camera(current_cam_idx)
    if not cap.isOpened():
        current_cam_idx = 0
        cap = open_camera(0)

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    try:
        cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass

    # Tạo thanh trượt (Trackbar) chỉnh % Confidence trực tiếp từ 50% đến 98% (mặc định 88%)
    default_conf_pct = 88
    cv2.createTrackbar("Nguong %", WINDOW_NAME, default_conf_pct, 98, on_trackbar_change)
    cv2.setTrackbarMin("Nguong %", WINDOW_NAME, 50)

    print("\n" + "=" * 60)
    print(" ĐANG CHẠY REAL-TIME YOLO CUBE DETECTION (BỘ LỌC CHUẨN XÁC)")
    print(f" - Ngưỡng tin cậy ban đầu : {default_conf_pct}% (Đúng cube > 90%)")
    print(" - Bộ lọc hình khối Cube  : Lọc bỏ vật thể dẹt/dài và mảng màu quá to")
    print("\n PHÍM TẮT ĐIỀU KHIỂN:")
    print("   [+] hoặc [=] : Tăng ngưỡng lọc %")
    print("   [-] hoặc [_] : Giảm ngưỡng lọc %")
    print("   [S] hoặc TAB : Đổi qua lại camera khác")
    print("   [Q] hoặc ESC : Thoát")
    print("=" * 60 + "\n")

    prev_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.02)
            continue

        h_img, w_img = frame.shape[:2]

        # Lấy ngưỡng tự tin hiện tại từ thanh trượt
        conf_pct = cv2.getTrackbarPos("Nguong %", WINDOW_NAME)
        conf_threshold = max(0.50, conf_pct / 100.0)

        # Chạy dự đoán bằng YOLOv8
        results = model.predict(frame, conf=conf_threshold, verbose=False)
        boxes_data = results[0].boxes

        valid_detections = 0

        if boxes_data is not None and len(boxes_data) > 0:
            for box in boxes_data:
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = model.names.get(cls_id, f"class_{cls_id}")

                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                x1, y1, x2, y2 = xyxy
                bw = x2 - x1
                bh = y2 - y1

                # --- BỘ LỌC HÌNH HỌC KHỐI CUBE (GEOMETRIC FILTER) ---
                # 1. Tỉ lệ khung hình (Aspect Ratio): Khối cube phải gần vuông (0.6 <= w/h <= 1.65)
                # Loại bỏ các vật thể dẹt/dài như mép bàn, thước kẻ, cánh tay áo
                aspect_ratio = bw / float(bh) if bh > 0 else 0
                if aspect_ratio < 0.60 or aspect_ratio > 1.65:
                    continue

                # 2. Lọc diện tích: Bỏ mảng màu khổng lồ (> 50% màn hình như áo người) hoặc quá nhỏ (< 1500px)
                area = bw * bh
                if area < 1500 or area > (0.50 * w_img * h_img):
                    continue

                valid_detections += 1
                color = CLASS_COLORS.get(cls_name, (0, 255, 255))

                # Vẽ khung Bounding Box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)

                # Vẽ nhãn tên + % độ tin cậy
                label_text = f"{cls_name} {int(conf * 100)}%"
                t_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)[0]
                label_y1 = max(0, y1 - 28)
                cv2.rectangle(frame, (x1, label_y1), (x1 + t_size[0] + 10, y1), color, -1)
                cv2.putText(
                    frame,
                    label_text,
                    (x1 + 5, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (255, 255, 255),
                    2,
                )

        # Tính toán FPS
        curr_time = time.time()
        fps = 1.0 / max(0.001, (curr_time - prev_time))
        prev_time = curr_time

        # Thanh trạng thái phía trên
        cv2.rectangle(frame, (0, 0), (w_img, 45), (25, 25, 25), -1)
        hud_text = f"Nguong Conf: {conf_pct}% (Keo thanh hoac bam +/-) | Cubes: {valid_detections} | FPS: {fps:.1f}"
        cv2.putText(frame, hud_text, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (0, 255, 200), 2)

        cv2.imshow(WINDOW_NAME, frame)

        key = cv2.waitKey(1) & 0xFF

        # Tăng / Giảm ngưỡng tự tin bằng bàn phím
        if key in [ord("+"), ord("=")]:
            new_pct = min(98, conf_pct + 2)
            cv2.setTrackbarPos("Nguong %", WINDOW_NAME, new_pct)
            print(f"[*] Tăng ngưỡng lọc: {new_pct}%")

        elif key in [ord("-"), ord("_")]:
            new_pct = max(50, conf_pct - 2)
            cv2.setTrackbarPos("Nguong %", WINDOW_NAME, new_pct)
            print(f"[*] Giảm ngưỡng lọc: {new_pct}%")

        # Đổi Camera
        elif key in [ord("s"), ord("S"), 9]:  # S hoặc TAB
            current_cam_idx = 0 if current_cam_idx == 1 else 1
            print(f"[*] Đổi sang Camera [{current_cam_idx}]...")
            cap.release()
            time.sleep(0.2)
            cap = open_camera(current_cam_idx)

        # Thoát
        elif key in [ord("q"), ord("Q"), 27]:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
