"""
Chạy nhận diện đa vật thể theo thời gian thực từ Camera sử dụng mô hình YOLO (best_v5.pt / best_v8.pt):
- Tự động ưu tiên tải best_v5.pt (hoặc best_v8.pt, best.pt).
- Ngưỡng tự tin chuẩn xác (mặc định 80% - 85%), phím [+] [-] để tinh chỉnh trực tiếp.
- Bộ lọc hình học khối Cube: bắt buộc tỉ lệ gần vuông (0.55 <= w/h <= 1.80) để chống nhận diện nhầm.
- Phím [S] / TAB để đổi qua lại camera.
"""

import sys
import time
import argparse
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

WINDOW_NAME = "YOLO Multi-Cube Detection (Real-time)"

# Màu sắc BGR đặc trưng cho từng loại cube
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


def find_model_file(requested_model=None):
    """Tìm file mô hình YOLO theo thứ tự ưu tiên."""
    if requested_model and Path(requested_model).exists():
        return Path(requested_model)

    priority_list = [
        Path("best_v5.pt"),
        Path("best_v8.pt"),
        Path("best.pt"),
    ]
    for p in priority_list:
        if p.exists():
            return p

    # Quét toàn bộ file .pt trong thư mục
    all_pts = [p for p in Path(".").glob("*.pt") if "yolov" not in p.name]
    if all_pts:
        return all_pts[0]

    return None


def main():
    parser = argparse.ArgumentParser(description="Chạy Camera nhận diện YOLO Object Detection.")
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        help="Đường dẫn tới file model .pt (mặc định: tự ưu tiên best_v5.pt hoặc best_v8.pt)",
    )
    parser.add_argument(
        "--conf",
        "-c",
        type=float,
        default=0.80,
        help="Ngưỡng tự tin tối thiểu (mặc định: 0.80 = 80%%)",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=1,
        help="Chỉ số camera (1: USB ngoài, 0: Laptop)",
    )

    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print("[!] Chưa có thư viện ultralytics. Hãy chạy: pip install ultralytics")
        return

    model_path = find_model_file(args.model)
    if model_path is None:
        print("[!] Không tìm thấy bất kỳ file mô hình .pt nào (best_v5.pt, best_v8.pt, best.pt).")
        return

    print("\n" + "=" * 62)
    print(f" [*] ĐANG NẠP MÔ HÌNH: {model_path.resolve()}")
    model = YOLO(str(model_path))
    print(f" [*] Danh sách nhãn phát hiện: {model.names}")
    print("=" * 62)

    current_cam_idx = args.camera
    cap = open_camera(current_cam_idx)
    if not cap.isOpened():
        current_cam_idx = 0
        cap = open_camera(0)

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    try:
        cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass

    conf_pct = int(args.conf * 100)

    print("\n--- PHÍM TẮT ĐIỀU KHIỂN ---")
    print("  [+] hoặc [=] : Tăng ngưỡng lọc %")
    print("  [-] hoặc [_] : Giảm ngưỡng lọc %")
    print("  [S] hoặc TAB : Đổi qua lại Camera")
    print("  [Q] hoặc ESC : Thoát")
    print("---------------------------\n")

    prev_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.02)
            continue

        h_img, w_img = frame.shape[:2]
        conf_threshold = conf_pct / 100.0

        # Dự đoán bằng YOLO
        results = model.predict(frame, conf=conf_threshold, verbose=False)
        boxes_data = results[0].boxes

        valid_count = 0

        if boxes_data is not None and len(boxes_data) > 0:
            for box in boxes_data:
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = model.names.get(cls_id, f"class_{cls_id}")

                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                x1, y1, x2, y2 = xyxy
                bw = x2 - x1
                bh = y2 - y1

                # 1. Bộ lọc hình học khối Cube: tỉ lệ cạnh gần vuông
                aspect_ratio = bw / float(bh) if bh > 0 else 0
                if aspect_ratio < 0.55 or aspect_ratio > 1.80:
                    continue

                # 2. Bộ lọc diện tích: loại mảng quá lớn (> 55% màn hình) hoặc quá nhỏ
                area = bw * bh
                if area < 1200 or area > (0.55 * w_img * h_img):
                    continue

                valid_count += 1
                color = CLASS_COLORS.get(cls_name, (0, 255, 255))

                # Vẽ khung Bounding Box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)

                # Vẽ nhãn tên + % tự tin
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

        # Tính FPS
        curr_time = time.time()
        fps = 1.0 / max(0.001, (curr_time - prev_time))
        prev_time = curr_time

        # Thanh trạng thái phía trên
        cv2.rectangle(frame, (0, 0), (w_img, 42), (25, 25, 25), -1)
        hud_text = (
            f"Model: {model_path.name} | Conf: {conf_pct}% (+/- de chinh) | "
            f"Cubes: {valid_count} | FPS: {fps:.1f}"
        )
        cv2.putText(frame, hud_text, (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 200), 2)

        cv2.imshow(WINDOW_NAME, frame)

        key = cv2.waitKey(1) & 0xFF

        # Tăng / Giảm ngưỡng tự tin bằng bàn phím
        if key in [ord("+"), ord("=")]:
            conf_pct = min(98, conf_pct + 2)
            print(f"[*] Ngưỡng tin cậy: {conf_pct}%")

        elif key in [ord("-"), ord("_")]:
            conf_pct = max(40, conf_pct - 2)
            print(f"[*] Ngưỡng tin cậy: {conf_pct}%")

        # Đổi Camera
        elif key in [ord("s"), ord("S"), 9]:
            current_cam_idx = 0 if current_cam_idx == 1 else 1
            print(f"[*] Chuyển sang Camera [{current_cam_idx}]...")
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
