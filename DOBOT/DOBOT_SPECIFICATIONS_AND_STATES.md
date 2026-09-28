# TÀI LIỆU KỸ THUẬT: THÔNG SỐ VẬT LÝ, GIỚI HẠN KHỚP & TRẠNG THÁI DOBOT MAGICIAN
**FABLAB - Dobot Magician Engineering Reference Manual**

---

## 1. THÔNG SỐ VẬT LÝ & KỸ THUẬT (HARDWARE SPECIFICATIONS)

### 1.1. Thông số cơ bản
| Thông số | Giá trị chuẩn | Ghi chú kỹ thuật |
| :--- | :--- | :--- |
| **Tải trọng tối đa (Payload)** | **500 g (0.5 kg)** | Tải trọng tối ưu khuyến nghị: 250g - 300g để động cơ mượt mà |
| **Bán kính làm việc tối đa (Max Reach)** | **320 mm - 330 mm** | Vượt quá 330 mm cánh tay duỗi thẳng, mất ngẫu lực |
| **Bán kính làm việc tối thiểu (Min Reach)** | **140 mm** | Dưới 140 mm đầu công cụ tự đâm vào thân/chân đế |
| **Độ lặp lại vị trí (Repeatability)** | **± 0.2 mm** | Đo tại đầu mũi giác hút |
| **Số bậc tự do (DOFs)** | **4 trục (4-Axis)** | $J_1$ (Base), $J_2$ (Rear), $J_3$ (Forearm), $J_4$ (Servo R) |
| **Trọng lượng thân máy** | **3.4 kg** | Đế hợp kim nhôm đúc đầm chắc |
| **Điện áp & Nguồn cấp** | **12V DC - 7A** | Dùng adapter chính hãng Dobot 100-240V AC |
| **Công suất tiêu thụ** | **60 W (tối đa)** | Khi chạy đồng thời 4 trục và bơm hút chân không |
| **Nhiệt độ hoạt động** | **-10°C đến 60°C** | Khuyến nghị 20°C - 35°C trong phòng LAB |

---

### 1.2. Kích thước hình học các khâu (Kinematic Link Dimensions)
Cơ cấu cánh tay Dobot Magician là dạng cánh tay robot song song 4 khâu (Parallel Link SCARA Mechanism):

* **$L_1$ (Độ cao tâm khớp vai so với mặt đáy):** $138.0\text{ mm}$
* **$L_2$ (Chiều dài cánh tay sau - Rear Arm):** $135.0\text{ mm}$
* **$L_3$ (Chiều dài cẳng tay trước - Forearm):** $147.0\text{ mm}$
* **$L_4$ (Khoảng cách từ cẳng trước ra tâm mặt bích):** $59.0\text{ mm}$

---

### 1.3. Bù trừ công cụ đầu cuối (End-Effector Tool Offsets)
Tọa độ trong firmware của Dobot tính theo tâm **mặt bích chuẩn (Flange)**. Khi gắn thêm công cụ, chiều dài công cụ được bù trừ theo trục $Z$:

| Công cụ đầu cuối | Chiều dài bù trừ ($Z_{\text{offset}}$) | Công thức quy đổi tọa độ ($Z_{\text{TCP}} \leftrightarrow Z_{\text{Flange}}$) |
| :--- | :--- | :--- |
| **Giác hút khí nén (Suction Cup)** | $-59.5\text{ mm}$ | $Z_{\text{Flange}} = Z_{\text{TCP}} + 59.5$ <br> $Z_{\text{TCP}} = Z_{\text{Flange}} - 59.5$ |
| **Tay kẹp khí nén (Gripper)** | $-68.0\text{ mm}$ | $Z_{\text{Flange}} = Z_{\text{TCP}} + 68.0$ <br> $Z_{\text{TCP}} = Z_{\text{Flange}} - 68.0$ |
| **Mặt bích trần (Flange)** | $0.0\text{ mm}$ | $Z_{\text{Flange}} = Z_{\text{TCP}}$ |
| **Bút vẽ / Ngòi viết** | $-50.0 \sim -75.0\text{ mm}$ *(tùy cữ gá)* | Đo từ mép mặt bích nhôm đến đầu ngòi bút |

