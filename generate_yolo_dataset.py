"""
Script Tự Động Tạo Dataset Object Detection (YOLO Format) từ dataset_raw:
- Tự động tách các khối cube (xanh, đỏ, vàng, lục) từ ảnh gốc.
- Tạo các bức ảnh bối cảnh chứa từ 1 đến 4 cube cùng lúc trên mặt bàn.
- Tự động nạp các ảnh Background / Negative samples từ dataset_raw/background và tạo file nhãn .txt rỗng (0 bytes) chuẩn YOLO để chống nhận diện nhầm.
- Tạo file cấu hình data.yaml sẵn sàng cho YOLOv8/v11 huấn luyện.
"""

import os
import sys
import shutil
import random
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
import numpy as np
from tqdm import tqdm


CUBE_CLASSES = ["cube_blue", "cube_green", "cube_red", "cube_yellow"]


def extract_cube_patch(img, class_name):
    """Tự động phân đoạn và tách cube bằng không gian màu HSV + Contour."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    if "blue" in class_name:
        mask = cv2.inRange(hsv, np.array([90, 70, 50]), np.array([135, 255, 255]))
    elif "green" in class_name:
        mask = cv2.inRange(hsv, np.array([35, 70, 50]), np.array([85, 255, 255]))
    elif "yellow" in class_name:
        mask = cv2.inRange(hsv, np.array([15, 80, 80]), np.array([38, 255, 255]))
    elif "red" in class_name:
        m1 = cv2.inRange(hsv, np.array([0, 70, 50]), np.array([10, 255, 255]))
        m2 = cv2.inRange(hsv, np.array([168, 70, 50]), np.array([180, 255, 255]))
        mask = cv2.bitwise_or(m1, m2)
    else:
        return None

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None

    c = max(cnts, key=cv2.contourArea)
    # Hạ ngưỡng diện tích từ 3000 xuống 800 để giữ lại cả các khối cube chụp ở cự ly xa
    if cv2.contourArea(c) < 800:
        return None

    x, y, w, h = cv2.boundingRect(c)
    patch_img = img[y : y + h, x : x + w]
    patch_mask = mask[y : y + h, x : x + w]
    return patch_img, patch_mask


def apply_finger_occlusion(patch_img):
    """Giả lập ngón tay người cầm vào mép/góc cube bằng các đốm màu da."""
    if random.random() > 0.40:
        return patch_img

    h, w = patch_img.shape[:2]
    out_img = patch_img.copy()

    # Các tông màu da người phổ biến (BGR)
    skin_colors = [
        (130, 160, 215),  # Da sáng hồng
        (105, 145, 200),  # Da vàng châu Á
        (85, 120, 175),   # Da rám nắng
        (75, 100, 150),   # Da ngăm
    ]

    num_fingers = random.choice([1, 2])
    for _ in range(num_fingers):
        skin_bgr = list(random.choice(skin_colors))
        skin_bgr = [int(np.clip(c + random.randint(-15, 15), 0, 255)) for c in skin_bgr]

        edge = random.choice(["top", "bottom", "left", "right"])
        finger_w = random.randint(max(8, int(w * 0.18)), max(12, int(w * 0.38)))
        finger_h = random.randint(max(8, int(h * 0.18)), max(12, int(h * 0.38)))

        if edge == "top":
            cx = random.randint(finger_w // 2, max(finger_w // 2 + 1, w - finger_w // 2))
            cy = random.randint(0, max(1, int(h * 0.25)))
        elif edge == "bottom":
            cx = random.randint(finger_w // 2, max(finger_w // 2 + 1, w - finger_w // 2))
            cy = random.randint(min(h - 1, int(h * 0.75)), h)
        elif edge == "left":
            cx = random.randint(0, max(1, int(w * 0.25)))
            cy = random.randint(finger_h // 2, max(finger_h // 2 + 1, h - finger_h // 2))
        else:
            cx = random.randint(min(w - 1, int(w * 0.75)), w)
            cy = random.randint(finger_h // 2, max(finger_h // 2 + 1, h - finger_h // 2))

        cv2.ellipse(
            out_img,
            (cx, cy),
            (finger_w // 2, finger_h // 2),
            random.randint(-45, 45),
            0,
            360,
            skin_bgr,
            -1,
        )

    return out_img


def apply_sensor_jitter(patch_img):
    """Giả lập sự khác biệt cảm biến/cân bằng trắng giữa camera laptop (nhạt, lệch màu) và camera ngoài."""
    hsv = cv2.cvtColor(patch_img, cv2.COLOR_BGR2HSV).astype(np.float32)
    # Lệch nhẹ Hue (-6 đến +6)
    hsv[:, :, 0] = (hsv[:, :, 0] + random.uniform(-6, 6)) % 180
    # Thay đổi độ bão hòa (0.50x đến 1.35x) để nhận diện cả camera nhạt màu của laptop
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * random.uniform(0.50, 1.35), 0, 255)
    # Thay đổi độ sáng (0.65x đến 1.30x)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * random.uniform(0.65, 1.30), 0, 255)

    jittered = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    # 25% làm mờ nhẹ (mô phỏng cam laptop tiêu cự kém hoặc chuyển động)
    if random.random() < 0.25:
        jittered = cv2.GaussianBlur(jittered, (3, 3), 0)
    return jittered


def get_clean_background(sample_img):
    """Tạo phông nền bàn làm việc sạch từ ảnh gốc bằng cách lấy mẫu viền mép bàn."""
    h, w = sample_img.shape[:2]
    border_samples = np.concatenate([
        sample_img[:50, :].reshape(-1, 3),
        sample_img[-50:, :].reshape(-1, 3),
        sample_img[:, :50].reshape(-1, 3),
        sample_img[:, -50:].reshape(-1, 3),
    ], axis=0)

    mean_color = border_samples.mean(axis=0).astype(np.uint8)
    bg = np.full((h, w, 3), mean_color, dtype=np.uint8)
    noise = np.random.normal(0, 5, (h, w, 3)).astype(np.int16)
    return np.clip(bg.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def check_overlap(box1, box2, iou_thresh=0.15):
    """Kiểm tra độ đè lấn (IOU) giữa 2 hộp bounding box."""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2

    xi1 = max(x1, x2)
    yi1 = max(y1, y2)
    xi2 = min(x1 + w1, x2 + w2)
    yi2 = min(y1 + h1, y2 + h2)

    inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    if inter_area == 0:
        return False

    box1_area = w1 * h1
    box2_area = w2 * h2
    iou = inter_area / float(box1_area + box2_area - inter_area)
    return iou > iou_thresh


def generate_synthetic_scene(cube_library, bg_template, real_bg_list=None, min_cubes=1, max_cubes=4):
    """Tạo 1 bức ảnh bối cảnh chứa nhiều cube với tọa độ Bounding Box chính xác."""
    # 50% sử dụng ảnh nền thật từ raw/background nếu có, 50% dùng nền bàn sạch
    if real_bg_list and random.random() < 0.50:
        bg_source = random.choice(real_bg_list)
        scene = cv2.resize(bg_source, (bg_template.shape[1], bg_template.shape[0]))
    else:
        scene = bg_template.copy()

    h_bg, w_bg = scene.shape[:2]

    alpha = random.uniform(0.85, 1.15)
    beta = random.uniform(-20, 20)
    scene = cv2.convertScaleAbs(scene, alpha=alpha, beta=beta)

    num_objects = random.randint(min_cubes, max_cubes)
    chosen_classes = random.sample(CUBE_CLASSES, min(num_objects, len(CUBE_CLASSES)))

    placed_boxes = []
    yolo_labels = []

    for cls_name in chosen_classes:
        class_id = CUBE_CLASSES.index(cls_name)
        patch_list = cube_library.get(cls_name, [])
        if not patch_list:
            continue

        patch_img, patch_mask = random.choice(patch_list)
        ph, pw = patch_img.shape[:2]

        # Giới hạn kích thước tối đa không vượt quá 50% khung hình nền
        max_allowed_w = int(w_bg * 0.50)
        max_allowed_h = int(h_bg * 0.50)

        # Mở rộng dải scale (0.18x - 1.15x) để học cả cube xa (nhỏ) và gần (lớn)
        scale = random.uniform(0.18, 1.15)
        new_w = int(pw * scale)
        new_h = int(ph * scale)

        if new_w > max_allowed_w or new_h > max_allowed_h:
            fit_ratio = min(max_allowed_w / max(1, new_w), max_allowed_h / max(1, new_h))
            new_w = int(new_w * fit_ratio)
            new_h = int(new_h * fit_ratio)

        new_w = max(28, new_w)
        new_h = max(28, new_h)

        max_x = w_bg - new_w - 10
        max_y = h_bg - new_h - 10
        if max_x <= 10 or max_y <= 10:
            continue

        scaled_patch = cv2.resize(patch_img, (new_w, new_h))
        scaled_mask = cv2.resize(patch_mask, (new_w, new_h))

        # 1. Giả lập ngón tay cầm cube
        scaled_patch = apply_finger_occlusion(scaled_patch)

        # 2. Giả lập lệch màu / độ bão hòa cảm biến (laptop vs ngoài)
        scaled_patch = apply_sensor_jitter(scaled_patch)

        if random.random() < 0.5:
            scaled_patch = cv2.flip(scaled_patch, 1)
            scaled_mask = cv2.flip(scaled_mask, 1)

        angle = random.uniform(-25, 25)
        center = (new_w / 2.0, new_h / 2.0)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        scaled_patch = cv2.warpAffine(scaled_patch, M, (new_w, new_h), borderMode=cv2.BORDER_CONSTANT)
        scaled_mask = cv2.warpAffine(scaled_mask, M, (new_w, new_h), borderMode=cv2.BORDER_CONSTANT)

        placed = False
        for _ in range(30):
            px = random.randint(10, max_x)
            py = random.randint(10, max_y)
            candidate_box = (px, py, new_w, new_h)
            if not any(check_overlap(candidate_box, b) for b in placed_boxes):
                placed = True
                break

        if not placed:
            continue

        placed_boxes.append((px, py, new_w, new_h))

        mask_norm = (scaled_mask.astype(np.float32) / 255.0)[:, :, np.newaxis]
        roi = scene[py : py + new_h, px : px + new_w]
        blended = (scaled_patch * mask_norm + roi * (1.0 - mask_norm)).astype(np.uint8)
        scene[py : py + new_h, px : px + new_w] = blended

        x_center = (px + new_w / 2.0) / w_bg
        y_center = (py + new_h / 2.0) / h_bg
        norm_w = new_w / w_bg
        norm_h = new_h / h_bg
        yolo_labels.append(f"{class_id} {x_center:.6f} {y_center:.6f} {norm_w:.6f} {norm_h:.6f}")

    return scene, yolo_labels


def main():
    parser = argparse.ArgumentParser(
        description="Tự động tạo dataset YOLO kèm ảnh Negative Background (file .txt rỗng 0 bytes)."
    )
    parser.add_argument("--raw", type=str, default="dataset_raw", help="Thư mục raw data")
    parser.add_argument("--output", type=str, default="yolo_dataset", help="Thư mục xuất dataset YOLO")
    parser.add_argument("--train-count", type=int, default=500, help="Số lượng ảnh huấn luyện (train)")
    parser.add_argument("--val-count", type=int, default=100, help="Số lượng ảnh kiểm định (val)")

    args = parser.parse_args()

    raw_dir = Path(args.raw)
    output_dir = Path(args.output)

    # 1. Trích xuất Cube Patches từ raw images
    print("[*] Đang phân tích và trích xuất các cube từ dataset_raw...")
    cube_library = {}
    sample_bg_img = None

    for cls_name in CUBE_CLASSES:
        cls_folder = raw_dir / cls_name
        if not cls_folder.exists():
            continue
        images = list(cls_folder.glob("*.jpg")) + list(cls_folder.glob("*.png"))
        patches = []
        for img_path in images:
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            if sample_bg_img is None:
                sample_bg_img = img

            res = extract_cube_patch(img, cls_name)
            if res is not None:
                patches.append(res)

        cube_library[cls_name] = patches
        print(f"  -> [{cls_name}]: Trích xuất được {len(patches)} mẫu cube sạch.")

    if not any(cube_library.values()):
        print("[!] Không trích xuất được cube nào từ dataset_raw. Vui lòng kiểm tra lại ảnh chụp!")
        return

    # Nạp danh sách ảnh nền thật (nếu có)
    bg_folder = raw_dir / "background"
    real_bg_list = []
    if bg_folder.exists():
        for p in list(bg_folder.glob("*.jpg")) + list(bg_folder.glob("*.png")):
            b_im = cv2.imread(str(p))
            if b_im is not None:
                real_bg_list.append(b_im)
        print(f"[*] Đã tải {len(real_bg_list)} ảnh nền thật từ {bg_folder} để trộn bối cảnh thực tế.")

    # 2. Xóa và làm mới thư mục output
    if output_dir.exists():
        shutil.rmtree(output_dir)

    train_img_dir = output_dir / "images" / "train"
    train_lbl_dir = output_dir / "labels" / "train"
    val_img_dir = output_dir / "images" / "val"
    val_lbl_dir = output_dir / "labels" / "val"

    for d in [train_img_dir, train_lbl_dir, val_img_dir, val_lbl_dir]:
        d.mkdir(parents=True, exist_ok=True)

    bg_template = get_clean_background(sample_bg_img)

    # 3. Sinh ảnh tổng hợp Cube cho Train & Val (kèm dải scale xa/gần, ngón tay, jitter màu)
    print(f"\n[*] Đang tổng hợp {args.train_count} ảnh Train (chứa 1-4 cube, đa cự ly, ngón tay cầm)...")
    for i in tqdm(range(args.train_count), desc="  Sinh ảnh Train Cube"):
        scene_img, labels = generate_synthetic_scene(
            cube_library, bg_template, real_bg_list=real_bg_list, min_cubes=1, max_cubes=4
        )
        base_name = f"syn_train_{i+1:05d}"
        cv2.imwrite(str(train_img_dir / f"{base_name}.jpg"), scene_img)
        with open(train_lbl_dir / f"{base_name}.txt", "w") as f:
            f.write("\n".join(labels))

    print(f"[*] Đang tổng hợp {args.val_count} ảnh Val Cube...")
    for i in tqdm(range(args.val_count), desc="  Sinh ảnh Val Cube"):
        scene_img, labels = generate_synthetic_scene(
            cube_library, bg_template, real_bg_list=real_bg_list, min_cubes=1, max_cubes=4
        )
        base_name = f"syn_val_{i+1:05d}"
        cv2.imwrite(str(val_img_dir / f"{base_name}.jpg"), scene_img)
        with open(val_lbl_dir / f"{base_name}.txt", "w") as f:
            f.write("\n".join(labels))

    # 4. Tự động nạp ảnh Background (Negative Samples) và tạo FILE NHÃN RỖNG (0 BYTES)
    bg_files = []
    if bg_folder.exists():
        bg_files = list(bg_folder.glob("*.jpg")) + list(bg_folder.glob("*.png"))

    if bg_files:
        random.shuffle(bg_files)
        # Chia 80% train, 20% val
        split_idx = int(len(bg_files) * 0.8)
        bg_train = bg_files[:split_idx]
        bg_val = bg_files[split_idx:]

        print(f"\n[*] Đang thêm {len(bg_files)} ảnh BACKGROUND (Negative Samples) với file nhãn 0 BYTES...")
        for i, fpath in enumerate(bg_train):
            out_name = f"bg_neg_train_{i+1:04d}"
            shutil.copy2(fpath, train_img_dir / f"{out_name}.jpg")
            # Tạo file .txt rỗng hoàn toàn (0 KB / 0 bytes)
            with open(train_lbl_dir / f"{out_name}.txt", "w") as f:
                pass

        for i, fpath in enumerate(bg_val):
            out_name = f"bg_neg_val_{i+1:04d}"
            shutil.copy2(fpath, val_img_dir / f"{out_name}.jpg")
            # Tạo file .txt rỗng hoàn toàn (0 KB / 0 bytes)
            with open(val_lbl_dir / f"{out_name}.txt", "w") as f:
                pass

        print(f"  -> Đã thêm {len(bg_train)} ảnh Background vào tập Train (file .txt rỗng 0 bytes)")
        print(f"  -> Đã thêm {len(bg_val)} ảnh Background vào tập Val (file .txt rỗng 0 bytes)")
    else:
        print("\n[!] Không tìm thấy thư mục 'dataset_raw/background'. Bỏ qua ảnh âm tính.")

    # 5. Tạo file data.yaml cho YOLO
    yaml_content = f"""path: {output_dir.resolve().as_posix()}
train: images/train
val: images/val

names:
  0: cube_blue
  1: cube_green
  2: cube_red
  3: cube_yellow
"""
    with open(output_dir / "data.yaml", "w", encoding="utf-8") as f:
        f.write(yaml_content)

    print("\n" + "=" * 60)
    print(" ĐÃ TẠO XONG DATASET OBJECT DETECTION ĐẦY ĐỦ:")
    print(f" - Thư mục: {output_dir.resolve()}")
    print(f" - Tổng ảnh Train : {args.train_count + len(bg_train if bg_files else [])} ảnh")
    print(f" - Tổng ảnh Val   : {args.val_count + len(bg_val if bg_files else [])} ảnh")
    print(f" - Số file nhãn 0 bytes (Background): {len(bg_files)} file")
    print(f" - File config    : {output_dir / 'data.yaml'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
