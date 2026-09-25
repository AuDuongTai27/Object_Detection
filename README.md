# Hệ Thống Thu Thập Dữ Liệu & Nhận Diện Đa Vật Thể (Object Detection) - FabLab

Dự án cung cấp giải pháp toàn diện từ khâu thu thập dữ liệu bằng Camera/Webcam, tăng cường dữ liệu nâng cao (Data Augmentation), cho đến nhận diện đa vật thể (Multi-Object Detection) vẽ khung Bounding Box theo thời gian thực bằng **YOLOv8** hoặc **OpenCV**.

---

## 1. Cấu Trúc Dự Án

```text
ObjectDetection/
│
├── capture_from_camera.py       # Thu thập ảnh từ Webcam/Camera USB (hỗ trợ nút chuột & lưu liên tục)
├── augment_images.py            # Siêu Augmentation (YOLO Mosaic, CutMix, MixUp, Shadows, Multi-scale)
├── generate_yolo_dataset.py     # Tự động ghép nhiều cube và tạo nhãn Bounding Box chuẩn YOLO (.txt)
├── zip_dataset.py               # Nén nhanh yolo_dataset.zip để sẵn sàng tải lên Google Colab
├── train_on_colab.ipynb         # File Google Colab Notebook huấn luyện YOLOv8 bằng GPU T4 miễn phí
│
├── detect_camera_opencv.py      # Nhận diện đa cube real-time bằng OpenCV (Chạy ngay lập tức, 60 FPS)
├── detect_camera_yolo.py        # Nhận diện đa vật thể camera bằng mô hình YOLOv8 vừa train (best.pt)
├── train_yolo.py                # Huấn luyện YOLOv8 trực tiếp trên máy tính cá nhân
│
├── dataset_raw/                 # Dữ liệu ảnh gốc chụp từ camera theo từng class (cube_blue,...)
├── yolo_dataset/                # Dữ liệu YOLO đã gán nhãn tự động (images/, labels/, data.yaml)
└── yolo_dataset.zip             # File nén dataset sẵn sàng đẩy lên Colab
```

---

## 2. Tổng Hợp Các Lệnh Để Chạy

### 📸 Bước 1: Thu thập ảnh từ Camera (`capture_from_camera.py`)

Hỗ trợ tự động nhận diện Camera USB ngoài và hiển thị nút bấm điều khiển bằng chuột trực tiếp trên màn hình:

```powershell
# Chụp cho class bất kỳ (tự động tạo thư mục nếu chưa có)
python capture_from_camera.py --class cube_yellow

# Xem danh sách camera đang cắm vào máy tính
python capture_from_camera.py --list

# Chỉ định mở camera USB ngoài (Camera index 1)
python capture_from_camera.py --class cube_blue --camera 1
```

* **Cách dùng trên cửa sổ Camera:**
  * 🔴 **Click nút `[LUU LIEN TUC]` (hoặc phím `R`):** Bắt đầu lưu tự động ~7 ảnh/giây. Lúc này dùng tay cầm vật thể di chuyển khắp các góc, mép bàn, xoay lật. **Bấm lại lần nữa để DỪNG LƯU**.
  * 📸 **Click nút `[CHUP 1 ANH]` (hoặc `SPACE`):** Chụp 1 ảnh tĩnh.
  * 🔄 **Click nút `[DOI CAMERA]` (hoặc `S` / `TAB`):** Đổi qua lại camera máy và camera USB.
  * ❌ **Click nút `[THOAT]` (hoặc `Q` / `ESC`):** Đóng camera.

---

### 🎨 Bước 2 (Lựa chọn 1): Huấn luyện trên Google Teachable Machine

Nếu bạn muốn phân loại ảnh từng vật thể đơn lẻ với Teachable Machine:

```powershell
# Chạy Augmentation với các kỹ thuật hiện đại (Mosaic 4, Mosaic 9, CutMix, MixUp, Shadows)
python augment_images.py --count 120
```

1. Mở [Google Teachable Machine (Image Model)](https://teachablemachine.withgoogle.com/train/image).
2. Tạo các class tương ứng (`cube_blue`, `cube_red`, `cube_yellow`, `cube_green`, `background`).
3. Kéo thả các thư mục trong `dataset_augmented/` vào.
4. Chỉnh thông số **Advanced**: **Epochs: 75**, **Batch Size: 32**, **Learning Rate: 0.0005**.
5. Bấm **Train Model**.

---

### 🎯 Bước 3 (Lựa chọn 2): Phát Hiện Đa Vật Thể & Bounding Box với YOLOv8 (Khuyên Dùng)

Dành cho bài toán: **1 bức ảnh có nhiều cube cùng lúc**, cần vẽ khung chữ nhật (Bounding Box) và hiện tên nhãn từng cube.

#### 3.1. Tự động tạo Dataset đa vật thể + Bounding Box (Không cần vẽ tay)
```powershell
# Tự động trích xuất cube từ dataset_raw, ghép 1-4 cube/ảnh và xuất nhãn YOLO chuẩn xác 100%
python generate_yolo_dataset.py --train-count 400 --val-count 80
```

#### 3.2. Nén tập dữ liệu để chuẩn bị mang lên Google Colab
```powershell
python zip_dataset.py
```
*(Lệnh này tạo ra file `yolo_dataset.zip` khoảng vài chục MB).*

#### 3.3. Huấn luyện siêu tốc bằng GPU trên Google Colab (`train_on_colab.ipynb`)
1. Truy cập [Google Colab](https://colab.research.google.com/) $\rightarrow$ Chọn **Upload** file `train_on_colab.ipynb`.
2. Bật GPU miễn phí: **Runtime** $\rightarrow$ **Change runtime type** $\rightarrow$ Chọn **T4 GPU** $\rightarrow$ **Save**.
3. Kéo thả file `yolo_dataset.zip` vào cột Files (thư mục bên trái Colab).
4. Bấm **Runtime** $\rightarrow$ **Run all** (Chạy tất cả).
5. Sau ~2-3 phút, Colab sẽ **tự động tải file mô hình `best.pt` về máy tính** của bạn.

#### 3.4. Chạy nhận diện Camera Real-time với YOLOv8
Chép file `best.pt` vừa tải về thả vào thư mục dự án này, rồi chạy:

```powershell
python detect_camera_yolo.py
```

---

### ⚡ Bước 4: Nhận Diện Bounding Box Tức Thì Bằng OpenCV (Không Cần Train)

Nếu muốn kiểm tra camera nhận diện Bounding Box ngay lập tức mà không cần chờ train model:

```powershell
python detect_camera_opencv.py
```
* Tự động quét và đóng khung tất cả các khối cube (Xanh dương, Đỏ, Vàng, Lục) đồng thời theo thời gian thực.
* Tốc độ cực cao (50 - 60 FPS) trên mọi loại máy tính.