---

## 2. GIỚI HẠN HOẠT ĐỘNG (MOTION LIMITS & WORKSPACE BOUNDARIES)

### 2.1. Giới hạn các góc khớp (Joint Angle Boundaries)
Dobot Magician trang bị công tắc hành trình quang học (Optical Limit Sensors) để định vị điểm 0° và giới hạn phần mềm:

| Khớp | Tên cơ cấu | Góc tối thiểu | Góc tối đa | Hành trình | Giới hạn vận tốc |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$J_1$** | Xoay đế (Base Rotation) | **$-90.0^\circ$** | **$+90.0^\circ$** | $180^\circ$ | $320^\circ/\text{s}$ |
| **$J_2$** | Cánh tay sau (Rear Arm) | **$0.0^\circ$** | **$+85.0^\circ$** | $85^\circ$ | $320^\circ/\text{s}$ |
| **$J_3$** | Cẳng tay trước (Forearm) | **$-10.0^\circ$** | **$+85.0^\circ$** | $95^\circ$ | $320^\circ/\text{s}$ |
| **$J_4$** | Xoay đầu hút (Servo Axis R) | **$-135.0^\circ$** | **$+135.0^\circ$** | $270^\circ$ | $480^\circ/\text{s}$ |

> [!IMPORTANT]
> **Ràng buộc cơ học liên khớp ($J_2 + J_3$ Constraint):**
> Do cơ cấu thanh truyền song song (Parallel 4-bar linkage), góc tổng hợp $J_2 + J_3$ luôn phải thỏa mãn:
> $$J_2 + J_3 \le 160.0^\circ$$
> Nếu tổng hai góc vượt quá $160^\circ$, thanh truyền bị gấp khúc chạm giới hạn cơ khí, vi điều khiển kích hoạt báo động Alarm `0x22` / `0x23`.

---

### 2.2. Vùng không gian làm việc Đề-các (Cartesian Workspace Envelope)

| Trục tọa độ | Giá trị an toàn (Safe) | Giới hạn tối đa phần cứng | Ghi chú & Cảnh báo an toàn |
| :--- | :--- | :--- | :--- |
| **Trục $X$** | **$+140.0\text{ mm}$ đến $+330.0\text{ mm}$** | $+120\text{ mm}$ đến $+340\text{ mm}$ | Trục tiến/lùi. Dưới $140\text{ mm}$ quá gần thân |
| **Trục $Y$** | **$-220.0\text{ mm}$ đến $+220.0\text{ mm}$** | $-240\text{ mm}$ đến $+240\text{ mm}$ | Trục trái/phải ($>0$ sang trái, $<0$ sang phải) |
| **Trục $Z_{\text{Flange}}$** | **$-60.0\text{ mm}$ đến $+140.0\text{ mm}$** | $-65\text{ mm}$ đến $+165\text{ mm}$ | Đo tại mặt bích nhôm chuẩn |
| **Trục $Z_{\text{TCP}}$ (Mũi hút)** | **$-120.0\text{ mm}$ đến $+80.5\text{ mm}$** | $-125\text{ mm}$ đến $+105.5\text{ mm}$ | Đo tại đầu mút giác hút cao su |
| **Bán kính ngang $R_{\text{horiz}}$** | **$140.0\text{ mm}$ đến $330.0\text{ mm}$** | $R = \sqrt{X^2 + Y^2}$ | $R < 140\text{ mm}$: Kẹt kỳ dị IK; $R > 330\text{ mm}$: Vượt tầm |
| **Trục $R$ (Xoay)** | **$-135.0^\circ$ đến $+135.0^\circ$** | $-140^\circ$ đến $+140^\circ$ | Góc xoay mũi hút so với hệ trục tọa độ gốc |

---

