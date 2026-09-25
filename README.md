# Hướng Dẫn Thu Thập & Augmentation Ảnh Cho Teachable Machine

Dự án hỗ trợ thu thập và nhân bản (data augmentation) hình ảnh vật thể (ví dụ: các khối cube màu đỏ, xanh, vàng, tím,...) phục vụ huấn luyện mô hình phân loại / phát hiện bằng **Google Teachable Machine**.

---

## 1. Cấu Trúc Thư Mục

```text
ObjectDetection/
│
├── augment_images.py         # Script chính biến đổi & sinh thêm ảnh (Augmentation)
├── capture_from_camera.py     # Script tiện ích chụp ảnh mẫu nhanh từ Camera/Webcam
│
├── dataset_raw/              # Nơi chứa các ảnh gốc chụp thực tế
│   ├── cube_blue/            # Các ảnh chụp cube màu xanh
│   ├── cube_red/             # Các ảnh chụp cube màu đỏ
│   └── cube_yellow/          # Các ảnh chụp cube màu vàng
│
└── dataset_augmented/        # Kết quả sau khi chạy script augment (sẵn sàng upload)
    ├── cube_blue/            # Hàng chục/trăm ảnh biến thể của cube xanh
    ├── cube_red/             # Hàng chục/trăm ảnh biến thể của cube đỏ
    └── cube_yellow/          # Hàng chục/trăm ảnh biến thể của cube vàng
```

---

## 2. Các Bước Thực Hiện

### Bước 1: Chuẩn Bị Ảnh Gốc (Ảnh Chụp Thật)
Bạn chỉ cần từ 1 đến 5 tấm ảnh cho mỗi loại cube/vật thể. Có 2 cách:
- **Cách A (Dùng camera/webcam trực tiếp):**
  ```powershell
  python capture_from_camera.py --class cube_blue
  python capture_from_camera.py --class cube_red
  python capture_from_camera.py --class cube_yellow
  ```
  - Bấm `SPACE` để chụp từng ảnh.
  - Bấm `C` để chụp liên tiếp 5 ảnh.
  - Bấm `Q` để thoát.
- **Cách B (Chụp bằng điện thoại/máy ảnh rồi chép vào):**
  - Chép ảnh vào các thư mục tương ứng trong `dataset_raw/<tên_class>/`.

---

### Bước 2: Chạy Script Tăng Cường Dữ Liệu (Augmentation)

Chạy lệnh sau để sinh biến thể từ ảnh gốc:

```powershell
python augment_images.py --count 60
```

> **Giải thích:** Lệnh trên sẽ quét toàn bộ các thư mục con trong `dataset_raw/` và sinh ra `60` ảnh biến thể mới cho mỗi class vào thư mục `dataset_augmented/`.

#### Các Kỹ Thuật Biến Đổi Tự Động Trong Script:
1. **Xoay ngẫu nhiên (Rotation):** Từ -35° đến +35° mô phỏng vật thể đặt theo nhiều hướng.
2. **Thu phóng (Zoom) & Dịch chuyển (Translation):** Giúp mô hình nhận diện vật thể ở gần hoặc ở xa, lệch tâm camera.
3. **Phối cảnh (Perspective warp):** Mô phỏng góc nhìn nghiêng của camera.
4. **Lật ảnh (Horizontal Flip):** Đối xứng hình ảnh.
5. **Biến thiên ánh sáng (Brightness & Contrast):** Mô phỏng phòng sáng, phòng tối, bóng râm.
6. **Mờ nét & Nhiễu cảm biến (Blur & Gaussian Noise):** Mô phỏng rung lắc hoặc camera mất nét.
7. **Bảo toàn màu sắc (Hue Preservation):** Mặc định **không** làm lệch màu sắc chính, đảm bảo cube đỏ không bị đổi thành màu xanh làm sai nhãn.

#### Các Tùy Chọn Bổ Sung Khi Chạy:
- **Tăng số lượng ảnh sinh ra (ví dụ 100 ảnh):**
  ```powershell
  python augment_images.py --count 100
  ```
- **Chỉ augment một ảnh duy nhất:**
  ```powershell
  python augment_images.py --input path/to/image.jpg --output my_output --count 50
  ```
- **Nếu vật thể không phân biệt theo màu (cho phép đổi màu ngẫu nhiên):**
  ```powershell
  python augment_images.py --allow-hue-shift
  ```

---

## 3. Huấn Luyện Trên Google Teachable Machine

1. Truy cập vào [Google Teachable Machine](https://teachablemachine.withgoogle.com/train/image).
2. Chọn **Image Project** -> **Standard image model**.
3. Tại mỗi **Class**:
   - Đổi tên class (ví dụ: `cube_blue`, `cube_red`, `cube_yellow`).
   - Bấm nút **Upload** -> Chọn **Choose images from your files** (hoặc kéo thả toàn bộ ảnh trong thư mục `dataset_augmented/<class_name>/` vào).
   - *(Nên thêm 1 class `background` / `khong_co_vat_the` chứa ảnh bàn làm việc trống để mô hình không nhận diện nhầm khi không có cube).*
4. Bấm **Train Model**.
5. Kiểm tra kết quả trực tiếp với Camera ở mục **Preview**, sau đó bấm **Export Model** (dưới dạng TensorFlow Lite hoặc Keras để dùng trên Python/Raspberry Pi).
