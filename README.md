# 🎯 FabLab Multi-Cube Object Detection System (Real-time YOLO)

Hệ thống thị giác máy tính toàn diện cho bài toán phát hiện và định vị đa vật thể (Multi-Object Detection) theo thời gian thực trên camera/webcam tại FabLab.

Dự án tối ưu hóa toàn bộ pipeline từ **Thu thập dữ liệu camera** $\rightarrow$ **Tăng cường dữ liệu thích nghi (Adaptive Data Augmentation)** $\rightarrow$ **Huấn luyện GPU trên Google Colab** $\rightarrow$ **Suy luận thời gian thực 25–30 FPS trên CPU laptop**.

---

## 📁 1. Cấu Trúc Dự Án (Project Structure)

```text
ObjectDetection/
├── models/                               # [Trọng số mô hình đã huấn luyện]
│   ├── best_11.pt                        # ⭐ [Khuyên dùng] YOLO11 Nano - Spatial Attention, chống bắt nhầm tốt nhất
│   ├── best_v8_more_augmentation.pt      # 🚀 [Độ nhạy cao] YOLOv8 Nano - Bắt cube cực nhạy, chịu ngón tay che
│   └── archive/                          # Lưu trữ các checkpoints đối chứng (v5, v8 gốc, v8 background)
│       ├── best_v5.pt
│       ├── best_v8.pt
│       ├── best_v8_background.pt
│       └── yolov8n.pt
│
├── dataset_raw/                          # Dữ liệu ảnh thô chụp từ camera
│   ├── cube_blue/                        # 145 ảnh
│   ├── cube_green/                       # 116 ảnh
│   ├── cube_red/                         # 108 ảnh
│   ├── cube_yellow/                      # 130 ảnh
│   └── background/                       # 131 ảnh nền âm tính (Negative samples)
│
├── yolo_dataset/                         # Tập dữ liệu tổng hợp chuẩn YOLO (Train / Val / data.yaml)
├── yolo_dataset.zip                      # File nén dataset sẵn sàng đẩy lên Google Colab (~141 MB)
│
├── detect_camera_yolo.py                 # ⭐ [Chính] Chương trình nhận diện camera thời gian thực bằng YOLO
├── detect_camera_opencv.py               # Nhận diện cơ bản bằng giải thuật phân đoạn màu HSV (60 FPS)
├── capture_from_camera.py                # Công cụ chụp và thu thập ảnh mẫu từ Webcam / USB Cam
├── generate_yolo_dataset.py              # Pipeline sinh dataset YOLO kèm mô phỏng che khuất & sai lệch cảm biến
├── augment_images.py                     # Bộ công cụ siêu Augmentation (Mosaic, CutMix, Shadows)
├── zip_dataset.py                        # Tiện ích tự động nén yolo_dataset.zip
├── train_on_colab.ipynb                  # Sổ tay huấn luyện GPU T4 trên Google Colab (~2-3 phút)
├── train_yolo.py                         # Huấn luyện cục bộ bằng CPU (tuỳ chọn)
│
├── requirements.txt                      # Danh sách các thư viện phụ thuộc
├── .gitignore                            # Cấu hình bỏ qua tệp nháp / file nhị phân
└── README.md                             # Tài liệu hướng dẫn sử dụng chi tiết
```

---

## 🏆 2. Đánh Giá & So Sánh 2 Mô Hình Tốt Nhất

| Đặc tính | ⭐ YOLO11 Nano (`models/best_11.pt`) | 🚀 YOLOv8 Nano (`models/best_v8_more_augmentation.pt`) |
| :--- | :---: | :---: |
| **Kiến trúc** | **C2PSA Spatial Attention + C3k2** | Task-Aligned Assigner Anchor-Free |
| **Ưu điểm vượt trội** | **Chống nhận diện nhầm vật lạ cực tốt** | **Bắt cube cực nhạy ở mọi góc khó** |
| **Phản ứng với ngón tay che** | Tốt, giữ vững bounding box | Rất tốt, chịu được cả khi che 30% cạnh |
| **Tốc độ trên CPU Laptop** | **~20 – 25 FPS (Rất nhẹ & mượt)** | ~18 – 22 FPS |
| **Mục đích sử dụng** | **Môi trường phòng thực tế có nhiều đồ vật** | **Môi trường ít đồ vật hoặc cự ly xa** |