### 2.3. Vùng điểm kỳ dị động học (Kinematic Singularity Zones)
1. **Kỳ dị ranh giới ngoài (Outer Boundary Singularity - $R \ge 330\text{ mm}$):**
   - Khi cánh tay duỗi thẳng hết cỡ, Jacobian matrix suy biến $\det(J) \to 0$.
   - Nếu điều khiển nội suy đường thẳng (`PTPMOVL`), vận tốc khớp sẽ tiến tới vô cực $\to$ Báo lỗi `0x11` (*ERR_PLAN_INV_SINGULARITY*).
2. **Kỳ dị vùng thân trong (Inner Body Collision Singularity - $R \le 140\text{ mm}$):**
   - Khi co đầu hút quá gần trục đế, cánh sau $J_2$ ép sát vào trụ đứng.
3. **Giải pháp xử lý triệt để:**
   - Luôn sử dụng chế độ **`PTPMOVJXYZ` (mode 1)** để quy hoạch đường đi trong không gian khớp, hoàn toàn miễn nhiễm với điểm kỳ dị.

---

## 3. CÁC TRẠNG THÁI HOẠT ĐỘNG CỦA DOBOT (DOBOT STATES & STATUSES)

### 3.1. Trạng thái chỉ báo đèn LED trên thân robot (LED Indicator States)
Đèn LED tròn nằm trên cụm khớp vai của Dobot Magician thông báo trạng thái phần cứng vi điều khiển:

| Màu đèn LED | Trạng thái kỹ thuật | Ý nghĩa hoạt động | Hành động cần thực hiện |
| :--- | :--- | :--- | :--- |
| 🟢 **Xanh lá sáng liên tục (Solid Green)** | **Normal / Ready / Idle** | Robot hoạt động bình thường, không có cờ lỗi, sẵn sàng nhận lệnh. | Gửi lệnh di chuyển bình thường. |
| 🟢 **Xanh lá thở chậm (Breathing Green)** | **Running / Executing** | Robot đang thực thi lệnh trong hàng đợi (động cơ đang quay). | Đợi lệnh hoàn thành hoặc gửi lệnh mới vào queue. |
| 🔴 **Đỏ sáng liên tục kèm còi hú (Solid Red + Beep)** | **Alarm / Fault Lockout** | Có lỗi phần cứng, chạm giới hạn cữ hoặc kẹt điểm kỳ dị. **Động cơ bị ngắt nguồn, queue bị đóng băng hoàn toàn.** | Bấm **[Xóa Lỗi]** trên Web hoặc gửi bộ 3 lệnh ID 20 + 245 + 240. |
| 🟡 **Vàng nhấp nháy (Flashing Yellow)** | **Homing in progress** | Robot đang quay tìm cữ hành trình cảm biến quang học. | Không chạm tay vào robot, đợi đèn chuyển xanh lá. |
| 🔵 **Xanh dương (Blue LED)** | **Wireless Peripheral Mode** | Đang nhận kết nối module mở rộng (Bluetooth / Wi-Fi dongle). | Hoạt động bình thường. |

---

### 3.2. Trạng thái hàng đợi lệnh (Command Queue States)
Dobot Magician xử lý chuyển động thông qua hàng đợi lệnh (FIFO Ring Buffer) trong vi điều khiển STM32:

| Lệnh điều khiển Queue | Mã Protocol ID | Giá trị Ctrl | Tác dụng kỹ thuật |
| :--- | :--- | :--- | :--- |
| **Start Queue** | **ID 240** | `0x01` | Kích hoạt bộ xử lý chạy các lệnh đang có trong hàng đợi. |
| **Stop / Pause Queue** | **ID 241** | `0x00` | Tạm dừng (Pause) thực thi queue (không xóa lệnh). |
| **Force Stop (E-Stop)** | **ID 242** | `0x00` | **Dừng khẩn cấp (Emergency Stop)**, ngắt lệnh đang chạy dở. |
| **Clear Queue** | **ID 245** | `0x01` | **Xóa sạch toàn bộ lệnh đang kẹt trong queue**, giải phóng bộ đệm. |

