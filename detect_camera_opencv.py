"""
Nhận diện đa vật thể Real-time từ Camera (Multi-Object Detection) bằng OpenCV:
- Phát hiện đồng thời TẤT CẢ các cube (Xanh dương, Lục, Đỏ, Vàng) cùng lúc trên bàn.
- Vẽ khung viền Bounding Box riêng biệt kèm tên nhãn cho từng vật thể.
- Tốc độ cực nhanh (40 - 60 FPS), không cần card GPU hay cài đặt mô hình nặng.
"""

import os
import sys
import time
import cv2
import numpy as np

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Định nghĩa dải màu HSV cho từng loại cube
COLOR_RANGES = {
    "cube_blue": {
        "lower": np.array([90, 70, 50]),
        "upper": np.array([135, 255, 255]),
        "bgr_color": (255, 100, 0),  # Xanh dương
    },
    "cube_green": {
        "lower": np.array([35, 70, 50]),
        "upper": np.array([85, 255, 255]),
        "bgr_color": (0, 255, 0),    # Xanh lục
    },
    "cube_yellow": {
        "lower": np.array([15, 80, 80]),
        "upper": np.array([38, 255, 255]),
        "bgr_color": (0, 230, 255),  # Vàng
    },
    "cube_red": {
        "lower_1": np.array([0, 70, 50]),
        "upper_1": np.array([10, 255, 255]),
        "lower_2": np.array([168, 70, 50]),
        "upper_2": np.array([180, 255, 255]),
        "bgr_color": (0, 0, 255),    # Đỏ
    },
}


def open_camera(index=1):
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cap


def main():
    print("\n" + "=" * 60)
    print(" ĐANG KHỞI ĐỘNG REAL-TIME OBJECT DETECTION CAMERA")
    print(" - Nhận diện đồng thời nhiều cube (Xanh dương, Đỏ, Vàng, Lục)")
    print(" - Tự động vẽ Bounding Box và gắn nhãn theo thời gian thực")
    print(" - Bấm [Q] hoặc [ESC] trên cửa sổ để thoát")
    print("=" * 60 + "\n")

    # Mở camera (ưu tiên camera ngoài 1, nếu không có thì mở 0)
    cap = open_camera(1)
    if not cap.isOpened():
        print("[!] Không thể mở camera.")
        return

    kernel = np.ones((5, 5), np.uint8)
    prev_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        detections = []

        # Quét tìm từng loại cube trong khung hình
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
                # Chỉ lấy vật thể có diện tích đủ lớn (tránh bụi/nhiễu)
                if area > 2500:
                    x, y, w, h = cv2.boundingRect(c)
                    detections.append({
                        "name": name,
                        "box": (x, y, w, h),
                        "color": cfg["bgr_color"],
                        "area": area,
                    })

        # Vẽ Bounding Box và tên nhãn lên màn hình
        for d in detections:
            x, y, w, h = d["box"]
            color = d["color"]
            label = d["name"]

            # Vẽ khung chữ nhật Bounding Box
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

            # Vẽ nền chữ nhãn
            t_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)[0]
            cv2.rectangle(frame, (x, y - 28), (x + t_size[0] + 10, y), color, -1)
            cv2.putText(frame, label, (x + 5, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        # Tính FPS
        curr_time = time.time()
        fps = 1.0 / max(0.001, (curr_time - prev_time))
        prev_time = curr_time

        # Header thông tin trên cùng
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 40), (20, 20, 20), -1)
        info = f"Real-time Detection  |  Objects found: {len(detections)}  |  FPS: {fps:.1f}"
        cv2.putText(frame, info, (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 200), 2)

        cv2.imshow("Multi-Object Detection - Realtime", frame)

        key = cv2.waitKey(1) & 0xFF
        if key in [ord("q"), ord("Q"), 27]:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
