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
- **Cách A (Dùng camera/webcam trực tiếp - Hỗ trợ cả Camera USB cắm ngoài):**
  ```powershell
  # Chụp ảnh (Mặc định sẽ tự ưu tiên nhận diện Camera ngoài nếu có cắm USB)
  python capture_from_camera.py --class cube_yellow

  # Hoặc chỉ định rõ camera USB (chỉ số 1)
  python capture_from_camera.py --class cube_yellow --camera 1

  # Xem danh sách các camera đang cắm vào máy:
  python capture_from_camera.py --list
  ```
  - **Các nút điều khiển trên màn hình Camera (Dùng chuột click hoặc phím tắt):**
    - 🔴 **[LUU LIEN TUC] (Phím 'R')**: Nhấp 1 lần để **BẮT ĐẦU lưu liên tục** (khoảng ~7 ảnh/giây). Trong lúc này bạn chỉ cần cầm vật thể di chuyển khắp các góc, mép bàn, xoay lật. **Bấm lại lần nữa để DỪNG LƯU**.
    - 📸 **[CHUP 1 ANH] (Phím SPACE)**: Chụp 1 ảnh tĩnh đơn lẻ.
    - 🔄 **[DOI CAMERA] (Phím S hoặc TAB)**: Đổi qua lại giữa Camera laptop và Camera USB cắm ngoài.
    - ❌ **[THOAT] (Phím Q hoặc ESC)**: Đóng camera an toàn.
- **Cách B (Chụp bằng điện thoại/máy ảnh rồi chép vào):**
  - Chép ảnh vào các thư mục tương ứng trong `dataset_raw/<tên_class>/`.

---

### Bước 2: Chạy Script Tăng Cường Dữ Liệu (Augmentation)

Chạy lệnh sau để sinh biến thể từ ảnh gốc:

```powershell
python augment_images.py --count 60
```

> **Giải thích:** Lệnh trên sẽ quét toàn bộ các thư mục con trong `dataset_raw/` và sinh ra `60` ảnh biến thể mới cho mỗi class vào thư mục `dataset_augmented/`.

#### Các Kỹ Thuật Siêu Augmentation (YOLO & Deep Learning) Tự Động:
1. **YOLO Mosaic 4-in-1 (20% dữ liệu):** Ghép 4 ảnh tại tâm giao ngẫu nhiên, giúp mô hình học nhận diện vật thể ở 4 góc phần tư khác nhau với tỉ lệ đa dạng.
2. **YOLO Mosaic 9-in-1 (10% dữ liệu):** Ghép 9 ảnh vào lưới 3x3 mô phỏng phát hiện các vật thể nhỏ ở khoảng cách xa.
3. **CutMix (10% dữ liệu):** Cắt một vùng hình chữ nhật từ ảnh này dán đè lên ảnh kia, giúp mô hình nhận diện tốt khi vật thể bị che khuất một phần.
4. **MixUp (10% dữ liệu):** Hòa trộn tuyến tính giữa 2 ảnh để làm trơn tru đường biên phân loại.
5. **Random Shadows (Bóng râm ngẫu nhiên):** Mô phỏng bóng tay người, bóng đèn trần hoặc vật thể khác đổ bóng lên bàn.
6. **Multi-Scale & Corner Shift:** Thu nhỏ vật thể đa tỉ lệ (0.4x - 1.25x) và dịch chuyển khắp 4 góc viền mép bàn.
7. **Biến dạng không gian 3D:** Perspective Warp (góc nhìn nghiêng camera), Xoay (Rotation), Lật (Flip).
8. **Mô phỏng camera thực tế:** Brightness, Contrast, Saturation, Sensor Noise, Motion Blur.
9. **Bảo toàn tông màu (Hue Preservation):** Đảm bảo giữ nguyên sắc độ màu của cube để không bao giờ bị nhầm lẫn giữa cube xanh, đỏ, vàng, tím.

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