> [!TIP]
> **Quy trình chuẩn phục hồi sau lỗi:**
> Khi robot gặp sự cố (đỏ đèn):
> 1. Gửi **ID 20** (`SetAlarmState(Clear)`): Tắt còi hú và hạ cờ lỗi.
> 2. Gửi **ID 245** (`SetQueuedCmdClear`): Xóa sạch các lệnh còn tắc trong bộ nhớ.
> 3. Gửi **ID 240** (`SetQueuedCmdStartExec`): Mở lại cổng cho phép nhận và chạy lệnh mới.

---

### 3.3. Các chế độ chuyển động PTP (PTP Motion Modes - ID 84)

Khi gửi lệnh `ID 84` (`SetPTPCmd`), byte đầu tiên chỉ định chế độ chuyển động (`ptpMode`):

| Giá trị `ptpMode` | Tên chế độ | Mô tả chuyển động | Đánh giá độ an toàn |
| :---: | :--- | :--- | :--- |
| `0` | `PTPJUMPXYZ` | Nhấc cao hình cổng (Jump) đến tọa độ XYZ | An toàn khi gắp thả vật thể |
| `1` | `PTPMOVJXYZ` | **Nội suy góc khớp đến tọa độ Cartesian XYZ** | **KHUYÊN DÙNG 100%: Mượt mà, chống kỳ dị, không bao giờ đỏ đèn** |
| `2` | `PTPMOVLXYZ` | Nội suy đường thẳng đến tọa độ Cartesian XYZ | Dễ dính điểm kỳ dị $R < 140$ gây đỏ đèn |
| `3` | `PTPJUMPANGLE` | Nhấc cao hình cổng theo góc khớp | Ít dùng |
| `4` | `PTPMOVJANGLE` | Xoay góc khớp trực tiếp đến ($J_1, J_2, J_3, J_4$) | Dùng khi điều khiển trực tiếp từng động cơ |
| `5` | `PTPMOVLANGLE` | Chuyển động thẳng theo góc khớp | Hiếm khi dùng |
| `6` | `PTPMOVJXYZINC` | Di chuyển tương đối ($\Delta X, \Delta Y, \Delta Z$) theo góc khớp | Tương đối |
| `7` | `PTPMOVLXYZINC` | Di chuyển tương đối ($\Delta X, \Delta Y, \Delta Z$) theo đường thẳng | **TUYỆT ĐỐI TRÁNH: Rất dễ kích hoạt còi hú đèn đỏ** |

---

### 3.4. Bảng mã lỗi chi tiết (Dobot Alarm Register Bitmask - ID 20)
Khi đọc gói tin `ID 20` (Ctrl=0), Dobot trả về 16 byte (128 bit). Bit thứ $N$ bằng 1 biểu thị lỗi $N$ đang kích hoạt:

