"""
Script Image Augmentation cho Object Detection / Teachable Machine.
Hỗ trợ tạo ra nhiều biến thể từ 1 hoặc nhiều ảnh chụp vật thể (ví dụ: khối cube màu).
"""

import os
import sys
import glob
import random
import argparse
from pathlib import Path

# Đảm bảo in tiếng Việt mượt mà trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import cv2
import numpy as np
from tqdm import tqdm


class ImageAugmentor:
    def __init__(
        self,
        rotation_range=35,
        zoom_range=(0.75, 1.25),
        shift_ratio=0.12,
        warp_ratio=0.08,
        brightness_range=(0.65, 1.35),
        contrast_range=(0.7, 1.3),
        allow_flip_h=True,
        allow_flip_v=False,
        allow_hue_shift=False,
        hue_shift_limit=8,  # Giới hạn đổi màu nhỏ (để cube đỏ không thành xanh)
        noise_prob=0.35,
        blur_prob=0.3,
        cutout_prob=0.25,
    ):
        self.rotation_range = rotation_range
        self.zoom_range = zoom_range
        self.shift_ratio = shift_ratio
        self.warp_ratio = warp_ratio
        self.brightness_range = brightness_range
        self.contrast_range = contrast_range
        self.allow_flip_h = allow_flip_h
        self.allow_flip_v = allow_flip_v
        self.allow_hue_shift = allow_hue_shift
        self.hue_shift_limit = hue_shift_limit
        self.noise_prob = noise_prob
        self.blur_prob = blur_prob
        self.cutout_prob = cutout_prob

    def random_affine_transform(self, img):
        """Xoay, thu phóng (zoom) và dịch chuyển (translation) đồng thời."""
        h, w = img.shape[:2]
        center = (w / 2.0, h / 2.0)

        angle = random.uniform(-self.rotation_range, self.rotation_range)
        scale = random.uniform(self.zoom_range[0], self.zoom_range[1])

        # Ma trận xoay + zoom
        rot_mat = cv2.getRotationMatrix2D(center, angle, scale)

        # Dịch chuyển (translation)
        dx = random.uniform(-self.shift_ratio, self.shift_ratio) * w
        dy = random.uniform(-self.shift_ratio, self.shift_ratio) * h
        rot_mat[0, 2] += dx
        rot_mat[1, 2] += dy

        transformed = cv2.warpAffine(
            img,
            rot_mat,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )
        return transformed

    def random_perspective(self, img):
        """Mô phỏng góc chụp nghiêng của camera (perspective warp)."""
        h, w = img.shape[:2]
        warp = self.warp_ratio

        src_pts = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
        dst_pts = np.float32(
            [
                [
                    random.uniform(0, warp * w),
                    random.uniform(0, warp * h),
                ],
                [
                    w - 1 - random.uniform(0, warp * w),
                    random.uniform(0, warp * h),
                ],
                [
                    w - 1 - random.uniform(0, warp * w),
                    h - 1 - random.uniform(0, warp * h),
                ],
                [
                    random.uniform(0, warp * w),
                    h - 1 - random.uniform(0, warp * h),
                ],
            ]
        )

        matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(
            img,
            matrix,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )
        return warped

    def random_flips(self, img):
        """Lật ảnh ngang/dọc."""
        if self.allow_flip_h and random.random() < 0.5:
            img = cv2.flip(img, 1)
        if self.allow_flip_v and random.random() < 0.3:
            img = cv2.flip(img, 0)
        return img

    def adjust_light_and_color(self, img):
        """Mô phỏng các điều kiện ánh sáng camera khác nhau (độ sáng, tương phản, độ bão hòa màu)."""
        # Độ tương phản (contrast) và độ sáng (brightness)
        alpha = random.uniform(self.contrast_range[0], self.contrast_range[1])
        beta = random.uniform(
            (self.brightness_range[0] - 1.0) * 100,
            (self.brightness_range[1] - 1.0) * 100,
        )
        img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)

        # Chuyển sang HSV để điều chỉnh độ rực rỡ và tông màu
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
        h, s, v = cv2.split(hsv)

        # Thay đổi độ bão hòa (Saturation) 70% - 130%
        sat_mult = random.uniform(0.7, 1.3)
        s = np.clip(s * sat_mult, 0, 255)

        # Đổi hue nhẹ nếu cho phép (lưu ý: với bài toán nhận diện màu sắc như cube, hue không nên đổi quá nhiều)
        if self.allow_hue_shift:
            dh = random.uniform(-self.hue_shift_limit, self.hue_shift_limit)
            h = (h + dh) % 180

        hsv = cv2.merge([h, s, v]).astype(np.uint8)
        img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        return img

    def add_noise(self, img):
        """Mô phỏng nhiễu hạt sensor camera (Gaussian noise)."""
        if random.random() < self.noise_prob:
            mean = 0
            var = random.uniform(10, 35)
            sigma = var**0.5
            gaussian = np.random.normal(mean, sigma, img.shape).astype(np.float32)
            noisy_img = img.astype(np.float32) + gaussian
            img = np.clip(noisy_img, 0, 255).astype(np.uint8)
        return img

    def add_blur(self, img):
        """Mô phỏng camera lấy nét chưa chuẩn hoặc vật thể chuyển động mờ (motion / focus blur)."""
        if random.random() < self.blur_prob:
            k = random.choice([3, 5])
            if random.random() < 0.5:
                img = cv2.GaussianBlur(img, (k, k), 0)
            else:
                img = cv2.medianBlur(img, k)
        return img

    def random_cutout(self, img):
        """Mô phỏng vật thể bị che khuất 1 phần (occlusion)."""
        if random.random() < self.cutout_prob:
            h, w = img.shape[:2]
            mask_size = int(random.uniform(0.08, 0.2) * min(h, w))
            cx = random.randint(0, w - mask_size)
            cy = random.randint(0, h - mask_size)
            # Dùng màu trung bình ảnh hoặc màu xám ngẫu nhiên
            color = [random.randint(50, 200) for _ in range(3)]
            img[cy : cy + mask_size, cx : cx + mask_size] = color
        return img

    def augment(self, img):
        """Thực hiện một chuỗi augmentation ngẫu nhiên."""
        res = img.copy()

        # 1. Hình học (Affine: Xoay, Zoom, Di chuyển)
        res = self.random_affine_transform(res)

        # 2. Phối cảnh (Perspective)
        if random.random() < 0.7:
            res = self.random_perspective(res)

        # 3. Lật ảnh (Flip)
        res = self.random_flips(res)

        # 4. Ánh sáng & Màu sắc
        res = self.adjust_light_and_color(res)

        # 5. Mờ (Blur) & Nhiễu (Noise)
        res = self.add_blur(res)
        res = self.add_noise(res)

        # 6. Che khuất 1 phần (Cutout)
        res = self.random_cutout(res)

        return res


