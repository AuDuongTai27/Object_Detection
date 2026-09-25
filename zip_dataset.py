"""
Nén thư mục yolo_dataset thành yolo_dataset.zip để sẵn sàng tải lên Google Colab.
Cách dùng:
    python zip_dataset.py
"""

import sys
import shutil
from pathlib import Path

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main():
    source_dir = Path("yolo_dataset")
    if not source_dir.exists():
        print("[!] Thư mục 'yolo_dataset' chưa tồn tại. Hãy chạy: python generate_yolo_dataset.py trước!")
        return

    output_zip = Path("yolo_dataset.zip")
    print(f"[*] Đang nén thư mục '{source_dir}' thành '{output_zip}'...")

    # Nén toàn bộ thư mục
    shutil.make_archive("yolo_dataset", "zip", root_dir="yolo_dataset")

    size_mb = output_zip.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 55)
    print(f" [+] NÉN THÀNH CÔNG: {output_zip.resolve()}")
    print(f" [+] Dung lượng: {size_mb:.2f} MB")
    print(" Sẵn sàng kéo thả file yolo_dataset.zip này lên Google Colab!")
    print("=" * 55)


if __name__ == "__main__":
    main()
