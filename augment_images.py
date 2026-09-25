"""
Script Image Augmentation Nâng Cao & Toàn Diện cho Object Detection / Teachable Machine.
Tích hợp các kỹ thuật Augmentation hàng đầu từ các mô hình YOLO (YOLOv5/v8/v11) & Deep Learning:
1. YOLO Mosaic 4-in-1: Ghép 4 ảnh tại tâm giao ngẫu nhiên (đa góc, đa tỉ lệ).
2. YOLO Mosaic 9-in-1: Ghép 9 ảnh (lưới 3x3) mô phỏng phát hiện vật thể nhỏ từ xa.
3. CutMix: Cắt một phần từ ảnh này dán đè lên ảnh kia (mô phỏng che khuất thực tế).
4. MixUp: Hòa trộn alpha giữa 2 ảnh để tăng tính tổng quát hóa cho mô hình.
5. Random Shadow: Mô phỏng bóng râm / bóng tay người che khuất khi thao tác.
6. Multi-scale Placement: Thu nhỏ vật thể (0.4x - 0.8x) và di chuyển khắp các góc, mép bàn.
7. Biến dạng không gian 3D: Perspective Warp, Rotation, Flip.
8. Ánh sáng thực tế: Brightness, Contrast, Saturation, Sensor Noise, Motion Blur.
9. Bảo toàn tông màu (Hue): Đảm bảo các màu cube (đỏ, xanh, vàng, tím) không bị biến sắc.
"""

import os
import sys
import glob
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