def get_image_files(folder_path):
    """Tìm tất cả các file ảnh hợp lệ trong thư mục."""
    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    folder = Path(folder_path)
    return [p for p in folder.iterdir() if p.suffix.lower() in valid_exts and p.is_file()]


def process_single_image(image_path, output_dir, count, augmentor):
    """Augment 1 ảnh thành `count` ảnh mới."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    img = cv2.imread(str(image_path))
    if img is None:
        print(f"[Lỗi] Không đọc được ảnh: {image_path}")
        return 0

    base_name = Path(image_path).stem
    ext = Path(image_path).suffix or ".jpg"

    # Lưu cả ảnh gốc
    cv2.imwrite(str(output_dir / f"{base_name}_orig{ext}"), img)

    for i in range(count):
        aug_img = augmentor.augment(img)
        save_name = output_dir / f"{base_name}_aug_{i+1:04d}{ext}"
        cv2.imwrite(str(save_name), aug_img)

    return count + 1


def process_dataset_folder(input_dir, output_dir, samples_per_class, augmentor):
    """
    Xử lý theo cấu trúc thư mục phân loại Teachable Machine:
    input_dir/
        class_blue_cube/
            cube1.jpg
        class_red_cube/
            cube2.jpg
    Output:
    output_dir/
        class_blue_cube/
            (samples_per_class ảnh đã augment)
        class_red_cube/
            (samples_per_class ảnh đã augment)
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    subdirs = [p for p in input_path.iterdir() if p.is_dir()]

    if not subdirs:
        # Nếu không có thư mục con, coi toàn bộ input_dir như 1 class
        images = get_image_files(input_path)
        if not images:
            print(f"[!] Không tìm thấy ảnh nào trong: {input_dir}")
            return

        print(f"Tìm thấy {len(images)} ảnh gốc trong {input_dir}. Đang augment {samples_per_class} ảnh...")
        output_path.mkdir(parents=True, exist_ok=True)

        for i in tqdm(range(samples_per_class), desc="Đang tạo ảnh"):
            chosen_img_path = random.choice(images)
            src_img = cv2.imread(str(chosen_img_path))
            if src_img is None:
                continue
            aug_img = augmentor.augment(src_img)
            out_name = output_path / f"aug_{i+1:04d}.jpg"
            cv2.imwrite(str(out_name), aug_img)
        return

    # Nếu có các subfolder ứng với từng class (VD: blue_cube, red_cube,...)
    print(f"Phát hiện {len(subdirs)} class (thư mục nhãn): {[s.name for s in subdirs]}")
    for class_folder in subdirs:
        class_name = class_folder.name
        class_images = get_image_files(class_folder)

        if not class_images:
            print(f"[-] Bỏ qua '{class_name}' vì không có ảnh gốc nào.")
            continue

        class_out_dir = output_path / class_name
        class_out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[+] Class '{class_name}': {len(class_images)} ảnh gốc -> sinh {samples_per_class} ảnh...")

        # Giữ lại các ảnh gốc vào output
        for orig in class_images:
            cv2.imwrite(str(class_out_dir / orig.name), cv2.imread(str(orig)))

        # Sinh các ảnh augment
        pbar = tqdm(total=samples_per_class, desc=f"  Tạo {class_name}")
        created = 0
        while created < samples_per_class:
            chosen = random.choice(class_images)
            src = cv2.imread(str(chosen))
            if src is None:
                continue
            aug_img = augmentor.augment(src)
            out_file = class_out_dir / f"aug_{created+1:04d}.jpg"
            cv2.imwrite(str(out_file), aug_img)
            created += 1
            pbar.update(1)
        pbar.close()