| Mã Hex | Tên biến hệ thống | Nguyên nhân kích hoạt | Cách xử lý |
| :---: | :--- | :--- | :--- |
| `0x00` | `RESET_ALARM` | Vi điều khiển vừa khởi động lại hoặc mới cắm nguồn | Bấm nút [Xóa lỗi] |
| `0x01` | `WARN_COMM_FRAME` | Nhận được gói tin có ID hoặc checksum sai | Kiểm tra cấu trúc packet nhị phân |
| `0x02` | `WARN_FLASH_WRITE` | Lỗi bộ nhớ Flash lưu trữ file | Nạp lại firmware |
| `0x10` | `ERR_PLAN_TRAJECTORY` | Thuật toán quy hoạch quỹ đạo bị lỗi | Đổi tọa độ điểm đến |
| `0x11` | `ERR_PLAN_INV_SINGULARITY` | Rơi vào điểm kỳ dị động học nghịch (IK Singularity) | Đổi sang `PTPMOVJXYZ` (mode 1), kiểm tra $R \ge 140\text{ mm}$ |
| `0x12` | `ERR_PLAN_LIMIT_SOFTWARE` | Điểm yêu cầu nằm ngoài phạm vi giới hạn phần mềm | Kiểm tra lại $X, Y, Z$ trong bảng giới hạn |
| `0x20` | `ERR_MOTION_EXECUTION` | Lỗi chấp hành động học khi động cơ đang quay | Dừng khẩn cấp, xóa queue |
| `0x21` | `ERR_AXIS1_LIMIT` | Khớp 1 ($J_1$) quay quá $\pm 90^\circ$ | Jog xoay $J_1$ ngược lại |
| `0x22` | `ERR_AXIS2_LIMIT` | Khớp 2 ($J_2$) chạm giới hạn $0^\circ$ hoặc $85^\circ$ | Jog gập/ngửa $J_2$ lại |
| `0x23` | `ERR_AXIS3_LIMIT` | Khớp 3 ($J_3$) chạm giới hạn $-10^\circ$ hoặc $85^\circ$ (hoặc $J_2 + J_3 > 160^\circ$) | Jog $J_3$ lại hoặc giảm $J_2$ |
| `0x24` | `ERR_AXIS4_LIMIT` | Khớp 4 ($J_4$) xoay quá $\pm 135^\circ$ | Xoay góc $J_4$ về $0^\circ$ |
| `0x30` | `ERR_SPEED_EXCEEDED` | Vận tốc khớp vượt quá ngưỡng an toàn vi điều khiển | Giảm vận tốc PTP xuống 30% - 50% |
| `0x31` | `ERR_LIMIT_SWITCH_HIT` | Chạm công tắc hành trình cơ học vật lý | Bấm Homing hoặc kéo nhẹ tay robot ra khỏi cữ |

---

## 4. TỌA ĐỘ CÁC VỊ TRÍ MẪU CHUẨN (STANDARD WORKSPACE PRESETS)

Dưới đây là các vị trí làm việc chuẩn đã được kiểm chứng an toàn 100% trên phần cứng thực tế:

| Tên vị trí | $X$ (mm) | $Y$ (mm) | $Z_{\text{Flange}}$ (mm) | $Z_{\text{TCP}}$ (Mũi hút) | $R$ (độ) | Ứng dụng thực tế |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **🏠 Home (Chuẩn)** | `250.0` | `0.0` | `50.0` | `-9.5` | `0.0` | Vị trí nghỉ an toàn, sẵn sàng nhận việc |
| **📦 Điểm Lấy Hàng (A)** | `200.0` | `-150.0` | `0.0` | `-59.5` | `-30.0` | Vị trí khay nạp phôi bên trái |
| **🎯 Điểm Thả Hàng (B)** | `200.0` | `150.0` | `0.0` | `-59.5` | `30.0` | Vị trí khay thành phẩm bên phải |
| **🏓 Tiếp Xúc Mặt Bàn** | `220.0` | `0.0` | `-50.0` | `-109.5` | `0.0` | Mức tiếp xúc bề mặt bàn phẳng chuẩn |
| **🚀 Trọng Tâm An Toàn** | `220.0` | `0.0` | `80.0` | `20.5` | `0.0` | Độ cao an toàn khi xoay chuyển hướng |

---

## 5. TỔNG KẾT NGUYÊN TẮC VẬN HÀNH AN TOÀN TRONG FABLAB
1. **Luôn Homing khi bắt đầu:** Mỗi khi mở nguồn hoặc reset cánh tay, luôn cho robot về gốc (Homing) để định vị encoder chính xác.
2. **Ưu tiên Mode 1 (`PTPMOVJXYZ`):** Không dùng mode 7 (`PTPMOVLXYZINC`) và cẩn trọng với mode 2 (`PTPMOVLXYZ`) gần ranh giới $R \approx 140\text{ mm}$ hoặc $R \approx 330\text{ mm}$.
3. **Theo dõi LED & Phục hồi:** Khi có còi hú và đèn đỏ $\to$ Click nút **[Xóa Lỗi]** trên Web UI (tương đương bộ 3 lệnh ID 20, 245, 240).
4. **Kiểm tra công cụ:** Luôn nhớ tính độ bù trừ $Z_{\text{TCP}} = Z_{\text{Flange}} - 59.5\text{ mm}$ khi lắp giác hút để tránh đâm mũi hút xuống mặt bàn.