class AdvancedDetectionAugmentor:
    def __init__(
        self,
        rotation_range=30,
        zoom_range=(0.4, 1.25),
        brightness_range=(0.65, 1.35),
        contrast_range=(0.7, 1.3),
        allow_flip_h=True,
        allow_flip_v=False,
        allow_hue_shift=False,
        hue_shift_limit=8,
        noise_prob=0.35,
        blur_prob=0.3,
        shadow_prob=0.4,
    ):
        self.rotation_range = rotation_range
        self.zoom_range = zoom_range
        self.brightness_range = brightness_range
        self.contrast_range = contrast_range
        self.allow_flip_h = allow_flip_h
        self.allow_flip_v = allow_flip_v
        self.allow_hue_shift = allow_hue_shift
        self.hue_shift_limit = hue_shift_limit
        self.noise_prob = noise_prob
        self.blur_prob = blur_prob
        self.shadow_prob = shadow_prob

    # =========================================================================
    # 1. BIẾN ĐỔI VỊ TRÍ, GÓC & TỈ LỆ (MULTI-SCALE & CORNER PLACEMENT)
    # =========================================================================
    def random_position_and_scale(self, img):
        """Thu phóng đa tỉ lệ và di chuyển vật thể ra góc/mép hoặc bất kỳ đâu."""
        h, w = img.shape[:2]
        center = (w / 2.0, h / 2.0)

        # Chọn scale ngẫu nhiên từ nhỏ (0.4x) đến lớn (1.25x)
        scale = random.uniform(self.zoom_range[0], self.zoom_range[1])
        angle = random.uniform(-self.rotation_range, self.rotation_range)

        # Biên độ dịch chuyển phụ thuộc vào scale
        # Vật thể càng nhỏ thì càng di chuyển xa được ra mép ngoài
        max_shift_x = 0.35 * (1.3 - min(scale, 1.0)) * w
        max_shift_y = 0.30 * (1.3 - min(scale, 1.0)) * h

        dx = random.uniform(-max_shift_x, max_shift_x)
        dy = random.uniform(-max_shift_y, max_shift_y)

        rot_mat = cv2.getRotationMatrix2D(center, angle, scale)
        rot_mat[0, 2] += dx
        rot_mat[1, 2] += dy

        return cv2.warpAffine(
            img, rot_mat, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101
        )

    def random_perspective(self, img):
        """Mô phỏng góc nghiêng 3D của camera so với mặt phẳng bàn."""
        h, w = img.shape[:2]
        warp = 0.08
        src_pts = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
        dst_pts = np.float32(
            [
                [random.uniform(0, warp * w), random.uniform(0, warp * h)],
                [w - 1 - random.uniform(0, warp * w), random.uniform(0, warp * h)],
                [w - 1 - random.uniform(0, warp * w), h - 1 - random.uniform(0, warp * h)],
                [random.uniform(0, warp * w), h - 1 - random.uniform(0, warp * h)],
            ]
        )
        matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        return cv2.warpPerspective(
            img, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101
        )

    def random_flips(self, img):
        """Lật ảnh đối xứng."""
        if self.allow_flip_h and random.random() < 0.5:
            img = cv2.flip(img, 1)
        if self.allow_flip_v and random.random() < 0.15:
            img = cv2.flip(img, 0)
        return img

    # =========================================================================
    # 2. CÁC KỸ THUẬT SIÊU TĂNG CƯỜNG HIỆN ĐẠI (YOLO MOSAIC, CUTMIX, MIXUP)
    # =========================================================================
    def generate_mosaic_4(self, image_list):
        """
        YOLO Mosaic 4-in-1:
        Ghép 4 ảnh tại 1 điểm giao ngẫu nhiên (xc, yc),
        tạo ra bức ảnh có 4 phân vùng ở các tỉ lệ và góc nhìn khác nhau.
        """
        chosen_4 = [random.choice(image_list) for _ in range(4)]
        loaded_4 = [cv2.imread(str(p)) for p in chosen_4]
        h, w = loaded_4[0].shape[:2]

        xc = int(random.uniform(0.35 * w, 0.65 * w))
        yc = int(random.uniform(0.35 * h, 0.65 * h))

        mosaic_img = np.zeros((h, w, 3), dtype=np.uint8)
        quadrants = [
            (0, 0, xc, yc),
            (xc, 0, w, yc),
            (0, yc, xc, h),
            (xc, yc, w, h),
        ]

        for i, (qx1, qy1, qx2, qy2) in enumerate(quadrants):
            qw, qh = qx2 - qx1, qy2 - qy1
            scaled = cv2.resize(loaded_4[i], (qw, qh))
            if self.allow_flip_h and random.random() < 0.5:
                scaled = cv2.flip(scaled, 1)
            mosaic_img[qy1:qy2, qx1:qx2] = scaled

        return mosaic_img

    def generate_mosaic_9(self, image_list):
        """
        YOLO Mosaic 9-in-1:
        Ghép 9 ảnh vào lưới 3x3 để mô phỏng vật thể kích thước nhỏ ở khoảng cách xa.
        """
        chosen_9 = [random.choice(image_list) for _ in range(9)]
        loaded_9 = [cv2.imread(str(p)) for p in chosen_9]
        h, w = loaded_9[0].shape[:2]

        # 2 đường chia ngang và dọc ngẫu nhiên
        x1 = int(random.uniform(0.28 * w, 0.38 * w))
        x2 = int(random.uniform(0.62 * w, 0.72 * w))
        y1 = int(random.uniform(0.28 * h, 0.38 * h))
        y2 = int(random.uniform(0.62 * h, 0.72 * h))

        xs = [0, x1, x2, w]
        ys = [0, y1, y2, h]

        mosaic_img = np.zeros((h, w, 3), dtype=np.uint8)
        idx = 0
        for r in range(3):
            for c in range(3):
                cell_w = xs[c + 1] - xs[c]
                cell_h = ys[r + 1] - ys[r]
                scaled = cv2.resize(loaded_9[idx], (cell_w, cell_h))
                if self.allow_flip_h and random.random() < 0.5:
                    scaled = cv2.flip(scaled, 1)
                mosaic_img[ys[r] : ys[r + 1], xs[c] : xs[c + 1]] = scaled
                idx += 1

        return mosaic_img

    def generate_cutmix(self, img_a, img_b):
        """
        CutMix: Cắt 1 vùng hình chữ nhật từ ảnh B dán đè lên ảnh A.
        Giúp mô hình không phụ thuộc vào 1 góc nhìn duy nhất và học nhận diện khi bị che khuất.
        """
        h, w = img_a.shape[:2]
        result = img_a.copy()

        # Chọn kích thước vùng cắt từ 20% - 45% diện tích
        cut_w = int(random.uniform(0.25, 0.45) * w)
        cut_h = int(random.uniform(0.25, 0.45) * h)

        cx = random.randint(0, w - cut_w)
        cy = random.randint(0, h - cut_h)

        result[cy : cy + cut_h, cx : cx + cut_w] = img_b[cy : cy + cut_h, cx : cx + cut_w]
        return result

    def generate_mixup(self, img_a, img_b):
        """
        MixUp: Trộn tuyến tính 2 ảnh với hệ số alpha.
        Tạo hiệu ứng phơi sáng kép giúp mô hình trơn tru đường biên quyết định.
        """
        alpha = random.uniform(0.65, 0.85)
        return cv2.addWeighted(img_a, alpha, img_b, 1.0 - alpha, 0)

    # =========================================================================
    # 3. MÔ PHỎNG ÁNH SÁNG, BÓNG ĐỔ VÀ MÔI TRƯỜNG THỰC TẾ
    # =========================================================================
    def add_random_shadow(self, img):
        """
        Mô phỏng bóng râm / bóng tay người hoặc vật cản che khuất ánh sáng đèn.
        Vẽ đa giác bóng tối mờ đè lên mặt bàn / vật thể.
        """
        if random.random() < self.shadow_prob:
            h, w = img.shape[:2]
            mask = np.zeros((h, w), dtype=np.uint8)

            # Tạo bóng hình đa giác ngẫu nhiên (3 - 5 đỉnh)
            num_vertices = random.randint(3, 5)
            pts = []
            for _ in range(num_vertices):
                pts.append([random.randint(0, w), random.randint(0, h)])
            pts = np.array(pts, np.int32)
            cv2.fillPoly(mask, [pts], 255)

            # Làm mờ viền bóng cho tự nhiên
            mask = cv2.GaussianBlur(mask, (31, 31), 0)

            # Hệ số giảm sáng vùng bóng (tối đi 30% - 60%)
            shadow_factor = random.uniform(0.4, 0.7)

            img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
            v = img_hsv[:, :, 2]
            v_shadow = v * shadow_factor
            img_hsv[:, :, 2] = np.where(mask > 50, (v * (1 - mask / 255.0) + v_shadow * (mask / 255.0)), v)
            img = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        return img

    def adjust_light_and_color(self, img):
        """Điều chỉnh độ sáng, tương phản và độ rực màu (Saturation), bảo toàn Hue."""
        alpha = random.uniform(self.contrast_range[0], self.contrast_range[1])
        beta = random.uniform(
            (self.brightness_range[0] - 1.0) * 100,
            (self.brightness_range[1] - 1.0) * 100,
        )
        img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
        h, s, v = cv2.split(hsv)

        # Điều chỉnh độ bão hòa màu (Saturation)
        s = np.clip(s * random.uniform(0.75, 1.3), 0, 255)

        # Đổi nhẹ hue nếu cho phép
        if self.allow_hue_shift:
            dh = random.uniform(-self.hue_shift_limit, self.hue_shift_limit)
            h = (h + dh) % 180

        hsv = cv2.merge([h, s, v]).astype(np.uint8)
        return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    def add_noise(self, img):
        """Nhiễu hạt cảm biến camera."""
        if random.random() < self.noise_prob:
            mean = 0
            sigma = random.uniform(8, 25) ** 0.5
            gaussian = np.random.normal(mean, sigma, img.shape).astype(np.float32)
            noisy = img.astype(np.float32) + gaussian
            img = np.clip(noisy, 0, 255).astype(np.uint8)
        return img

    def add_blur(self, img):
        """Mờ chuyển động / lấy nét chưa chuẩn."""
        if random.random() < self.blur_prob:
            k = random.choice([3, 5])
            if random.random() < 0.5:
                img = cv2.GaussianBlur(img, (k, k), 0)
            else:
                img = cv2.medianBlur(img, k)
        return img

    def augment_single(self, img):
        """Pipeline tăng cường hoàn chỉnh cho 1 ảnh."""
        res = img.copy()
        res = self.random_position_and_scale(res)
        if random.random() < 0.65:
            res = self.random_perspective(res)
        res = self.random_flips(res)
        res = self.add_random_shadow(res)
        res = self.adjust_light_and_color(res)
        res = self.add_blur(res)
        res = self.add_noise(res)
        return res