def main():
    parser = argparse.ArgumentParser(
        description="Tool Data Augmentation tự động cho bài toán nhận diện vật thể / Teachable Machine."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="dataset_raw",
        help="Đường dẫn tới thư mục ảnh gốc hoặc file ảnh lẻ (mặc định: dataset_raw)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="dataset_augmented",
        help="Đường dẫn thư mục lưu ảnh augment (mặc định: dataset_augmented)",
    )
    parser.add_argument(
        "--count",
        "-n",
        type=int,
        default=60,
        help="Số lượng ảnh augment cần sinh cho mỗi class / mỗi ảnh (mặc định: 60)",
    )
    parser.add_argument(
        "--allow-hue-shift",
        action="store_true",
        help="Cho phép đổi nhẹ tông màu (LƯU Ý: Không nên bật nếu màu sắc là đặc trưng nhãn như cube đỏ/xanh).",
    )
    parser.add_argument(
        "--rotation",
        type=int,
        default=35,
        help="Góc xoay tối đa (+/- degrees, mặc định: 35)",
    )

    args = parser.parse_args()

    augmentor = ImageAugmentor(
        rotation_range=args.rotation,
        allow_hue_shift=args.allow_hue_shift,
    )

    input_path = Path(args.input)

    # Nếu truyền vào 1 file ảnh cụ thể
    if input_path.is_file():
        print(f"Đang augment ảnh đơn: {input_path}")
        total = process_single_image(input_path, args.output, args.count, augmentor)
        print(f"\n[Hoàn thành] Đã tạo {total} ảnh trong thư mục '{args.output}'.")
    elif input_path.is_dir():
        process_dataset_folder(input_path, args.output, args.count, augmentor)
        print(f"\n[Hoàn thành] Dữ liệu đã sẵn sàng tại thư mục: '{args.output}'.")
    else:
        print(f"[!] Đường dẫn '{args.input}' chưa tồn tại.")
        print("Tạo thư mục mẫu cho bạn...")
        # Tạo sẵn cấu trúc mẫu
        Path("dataset_raw/cube_blue").mkdir(parents=True, exist_ok=True)
        Path("dataset_raw/cube_red").mkdir(parents=True, exist_ok=True)
        Path("dataset_raw/cube_yellow").mkdir(parents=True, exist_ok=True)
        print(
            "Đã tạo các thư mục mẫu:\n"
            "  dataset_raw/\n"
            "    ├── cube_blue/\n"
            "    ├── cube_red/\n"
            "    └── cube_yellow/\n"
            "Hãy thả ảnh chụp vật thể vào các thư mục trên rồi chạy lại lệnh!"
        )


if __name__ == "__main__":
    main()
