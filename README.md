# 🦾 FabLab AI & Dobot Magician 3D Digital Twin Studio

Hệ thống tích hợp toàn diện **Thị giác Máy tính (AI Computer Vision)**, **Bản sao số 3D (3D Digital Twin)** và **Điều khiển Cánh tay Robot công nghiệp Dobot Magician**, phục vụ nghiên cứu, sản xuất thử nghiệm và giáo dục STEAM chuẩn công nghiệp 4.0.

Toàn bộ quy trình từ **Thu thập dữ liệu** $\rightarrow$ **Huấn luyện mô hình AI** $\rightarrow$ **Lập trình trực quan Blockly** $\rightarrow$ **Tự động hóa gắp thả phân loại phôi màu theo thời gian thực** đã được tích hợp tập trung vào một giao diện Web duy nhất.

---

## 🚀 1. Hướng Dẫn Khởi Chạy Nhanh (Quickstart)

Chỉ cần **1 lệnh duy nhất** để khởi động toàn bộ hệ thống (Web Studio, 3D Digital Twin, luồng Camera AI và Server điều khiển Dobot):

### Bước 1: Cài đặt thư viện phụ thuộc
Khuyến nghị sử dụng môi trường Python 3.10 – 3.12:
```bash
pip install -r requirements.txt
```

### Bước 2: Khởi động Server trung tâm
```bash
python DOBOT/dobot_live_server.py
```

* Máy chủ sẽ tự động chạy tại: **`http://localhost:8080`** (hoặc tự động mở trình duyệt web tới `http://localhost:8080/dobot_visualizer.html`).
* Cắm cáp USB Dobot Magician vào máy tính, bấm nút **"🔌 Kết Nối"** trên giao diện Web để đồng bộ ngay lập tức.

---

## 🖥️ 2. Các Phân Hệ Trên Giao Diện Web Studio (5 Tabs)

Giao diện trực quan tích hợp trọn vẹn 5 phân hệ công nghệ:

### 🦾 Tab 1: 3D Digital Twin & Blockly Studio
* **Bản sao số 3D thời gian thực (Three.js):** Mô phỏng cử động 3D đồng bộ 1:1 với cánh tay Dobot vật lý qua WebSocket nội bộ với độ trễ $< 50\text{ms}$.
* **Điều khiển đa chế độ:** Điều khiển tọa độ Descartes $(X, Y, Z, R)$, góc 4 khớp xoay $(J_1 - J_4)$, bước nhảy an toàn **Safe Jump** chống va đập, và bật/tắt đầu hút chân không.
* **Lập trình trực quan khối lệnh (Blockly):** Kéo thả các khối lệnh di chuyển, vòng lặp, điều kiện $\rightarrow$ Tự động sinh mã nguồn Python chuẩn và nạp lệnh trực tiếp tới robot.

### 📸 Tab 2: Thu Thập Dữ Liệu Thị Giác (Dataset Manager)
* Kết nối luồng webcam trực tiếp, chuyển đổi qua lại giữa Camera tích hợp và Camera USB ngoài.
* Chụp ảnh và tự động gán nhãn phôi mẫu (`cube_red`, `cube_green`, `cube_blue`, `cube_yellow`) và ảnh nền âm tính (Background).
* Quản lý số lượng mẫu và thống kê tập dữ liệu trực tiếp trên giao diện.

### 🧠 Tab 3: Trạm Huấn Luyện AI (AI Training Hub)
* Huấn luyện mô hình phát hiện vật thể YOLOv8n / YOLO11n.
* **Tích hợp Cloud GPU miễn phí (Kaggle API):** Tận dụng 30 giờ GPU NVIDIA Tesla T4/P100 miễn phí hàng tuần chỉ với 1 cú click chuột, không đòi hỏi máy tính cấu hình mạnh.
* Hỗ trợ xuất file nén `yolo_dataset.zip` để chạy trên Google Colab.
* Theo dõi tiến trình trực quan theo từng Epoch: Biểu đồ Loss, độ chính xác $mAP_{50}$, Precision và Recall.

### 🎯 Tab 4: Dây Chuyền Thị Giác & Phân Loại Tự Động (AI Vision Sorting)
* Chạy mô hình YOLO thời gian thực bám theo phôi trên bàn làm việc / băng chuyền.
* Tự động chuyển đổi tọa độ Pixel ảnh sang tọa độ thực $(X, Y\text{ mm})$ của Dobot thông qua ma trận biến đổi phối cảnh (**Homography**).
* **Vùng an toàn tự động (Workspace Safety Check):** Giới hạn bán kính an toàn ($140\text{mm} \le R \le 330\text{mm}$), chống va đập và ngăn chặn lệnh ngoài tầm với.
* Chế độ tự động gắp thả phôi màu vào các khay thả chỉ định (`drop_targets.json`).