def get_image_files(folder_path):
    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    folder = Path(folder_path)
    return [p for p in folder.iterdir() if p.suffix.lower() in valid_exts and p.is_file()]


def process_dataset(input_dir, output_dir, samples_per_class, augmentor):
    """
    Phối hợp đồng thời các kỹ thuật:
    - 50% Ảnh biến đổi vị trí đa tỉ lệ, góc 3D, bóng râm
    - 20% YOLO Mosaic 4-in-1
    - 10% YOLO Mosaic 9-in-1 (lưới 3x3)
    - 10% CutMix (ghép mảng che khuất)
    - 10% MixUp (hòa trộn tuyến tính)
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    subdirs = [p for p in input_path.iterdir() if p.is_dir()]
    if not subdirs:
        print(f"[!] Không tìm thấy thư mục class nào trong {input_dir}")
        return

    print("\n" + "=" * 62)
    print(" BẮT ĐẦU CHẠY BỘ SIÊU AUGMENTATION (YOLO & DEEP LEARNING)")
    print(f" - Số class phát hiện   : {len(subdirs)}")
    print(f" - Số lượng tạo/class   : {samples_per_class} ảnh biến thể")
    print(" - Các kỹ thuật áp dụng :")
    print("     + Multi-scale & Corner Shift : Di chuyển khắp 4 góc & mép bàn")
    print("     + YOLO Mosaic 4-in-1         : Ghép 4 góc phần tư ngẫu nhiên")
    print("     + YOLO Mosaic 9-in-1         : Lưới 3x3 mô phỏng vật thể nhỏ")
    print("     + CutMix                     : Ghép mảng mô phỏng che khuất")
    print("     + MixUp                      : Hòa trộn đa phơi sáng")
    print("     + Random Shadows             : Đổ bóng râm tay/đèn thực tế")
    print("=" * 62 + "\n")

    for class_folder in subdirs:
        class_name = class_folder.name
        class_images = get_image_files(class_folder)

        if not class_images:
            print(f"[-] Bỏ qua '{class_name}' vì không có ảnh gốc nào.")
            continue

        class_out_dir = output_path / class_name
        class_out_dir.mkdir(parents=True, exist_ok=True)

        # Lưu lại toàn bộ ảnh gốc vào thư mục kết quả
        for orig in class_images:
            cv2.imwrite(str(class_out_dir / orig.name), cv2.imread(str(orig)))

        # Chia tỉ lệ các kỹ thuật
        n_mosaic4 = int(samples_per_class * 0.20)
        n_mosaic9 = int(samples_per_class * 0.10)
        n_cutmix = int(samples_per_class * 0.10)
        n_mixup = int(samples_per_class * 0.10)
        n_standard = samples_per_class - (n_mosaic4 + n_mosaic9 + n_cutmix + n_mixup)

        pbar = tqdm(total=samples_per_class, desc=f"  Tạo [{class_name}]")
        created = 0

        # 1. Standard (Multi-scale, Góc 3D, Vị trí góc, Đổ bóng râm)
        for _ in range(n_standard):
            chosen = random.choice(class_images)
            src = cv2.imread(str(chosen))
            if src is None:
                continue
            aug = augmentor.augment_single(src)
            cv2.imwrite(str(class_out_dir / f"aug_std_{created+1:04d}.jpg"), aug)
            created += 1
            pbar.update(1)

        # 2. YOLO Mosaic 4-in-1
        for _ in range(n_mosaic4):
            aug = augmentor.generate_mosaic_4(class_images)
            aug = augmentor.add_random_shadow(aug)
            aug = augmentor.adjust_light_and_color(aug)
            aug = augmentor.add_noise(aug)
            cv2.imwrite(str(class_out_dir / f"aug_mosaic4_{created+1:04d}.jpg"), aug)
            created += 1
            pbar.update(1)

        # 3. YOLO Mosaic 9-in-1
        for _ in range(n_mosaic9):
            aug = augmentor.generate_mosaic_9(class_images)
            aug = augmentor.adjust_light_and_color(aug)
            cv2.imwrite(str(class_out_dir / f"aug_mosaic9_{created+1:04d}.jpg"), aug)
            created += 1
            pbar.update(1)

        # 4. CutMix
        for _ in range(n_cutmix):
            img_a = cv2.imread(str(random.choice(class_images)))
            img_b = cv2.imread(str(random.choice(class_images)))
            aug = augmentor.generate_cutmix(img_a, img_b)
            aug = augmentor.augment_single(aug)
            cv2.imwrite(str(class_out_dir / f"aug_cutmix_{created+1:04d}.jpg"), aug)
            created += 1
            pbar.update(1)

        # 5. MixUp
        for _ in range(n_mixup):
            img_a = cv2.imread(str(random.choice(class_images)))
            img_b = cv2.imread(str(random.choice(class_images)))
            aug = augmentor.generate_mixup(img_a, img_b)
            aug = augmentor.adjust_light_and_color(aug)
            cv2.imwrite(str(class_out_dir / f"aug_mixup_{created+1:04d}.jpg"), aug)
            created += 1
            pbar.update(1)

        pbar.close()


def main():
    parser = argparse.ArgumentParser(
        description="Siêu công cụ Data Augmentation cho Object Detection (Mosaic 4, Mosaic 9, CutMix, MixUp, Shadows)."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="dataset_raw",
        help="Thư mục ảnh gốc (mặc định: dataset_raw)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="dataset_augmented",
        help="Thư mục lưu ảnh đã augment (mặc định: dataset_augmented)",
    )
    parser.add_argument(
        "--count",
        "-n",
        type=int,
        default=120,
        help="Số lượng ảnh augment cần sinh cho mỗi class (mặc định: 120)",
    )
    parser.add_argument(
        "--allow-hue-shift",
        action="store_true",
        help="Cho phép đổi nhẹ tông màu (mặc định: False để bảo toàn màu sắc cube)",
    )

    args = parser.parse_args()

    augmentor = AdvancedDetectionAugmentor(
        allow_hue_shift=args.allow_hue_shift,
    )

    process_dataset(args.input, args.output, args.count, augmentor)
    print(f"\n[Xong hoàn tất] Dữ liệu siêu phong phú đã sẵn sàng tại: '{args.output}'.")


if __name__ == "__main__":
    main()
