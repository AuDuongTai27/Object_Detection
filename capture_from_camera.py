"""
Công cụ chụp ảnh mẫu trực tiếp từ Camera / Webcam để làm dataset huấn luyện.
Cách dùng:
    python capture_from_camera.py --class cube_blue
    python capture_from_camera.py --class cube_red
Phím tắt khi mở Camera:
    [SPACE] : Chụp 1 tấm ảnh
    [c]     : Chụp liên tục (burst mode 5 ảnh)
    [q] / [ESC]: Thoát
"""

import os
import sys
import time
import argparse
from pathlib import Path

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import cv2


def main():
    parser = argparse.ArgumentParser(description="Chụp ảnh mẫu từ Camera / Webcam cho Dataset.")
    parser.add_argument(
        "--class",
        "-c",
        dest="class_name",
        type=str,
        default="cube_blue",
        help="Tên nhãn / class cần chụp (VD: cube_blue, cube_red, background)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="dataset_raw",
        help="Thư mục gốc chứa dataset thô (mặc định: dataset_raw)",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Chỉ số camera (0 là webcam mặc định)",
    )

    args = parser.parse_args()

    save_dir = Path(args.output) / args.class_name
    save_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"[Lỗi] Không thể mở camera index {args.camera}. Vui lòng kiểm tra lại kết nối camera.")
        return

    # Đếm số ảnh hiện có để đặt tên tiếp theo
    existing_count = len(list(save_dir.glob("*.jpg")))
    img_counter = existing_count

    print(f"\n{'='*50}")
    print(f" Đang mở camera cho class: '{args.class_name}'")
    print(f" Ảnh sẽ được lưu vào: {save_dir.resolve()}")
    print(f" [SPACE]: Chụp 1 ảnh | [C]: Chụp 5 ảnh liên tiếp | [Q]/[ESC]: Thoát")
    print(f"{'='*50}\n")

    burst_remaining = 0
    last_burst_time = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[Lỗi] Không nhận được khung hình từ camera.")
            break

        display_frame = frame.copy()
        h, w = display_frame.shape[:2]

        # Hiển thị thông tin lên khung hình
        info_text = f"Class: {args.class_name} | Captured: {img_counter}"
        cv2.putText(display_frame, info_text, (15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(display_frame, "SPACE: Chup 1 anh | C: Chup 5 anh | Q: Thoat", (15, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        # Khung viền ngắm mục tiêu ở giữa
        box_size = int(min(h, w) * 0.5)
        x1 = (w - box_size) // 2
        y1 = (h - box_size) // 2
        cv2.rectangle(display_frame, (x1, y1), (x1 + box_size, y1 + box_size), (0, 255, 255), 1)

        cv2.imshow("Camera Capture - Teachable Machine Dataset", display_frame)

        key = cv2.waitKey(1) & 0xFF

        # Xử lý chụp 1 ảnh
        if key == 32:  # Phím SPACE
            img_counter += 1
            filename = save_dir / f"img_{img_counter:04d}.jpg"
            cv2.imwrite(str(filename), frame)
            print(f"[Đã chụp] {filename.name}")
            # Hiệu ứng chớp màn hình trắng nhẹ khi chụp
            cv2.imshow("Camera Capture - Teachable Machine Dataset", 255 - display_frame)
            cv2.waitKey(50)

        # Xử lý burst 5 ảnh
        elif key in [ord('c'), ord('C')]:
            burst_remaining = 5
            print("[Burst] Bắt đầu chụp 5 ảnh liên tiếp...")

        # Thoát
        elif key in [ord('q'), ord('Q'), 27]:
            break

        # Xử lý burst
        if burst_remaining > 0 and time.time() - last_burst_time > 0.3:
            img_counter += 1
            filename = save_dir / f"img_{img_counter:04d}.jpg"
            cv2.imwrite(str(filename), frame)
            print(f"  [Burst {6 - burst_remaining}/5] {filename.name}")
            burst_remaining -= 1
            last_burst_time = time.time()

    cap.release()
    cv2.destroyAllWindows()
    print(f"\n[Xong] Tổng cộng {img_counter} ảnh trong thư mục '{save_dir}'.")


if __name__ == "__main__":
    main()
