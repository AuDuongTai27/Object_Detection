"""
Module quản lý dữ liệu (Dataset Manager) cho FabLab AI & Dobot Web Studio:
- Quản lý thư mục dataset_raw/
- Thống kê số lượng ảnh của từng nhãn
- Lưu ảnh chụp từ Camera
- Xóa ảnh hỏng / ảnh thừa
- Thêm nhãn mới linh hoạt
"""

import os
import sys
import time
import shutil
from pathlib import Path
import cv2

# Đường dẫn gốc
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATASET_RAW_DIR = PROJECT_ROOT / "dataset_raw"
YOLO_DATASET_DIR = PROJECT_ROOT / "yolo_dataset"

DEFAULT_CLASSES = ["cube_red", "cube_green", "cube_blue", "cube_yellow", "background"]


def ensure_dataset_dirs():
    """Đảm bảo các thư mục class mặc định tồn tại trong dataset_raw."""
    DATASET_RAW_DIR.mkdir(parents=True, exist_ok=True)
    for c in DEFAULT_CLASSES:
        (DATASET_RAW_DIR / c).mkdir(exist_ok=True)


def get_dataset_stats():
    """
    Trả về thống kê số lượng ảnh của từng class trong dataset_raw.
    """
    ensure_dataset_dirs()
    stats = {}
    total = 0

    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    for class_dir in sorted(DATASET_RAW_DIR.iterdir()):
        if class_dir.is_dir():
            count = sum(1 for f in class_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_exts)
            stats[class_dir.name] = count
            total += count

    return {
        "status": "ok",
        "classes": stats,
        "counts": stats,
        "total_images": total,
        "dataset_path": str(DATASET_RAW_DIR)
    }


def save_captured_frame(class_name: str, frame_bgr) -> dict:
    """
    Lưu 1 frame ảnh vào thư mục class tương ứng trong dataset_raw.
    """
    ensure_dataset_dirs()
    target_dir = DATASET_RAW_DIR / class_name
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time() * 1000)
    filename = f"{class_name}_{timestamp}.jpg"
    filepath = target_dir / filename

    success = cv2.imwrite(str(filepath), frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if success:
        return {
            "status": "ok",
            "success": True,
            "filename": filename,
            "class_name": class_name,
            "filepath": str(filepath)
        }
    return {
        "status": "error",
        "success": False,
        "error": "Không thể lưu ảnh xuống đĩa."
    }


def delete_captured_image(class_name: str, filename: str) -> dict:
    """Xóa 1 ảnh cụ thể khỏi dataset_raw."""
    filepath = None
    if class_name:
        candidate = DATASET_RAW_DIR / class_name / filename
        if candidate.exists() and candidate.is_file():
            filepath = candidate
    
    if not filepath:
        # Tìm trong tất cả các thư mục con
        for cd in DATASET_RAW_DIR.iterdir():
            if cd.is_dir():
                candidate = cd / filename
                if candidate.exists() and candidate.is_file():
                    filepath = candidate
                    break

    if filepath and filepath.exists() and filepath.is_file():
        try:
            filepath.unlink()
            return {"status": "ok", "success": True, "deleted": filename}
        except Exception as e:
            return {"status": "error", "success": False, "error": str(e)}
    return {"status": "error", "success": False, "error": "Tập tin không tồn tại"}


def add_new_class(class_name: str) -> dict:
    """Tạo thêm nhãn phân loại mới."""
    cleaned = class_name.strip().replace(" ", "_").lower()
    if not cleaned:
        return {"status": "error", "success": False, "error": "Tên nhãn không hợp lệ"}

    target_dir = DATASET_RAW_DIR / cleaned
    target_dir.mkdir(parents=True, exist_ok=True)
    return {"status": "ok", "success": True, "class_name": cleaned}


def get_recent_captures(limit=16) -> list:
    """Lấy danh sách các ảnh chụp gần đây nhất để hiển thị thumbnail."""
    ensure_dataset_dirs()
    all_images = []
    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    for class_dir in DATASET_RAW_DIR.iterdir():
        if class_dir.is_dir():
            for f in class_dir.iterdir():
                if f.is_file() and f.suffix.lower() in valid_exts:
                    all_images.append({
                        "class_name": class_dir.name,
                        "filename": f.name,
                        "url": f"/api/dataset/image/{class_dir.name}/{f.name}",
                        "mtime": f.stat().st_mtime
                    })

    all_images.sort(key=lambda x: x["mtime"], reverse=True)
    return all_images[:limit]