---

## 🚀 3. Hướng Dẫn Chạy Nhanh (Quickstart)

### 3.1. Cài đặt môi trường
Khuyến nghị sử dụng Python 3.10 – 3.12 (hoặc Conda):
```bash
pip install -r requirements.txt
```

### 3.2. Chạy nhận diện trực tiếp bằng Camera
Mặc định hệ thống tự động ưu tiên nạp `models/best_11.pt` và mở Camera USB ngoài:
```bash
python detect_camera_yolo.py
```

* **Chỉ định model cụ thể:**
  ```bash
  # Chạy với YOLO11
  python detect_camera_yolo.py --model models/best_11.pt

  # Chạy với YOLOv8 More Augmentation
  python detect_camera_yolo.py --model models/best_v8_more_augmentation.pt
  ```

* **Phím tắt điều khiển trực tiếp trên cửa sổ Camera:**
  * `+` hoặc `=`: Tăng ngưỡng tự tin (Confidence) thêm 2% (giúp lọc sạch nhiễu nền).
  * `-` hoặc `_`: Giảm ngưỡng tự tin bớt 2% (giúp bắt các góc cube mờ/xa).
  * `S` hoặc `TAB`: **Chuyển đổi qua lại ngay lập tức giữa Camera Laptop và Camera USB ngoài**.
  * `Q` hoặc `ESC`: Thoát ứng dụng.

---

## 🛠️ 4. Quy Trình Cập Nhật & Huấn Luyện Thêm Dữ Liệu

Khi bạn muốn bổ sung thêm vật thể mới hoặc chụp thêm bối cảnh để chống nhận nhầm:

### Bước 1: Chụp thêm ảnh từ Camera
```bash
# Chụp thêm mẫu cube (ví dụ cube_blue)
python capture_from_camera.py --class cube_blue

# Chụp thêm bối cảnh phòng/bàn để làm mẫu âm tính chống nhận nhầm
python capture_from_camera.py --class background
```
*(Bấm phím `R` trên cửa sổ camera để lưu liên tục ~7 ảnh/giây, di chuyển vật thể quanh bàn).*

### Bước 2: Sinh lại tập dữ liệu YOLO
```bash
python generate_yolo_dataset.py
```
*Tự động tách cube, áp dụng Cutout ngón tay che khuất, biến thiên màu sắc cảm biến, trộn 131 ảnh nền âm tính với file `.txt` rỗng (0 bytes).*

### Bước 3: Nén dataset
```bash
python zip_dataset.py
```
*Tạo file `yolo_dataset.zip` (~140 MB).*

### Bước 4: Train GPU trên Google Colab
1. Mở [train_on_colab.ipynb](file:///c:/Users/PC/OneDrive/Desktop/EIU/FabLabExecutive/ObjectDetection/train_on_colab.ipynb) trên Google Colab.
2. Đổi Runtime sang **T4 GPU**.
3. Kéo thả file `yolo_dataset.zip` vào mục Files bên trái.
4. Bấm **Runtime** $\rightarrow$ **Run all** (chạy ~2–3 phút).
5. Tải file `best.pt` về, đổi tên thành `best_11.pt`, đặt vào thư mục `models/` và chạy `python detect_camera_yolo.py`.

---

## ⚡ 5. Bí Quyết Tối Ưu Hóa Kỹ Thuật (Engineering Notes)

1. **Khắc phục nghẽn băng thông USB 2.0 (Sub-10 FPS Bottleneck)**:
   - Trên Windows DirectShow, camera ngoài được ép chuẩn nén phần cứng `MJPG`:
     `cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))`
   - Giúp camera USB truyền dữ liệu ở tốc độ chuẩn **30 FPS**.
2. **Tăng tốc suy luận CPU Laptop**:
   - Tham số `imgsz=416` giảm 57% lượng phép tính FLOPS so với kích thước gốc 640x640, tăng gấp đôi tốc độ xử lý mà không làm suy giảm độ chính xác định vị cube.
3. **Cơ chế chống Ức chế ngược (Negative Suppression)**:
   - Các ảnh nền thật được kết hợp song song: vừa làm ảnh âm tính (0 bytes), vừa làm phôi nền để dán cube, giúp mô hình phân biệt rạch ròi giữa đồ vật trong phòng và khối cube màu.
