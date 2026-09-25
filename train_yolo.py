"""
Script Huấn luyện mô hình YOLOv8 Nano từ tập dữ liệu vừa tạo:
- Sử dụng mô hình nhẹ nhất: yolov8n.pt (chỉ ~6MB, siêu mượt cho camera và vi điều khiển).
- Huấn luyện trực tiếp trên file yolo_dataset/data.yaml.
- Xuất ra model tốt nhất tại: runs/detect/train/weights/best.pt
"""

import sys
import subprocess
from pathlib import Path

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def check_and_install_ultralytics():
    """Kiểm tra và cài đặt thư viện ultralytics nếu máy chưa có."""
    try:
        import ultralytics
        print(f"[*] Đã tìm thấy thư viện Ultralytics (YOLO) phiên bản {ultralytics.__version__}.")
    except ImportError:
        print("[*] Đang cài đặt thư viện Ultralytics YOLOv8...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "ultralytics"])
        print("[+] Cài đặt thành công Ultralytics!")


def main():
    check_and_install_ultralytics()
    from ultralytics import YOLO

    dataset_yaml = Path("yolo_dataset/data.yaml").resolve()
    if not dataset_yaml.exists():
        print(f"[!] Không tìm thấy file {dataset_yaml}. Hãy chạy lệnh: python generate_yolo_dataset.py trước!")
        return

    print("\n" + "=" * 60)
    print(" BẮT ĐẦU HUẤN LUYỆN YOLOv8 NANO CHO OBJECT DETECTION")
    print(f" - Dataset config: {dataset_yaml}")
    print(" - Base Model    : yolov8n.pt (Pre-trained weights)")
    print(" - Số epoch      : 30")
    print(" - Kích thước ảnh: 640")
    print("=" * 60 + "\n")

    # Tải mô hình nền YOLOv8n
    model = YOLO("yolov8n.pt")

    # Huấn luyện
    model.train(
        data=str(dataset_yaml),
        epochs=30,
        imgsz=640,
        batch=16,
        name="custom_cubes",
        plots=True,
    )

    print("\n" + "=" * 60)
    print(" [HOÀN TẤT HUẤN LUYỆN]")
    print(" Mô hình tốt nhất đã được lưu tại:")
    print("  -> runs/detect/custom_cubes/weights/best.pt")
    print(" Bạn có thể chạy nhận diện camera bằng:")
    print("  -> python detect_camera_yolo.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