### 📐 Tab 5: Cân Chỉnh Không Gian Camera – Robot (Calibration)
* Giao diện hiệu chuẩn phối cảnh 4 điểm (**Hand-Eye Calibration**).
* Tự động tính toán ma trận Homography và lưu trữ vào file cấu hình `homography_dobot.json`.

---

## 📁 3. Cấu Trúc Dự Án (Project Structure)

```text
ObjectDetection/
├── DOBOT/                                # [Hệ thống Động học, Server & Giao diện Dobot]
│   ├── dobot_live_server.py              # ⭐ [SERVER CHÍNH] Khởi chạy toàn bộ hệ thống
│   ├── dobot_visualizer.html             # 🌐 Giao diện Web 3D Digital Twin & AI Studio
│   ├── dobot_auto_sort.py                # Pipeline phân loại phôi tự động độc lập
│   ├── calibrate_camera_to_dobot.py      # Script hiệu chuẩn ma trận Homography
│   ├── kaggle_trainer.py                 # Module tự động hóa huấn luyện trên Kaggle Cloud GPU
│   ├── web_vision_engine.py              # Động cơ thị giác máy tính tích hợp Web
│   ├── web_trainer.py                    # Bộ điều phối huấn luyện YOLO tích hợp
│   ├── web_dataset_manager.py            # Trình quản lý tập dữ liệu hình ảnh
│   ├── drop_targets.json                 # Cấu hình tọa độ khay thả vật phẩm theo màu
│   ├── homography_dobot.json             # Ma trận biến đổi tọa độ Camera -> Dobot
│   ├── move_to_point.py                  # Điều khiển di chuyển điểm quỹ đạo Safe Jump
│   └── test_dobot.py                     # Script kiểm tra kết nối phần cứng Dobot
│
├── models/                               # [Trọng số mô hình đã huấn luyện]
│   ├── best_11.pt                        # ⭐ [Khuyên dùng] YOLO11 Nano - Spatial Attention
│   ├── best_trained.pt                   # Mô hình mới nhất vừa huấn luyện từ Studio
│   └── best_v8_more_augmentation.pt      # YOLOv8 Nano - Độ nhạy cao
│
├── dataset_raw/                          # Dữ liệu ảnh thô chụp từ camera theo từng class
├── yolo_dataset/                         # Tập dữ liệu cấu trúc chuẩn YOLO (train / val)
├── yolo_dataset.zip                      # File nén dataset sẵn sàng đẩy lên Cloud
│
├── requirements.txt                      # Danh sách thư viện Python phụ thuộc
└── README.md                             # Tài liệu hướng dẫn sử dụng
```

---

## ⚡ 4. Điểm Nhấn Kỹ Thuật (Key Technical Highlights)

1. **Điện toán biên cục bộ (Edge Computing):** Vận hành hoàn toàn Offline trên máy tính nội bộ thông qua Localhost, không đòi hỏi kết nối Internet khi điều khiển robot vật lý.
2. **Khắc phục nghẽn băng thông USB Camera:** Ép chuẩn nén phần cứng `MJPG` trên Windows DirectShow giúp camera ngoài luôn duy trì mượt mà ở **30 FPS**.
3. **Cơ chế Bước nhảy an toàn (Safe Jump):** Tự động bù trừ chiều dài giác hút ($Z_{\text{offset}} = 59.5\text{mm}$), tự động nâng độ cao an toàn trước khi di chuyển ngang giúp triệt tiêu nguy cơ va quẹt phôi hoặc camera.
4. **Tích hợp Cloud GPU 0 Đồng:** Huấn luyện trực tiếp trên GPU Tesla T4 thông qua Kaggle API, giải quyết triệt để rào cản phòng máy trường học không có card đồ họa rời.

---

## 🤝 Đóng Góp & Tác Giả (Credits)

- **Hệ thống Động học & Điều khiển Cánh tay Robot Dobot (Thư mục `DOBOT/`)**:
  Được nghiên cứu, phát triển và tối ưu hóa bởi kỹ sư **Danh Huynh** — [GitHub: @DanhCon](https://github.com/DanhCon).
  Bao gồm các module:
  - Hiệu chuẩn tọa độ thị giác Hand-Eye Calibration (Homography Mapping $u, v \to X, Y\text{ mm}$).
  - Thuật toán giải động học nghịch & Quỹ đạo an toàn **Safe Jump** chống báo động/va đập.
  - Server bản sao số 3D Live Digital Twin và chu trình tự động hóa gắp thả phân loại khối màu.
