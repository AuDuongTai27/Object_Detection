"""
Chạy nhận diện đa vật thể theo thời gian thực từ Camera sử dụng mô hình YOLOv8 vừa train:
- Tự động tìm mô hình runs/detect/custom_cubes/weights/best.pt
- Vẽ Bounding Box, hiển thị tên nhãn và độ tin cậy (Confidence).
"""

import sys
from pathlib import Path
import cv2

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main():
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[!] Chưa có thư viện ultralytics. Hãy chạy: pip install ultralytics")
        return

    # Ưu tiên tìm file best.pt ở thư mục gốc hoặc thư mục runs
    possible_paths = [
        Path("best.pt"),
        Path("runs/detect/custom_cubes/weights/best.pt"),
        *list(Path("runs").glob("**/best.pt")),
    ]
    model_path = next((p for p in possible_paths if p.exists()), None)
    if model_path is None:
        print("[!] Chưa tìm thấy file mô hình best.pt.")
        print("-> Nếu bạn vừa train trên Colab: Hãy kéo file best.pt vừa tải về thả vào thư mục dự án này!")
        return

    print(f"[*] Đang tải mô hình: {model_path}...")
    model = YOLO(str(model_path))

    # Mở camera
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(1, backend)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0, backend)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print("\n" + "=" * 55)
    print(" ĐANG CHẠY REAL-TIME YOLO OBJECT DETECTION")
    print(" Bấm [Q] hoặc [ESC] để thoát.")
    print("=" * 55 + "\n")

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        # Dự đoán bằng YOLO
        results = model.predict(frame, conf=0.45, verbose=False)
        annotated_frame = results[0].plot()

        cv2.imshow("YOLOv8 Multi-Object Detection", annotated_frame)

        key = cv2.waitKey(1) & 0xFF
        if key in [ord("q"), ord("Q"), 27]:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
