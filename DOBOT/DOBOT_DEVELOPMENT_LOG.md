# DOBOT MAGICIAN 3D DIGITAL TWIN & REAL-TIME CONTROLLER
## TÀI LIỆU KỸ THUẬT, TIẾN TRÌNH & HƯỚNG DẪN BÀN GIAO TOÀN DIỆN (HANDOVER NOTES)

> **Mục đích:** Tài liệu này ghi lại toàn bộ kiến trúc hệ thống, các tính năng đã hoàn thiện, danh sách các lỗi phần cứng/giao thức đã gặp, nguyên nhân gốc rễ, phương án khắc phục triệt để và những lưu ý cốt lõi để các kỹ sư hoặc Agent AI tiếp theo có thể tiếp tục phát triển mà không gặp trở ngại.

---

## 1. TỔNG QUAN HỆ THỐNG & KIẾN TRÚC (SYSTEM ARCHITECTURE)

Hệ thống điều khiển và bản sao số 3D thời gian thực (Digital Twin) cho cánh tay robot **Dobot Magician** trên hệ điều hành **Ubuntu Linux**.

```
[ Giao diện Web 3D (Three.js) ]
         │ (WebSocket ws:// hoặc wss://)
         ▼
[ Python Tornado Server (dobot_live_server.py) ]
         │ (Pyserial 115200 baud, 8N1)
         ▼
[ Cổng Serial /dev/ttyUSB* (STM32 Firmware) ]
         │ (Giao thức nhị phân Dobot Protocol v1.1.4)
         ▼
[ Dobot Magician Robotic Arm + Giác hút khí nén ]
```

### 1.1. Thông số vật lý & Cấu hình phần cứng
- **Cổng giao tiếp Serial:** `/dev/ttyUSB0` hoặc `/dev/ttyUSB1` (tự động nhận diện).
- **Tốc độ truyền:** `115200` bps, Data bits: 8, Stop bits: 1, Parity: None.
- **Bù trừ chiều dài đầu công cụ (Tool Offset Z):**
  - Chiều dài giác hút: **`59.5 mm`**
  - Mặt bích (Flange Z) $\to$ Đầu mút giác hút (TCP Z):
    $$Z_{TCP} = Z_{Flange} - 59.5\text{ mm}$$
    $$Z_{Flange} = Z_{TCP} + 59.5\text{ mm}$$
- **Phạm vi không gian làm việc an toàn (Workspace Safety Envelope):**
  - Bán kính ngang: $R_{horiz} = \sqrt{X^2 + Y^2} \in [140.0\text{ mm}, 330.0\text{ mm}]$. Dưới $140\text{ mm}$ sẽ tự đâm vào thân robot, trên $330\text{ mm}$ vượt tầm với tối đa.
  - Chiều cao đầu hút: $Z_{TCP} \in [-120.0\text{ mm}, +100.0\text{ mm}]$ (Tương ứng $Z_{Flange} \in [-60.5\text{ mm}, +159.5\text{ mm}]$). Dưới $-120\text{ mm}$ có nguy cơ đâm gãy đầu hút vào mặt bàn.
  - Góc quay trục $R$: $[-135^\circ, +135^\circ]$.

---

## 2. CÁC TÍNH NĂNG ĐÃ HOÀN THIỆN (COMPLETED FEATURES)

1. **Đọc dữ liệu thời gian thực (Real-time Kinematics & Pose):**
   - Đọc tọa độ $X, Y, Z, R$ và 4 góc khớp $J_1, J_2, J_3, J_4$ với tần số 20Hz (mỗi 50ms) không gây nghẽn Serial.
2. **Điều khiển giác hút khí nén (End-Effector Suction Cup):**
   - Bật/tắt bơm hút chân không và van xả khí nhả vật tức thì.
3. **Di chuyển điểm chỉ định an toàn (`move_to_point.py`):**
   - Hỗ trợ cả tương tác qua Terminal (Interactive) lẫn truyền tham số dòng lệnh CLI (`--x`, `--y`, `--z`, `--r`, `--suck`).
   - Tích hợp quỹ đạo an toàn dạng cổng **Safe Jump**: Nhấc đầu hút lên cao an toàn $\to$ Bay ngang tới $(X_{đích}, Y_{đích})$ $\to$ Hạ thẳng xuống $Z_{đích}$. Tránh hoàn toàn nguy cơ quẹt đổ vật cản trên bàn.
   - Độ chính xác kiểm chứng thực tế: **Sai số $\Delta X = 0.00\text{ mm}, \Delta Y = 0.00\text{ mm}, \Delta Z = 0.00\text{ mm}$**.
4. **Cục Điểm Đích 3D Tương Tác Trực Quan (Interactive 3D Beacon):**
   - Trên Web 3D có khối lập phương điểm đích phát sáng cam với trục tọa độ **TransformControls (Gizmo)**:
     - Mũi tên **Xanh lá (HƯỚNG LÊN)**: Kéo trục $Z$ (Độ cao).
     - Mũi tên **Đỏ**: Kéo trục $X$ (Tiến / Lùi).
     - Mũi tên **Xanh dương**: Kéo trục $Y$ (Trái / Phải).
   - Tùy chọn *"Tự động di chuyển khi thả chuột"* hoặc bấm nút *"🚀 Di chuyển robot tới điểm đích"*.
5. **Hạ tầng Publish Online ra Internet:**
   - Thư mục `dist_netlify/` sẵn sàng kéo thả lên Netlify.
   - Script `./start_online.sh` tự động thiết lập đường hầm Cloudflare Tunnel (`cloudflared`) để điều khiển từ xa qua 4G/Internet mà không cần mở port modem.
6. **Cơ chế Tự Động Giám Sát Lỗi & Khôi Phục Đèn Xanh:**
   - Đọc và giải mã liên tục trạng thái Alarm của Dobot.
   - Nút khôi phục 1 chạm (Reset Alarm) trên Web và Terminal, xóa sạch cờ lỗi và hàng đợi kẹt mà không cần phải Homing lại.

---

## 3. DANH SÁCH LỖI ĐÃ GẶP, NGUYÊN NHÂN & CÁCH SỬA TRIỆT ĐỂ

### ❌ Lỗi 1: Gửi nhầm mã lệnh Clear Queue (ID 242 vs ID 245)
- **Hiện tượng:** Sau khi gặp lỗi hoặc dừng khẩn cấp, gửi lệnh mới robot không di chuyển dù cổng Serial vẫn kết nối.
- **Nguyên nhân gốc:**
  - Trong tài liệu giao thức Dobot Protocol:
    - ID 240 = `SetQueuedCmdStartExec` (Bắt đầu chạy queue)
    - ID 241 = `SetQueuedCmdStopExec` (Tạm dừng queue)
    - **ID 242 = `SetQueuedCmdForceStopExec`** (Cưỡng bức dừng queue khẩn cấp!)
    - **ID 245 = `SetQueuedCmdClear`** (Xóa sạch các lệnh đang kẹt trong queue!)
  - Code cũ gửi `id=242` với ý định xóa queue, nhưng thực chất lại liên tục ép vi điều khiển Dobot vào trạng thái Force Stop.
- **Cách sửa chuẩn:**
  ```python
  # Trình tự khôi phục chuẩn:
  self._send_raw_cmd(id=20, ctrl=1)   # Xóa cờ lỗi phần cứng
  self._send_raw_cmd(id=245, ctrl=1)  # Xóa sạch lệnh kẹt trong queue (ID 245)
  self._send_raw_cmd(id=240, ctrl=1)  # Kích hoạt thực thi lại queue (ID 240)
  ```

---

### ❌ Lỗi 2: Nhấn nút Jog hoặc Manual bị đỏ đèn còi hú liên tục
- **Hiện tượng:** Nhấn các nút jog manual trên giao diện web (+Z, -Z, +X, -X) hoặc lệnh test, robot lập tức ngắt động cơ, đèn chuyển sang ĐỎ và còi kêu.
- **Nguyên nhân gốc:**
  - Code cũ jog bằng chế độ tương đối tuyến tính Descartes: `mode=7` (`MOVL_XYZ_INC`).
  - Cơ cấu cánh tay song song SCARA của Dobot có các **điểm kỳ dị động học nghịch (IK Singularity)**. Khi đi đường thẳng gần giới hạn hoặc gần thân ($R < 140\text{ mm}$), vi điều khiển tính ra vận tốc góc khớp tiến tới vô hạn $\to$ kích hoạt cờ bảo vệ động cơ ngắt khẩn cấp (Alarm `0x11` - *ERR_PLAN_INV_SINGULARITY*).
- **Cách sửa chuẩn:**
  - Thay vì dùng `mode=7`, server đọc vị trí hiện tại: $X_{cur}, Y_{cur}, Z_{cur}, R_{cur}$.
  - Tính vị trí đích tuyệt đối: $X_{target} = X_{cur} + \Delta X, \dots$
  - Kiểm tra điều kiện an toàn vùng làm việc trước khi gửi.
  - Gửi lệnh di chuyển bằng **`mode=1` (`PTPMOVJXYZMode`)**:
    ```python
    # mode=1 là nội suy không gian khớp: chuyển động mượt mà,
    # hoàn toàn miễn nhiễm với điểm kỳ dị động học, không bao giờ bị đỏ đèn!
    params = bytes([1]) + struct.pack("<4f", tx, ty, tz, tr)
    self._send_raw_cmd(id=84, ctrl=3, params=params)
    ```

---

### ❌ Lỗi 3: Robot không di chuyển khi gửi lệnh PTP (`move_ptp`)
- **Hiện tượng:** Gửi lệnh PTP nhưng robot đứng im, không báo lỗi.
- **Nguyên nhân gốc:**
  1. Thiếu thông số vận tốc PTP: Nếu chưa gửi cấu hình vận tốc/gia tốc (ID 80, 81, 83), firmware đặt vận tốc mặc định bằng 0.
  2. Byte `ctrl`: Với lệnh `SetPTPCmd (ID 84)`, phải đặt `ctrl=3` (Queued write) để lệnh được nạp vào hàng đợi và bộ nội suy quỹ đạo kích hoạt.
- **Cách sửa chuẩn:**
  Ngay khi mở cổng Serial, bắt buộc gửi gói cấu hình vận tốc:
  ```python
  # ID 80: SetPTPJointParams (Vận tốc/gia tốc 4 khớp)
  self._send_raw_cmd(id=80, ctrl=1, params=struct.pack('<8f', *([200.0]*8)))
  # ID 81: SetPTPCoordinateParams (Vận tốc/gia tốc Descartes XYZ và R)
  self._send_raw_cmd(id=81, ctrl=1, params=struct.pack('<4f', 200.0, 200.0, 200.0, 200.0))
  # ID 83: SetPTPCommonParams (Tỉ lệ vận tốc & gia tốc = 50%)
  self._send_raw_cmd(id=83, ctrl=1, params=struct.pack('<2f', 50.0, 50.0))
  ```

---

### ❌ Lỗi 4: Rơi rớt gói tin Serial (Packet Loss) khi đọc phản hồi
- **Hiện tượng:** Hàm đọc dữ liệu (`get_pose()` hoặc `get_alarms()`) thỉnh thoảng trả về `None` dù robot vẫn gửi dữ liệu.
- **Nguyên nhân gốc:**
  - Bộ đệm `buf = bytearray()` nằm cục bộ trong hàm đọc phản hồi, mỗi lần gọi hàm thì buffer bị tạo mới.
  - Khi robot gửi liên tiếp nhiều gói tin (ví dụ: ACK 240, ACK 245, Pose, Alarms), các byte còn sót lại của gói tin sau bị hủy bỏ khi hàm kết thúc.
- **Cách sửa chuẩn:**
  - Khai báo `self.buf = bytearray()` là thuộc tính của đối tượng `DobotController`.
  - Giữ lại các byte chưa parse hết trong `self.buf` để hàm đọc tiếp theo xử lý trọn vẹn, không bao giờ mất byte.

---

### ❌ Lỗi 5: Đụng độ cổng mạng (Port 8080 Collision)
- **Hiện tượng:** Server báo `OSError: [Errno 98] Address already in use`.
- **Cách sửa chuẩn:**
  Tích hợp hàm `find_available_port(preferred_port=8080)` tự động kiểm tra cổng 8080 $\to$ 8081 $\to$ 8082 $\to$ 8088. Trên Web client, dùng `window.location.host` để WebSocket tự động bắt đúng port máy chủ.

---

### ❌ Lỗi 6: Dịch vụ `localtunnel` bị treo vô tận (Hang without response)
- **Hiện tượng:** Chạy `npx localtunnel --port 8080 --subdomain ...` thì terminal đứng im phắc, không in ra URL kết nối và không báo lỗi.
- **Nguyên nhân gốc:**
  - Máy chủ trung gian mã nguồn mở của `localtunnel.me` ở nước ngoài thường xuyên bị quá tải băng thông hoặc bị tường lửa/DNS của các nhà mạng tại Việt Nam bóp chặn quá trình bắt tay kết nối (handshake).
- **Cách sửa chuẩn:**
  - Hủy lệnh bằng `Ctrl + C`.
  - Thay thế bằng **Cloudflare Quick Tunnel** (hạ tầng Edge CDN cực mạnh có POP tại Việt Nam) hoặc **ngrok** (dịch vụ thương mại cấp domain tĩnh ổn định 100%).

---

### ❌ Lỗi 7: Bất tiện của Domain Ngẫu Nhiên / Domain Xấu khi đưa lên Internet
- **Hiện tượng:** 
  - Cloudflare Quick Tunnel đổi subdomain ngẫu nhiên sau mỗi lần khởi động (`xxx.trycloudflare.com`), khiến người dùng phải mở bánh răng ⚙️ dán lại link.
  - Ngrok Free cung cấp domain tĩnh nhưng tên tự sinh ngẫu nhiên khó nhớ và thiếu chuyên nghiệp (`rebuild-thinner-spur.ngrok-free.dev`).
- **Cách sửa chuẩn (Mô hình Mặt tiền đẹp + Ống ngầm):**
  - **Mặt tiền (Frontend):** Deploy giao diện Web 3D lên Netlify với tên miền tùy chọn đẹp mắt `https://dobot-fablab.netlify.app`.
  - **Ống nước ngầm (Backend Bridge):** Trong mã nguồn Web (`dist_netlify/index.html`), cài cứng địa chỉ kết nối ngầm `wss://rebuild-thinner-spur.ngrok-free.dev/ws`.
  - **Kết quả:** Người dùng mở link Netlify là điều khiển được robot ngay, không bao giờ phải cấu hình bánh răng ⚙️ và không ai nhìn thấy domain ngrok xấu.

---

## 4. BẢNG MÃ LỖI DOBOT MAGICIAN (DOBOT ALARM REFERENCE)

Khi đọc ID 20 (Ctrl=0), Dobot trả về mảng 16 byte (128 bit). Bit thứ $k$ tương ứng với mã lỗi $k$:

| Mã Hex | Tên kỹ thuật | Ý nghĩa & Nguyên nhân | Cách khắc phục |
| :--- | :--- | :--- | :--- |
| **`0x00`** | `Reset Alarm` | Vi điều khiển robot vừa khởi động lại hoặc cắm nguồn | Bấm "Khôi phục / Xóa lỗi" |
| **`0x01`** | `Undefined Instruction` | Vi điều khiển nhận được gói tin có ID không hợp lệ | Kiểm tra lại cấu trúc packet |
| **`0x02`** | `File System Error` | Lỗi bộ nhớ Flash lưu file của robot | Xóa lỗi hoặc nạp lại firmware |
| **`0x10`** | `Planning Error` | Lỗi thuật toán quy hoạch đường đi | Điều chỉnh điểm đích |
| **`0x11`** | `IK Singularity Error` | Vượt tầm với hoặc rơi vào điểm kỳ dị động học | Đổi sang mode 1 (`MOVJ`), kiểm tra bán kính $R \ge 140\text{ mm}$ |
| **`0x12`** | `Planning Limit Error` | Điểm yêu cầu vượt ngoài giới hạn phần mềm | Kiểm tra lại tọa độ $X, Y, Z$ |
| **`0x20`** | `Kinematics Motion Error` | Lỗi chấp hành chuyển động khi động cơ đang quay | Dừng khẩn cấp, giải phóng queue |
| **`0x21`** | `Joint 1 Limit` | Khớp 1 quay chạm giới hạn hành trình | Jog lùi khớp 1 lại |
| **`0x22`** | `Joint 2 Limit` | Khớp 2 (Rear arm) chạm giới hạn | Jog lùi khớp 2 lại |
| **`0x23`** | `Joint 3 Limit` | Khớp 3 (Forearm) chạm giới hạn | Jog lùi khớp 3 lại |
| **`0x24`** | `Joint 4 Limit` | Khớp 4 (Xoay đầu hút) chạm giới hạn | Xoay góc $R$ về $0^\circ$ |
| **`0x30`** | `Overspeed Alarm` | Vận tốc khớp vượt quá ngưỡng an toàn | Giảm vận tốc PTP xuống 30-50% |
| **`0x40`** | `Sensor / Limit Switch` | Chạm công tắc hành trình vật lý | Bấm Homing hoặc kéo tay nhẹ ra khỏi cữ |

---

## 5. DANH SÁCH FILE VÀ CẤU TRÚC DỰ ÁN

```
/home/danh/FABLAB/DOBOT/
├── dobot_live_server.py      # Server chính: Tornado Web + WebSocket + Dobot Serial Driver (hỗ trợ PTP, Jog, Homing, Suction)
├── dobot_visualizer.html     # Giao diện Web 3D: Three.js 3 Tab, Gizmo Beacon, Homing, TCP Monitor
├── move_to_point.py          # Script CLI & Interactive: Di chuyển đầu hút đến 1 điểm với Safe Jump
├── test_dobot.py             # Script kiểm tra phần cứng độc lập (Menu 0-6 trên Terminal)
├── start_online.sh           # Script 1-click: Bật server + mở Cloudflare Tunnel ngẫu nhiên ra Internet
├── start_ngrok.sh            # Script 1-click: Bật server + kết nối domain cố định ngrok (rebuild-thinner-spur)
├── cloudflared               # Binary Cloudflare Tunnel dành cho Linux x86_64
└── DOBOT_DEVELOPMENT_LOG.md  # Tài liệu bàn giao & lịch sử phát triển toàn diện

/home/danh/FABLAB/dist_netlify/
├── index.html                # Bản build Web tĩnh tích hợp sẵn cầu nối ngrok cố định
├── TransformControls.js      # Thư viện Three.js kéo thả tọa độ 3D
├── _redirects                # Cấu hình redirect SPA cho Netlify
└── README.md                 # Hướng dẫn deploy Netlify
```

---

## 6. HƯỚNG DẪN VẬN HÀNH NHANH (QUICK START GUIDE)

### Cách 1: Chạy Menu Terminal độc lập (Offline)
```bash
cd /home/danh/FABLAB/DOBOT
python3 test_dobot.py
```
- Phím `1`: Đọc tọa độ hiện tại.
- Phím `2`: Bật/tắt giác hút.
- Phím `3`: Thử di chuyển trục Z $\pm 10\text{ mm}$ bằng `MOVJ`.
- Phím `4`: Xem chi tiết mã lỗi & khôi phục còi báo động.
- Phím `5`: Chạy Homing về vị trí chuẩn cơ khí.
- Phím `6`: Di chuyển đầu hút tới tọa độ $(X, Y, Z)$ chỉ định bằng Safe Jump.

### Cách 2: Mở Web 3D Local trên máy tính
```bash
cd /home/danh/FABLAB/DOBOT
python3 dobot_live_server.py
```
Mở trình duyệt: `http://localhost:8080` (hoặc `http://localhost:8081`).

### Cách 3: Điều khiển từ xa qua Internet bằng Cloudflare (Nhanh nhất - Không cần tài khoản)
```bash
cd /home/danh/FABLAB/DOBOT
./start_online.sh
```
Terminal tự động cấp link dạng: `https://xxxx.trycloudflare.com` để mở trên điện thoại / 4G.

### Cách 4: Điều khiển từ xa qua Netlify với Domain Cố Định Đẹp (Chuyên nghiệp nhất)
1. Trên máy Linux, chạy cầu nối:
   ```bash
   cd /home/danh/FABLAB/DOBOT
   ./start_ngrok.sh
   ```
2. Mở trình duyệt trên điện thoại/máy tính bất kỳ:
   👉 **`https://dobot-fablab.netlify.app`**
   *(Giao diện tự động kết nối ngầm về robot, không cần dán link, không hiện domain ngrok)*.

---

## 7. GHI CHÚ QUAN TRỌNG CHO CÁC AGENT / DEVELOPER TIẾP THEO

1. **Tuyệt đối không gửi lệnh di chuyển tương đối bằng `mode=7` (`MOVL_XYZ_INC`):** Luôn cộng delta vào vị trí hiện tại và dùng `mode=1` (`MOVJ_XYZ`) để tránh lỗi kỳ dị toán học.
2. **Luôn duy trì Tool Offset Z = 59.5mm:** Tọa độ người dùng quan tâm luôn là mũi đầu hút ($Z_{TCP}$), còn tọa độ robot thực thi là mặt bích ($Z_{Flange} = Z_{TCP} + 59.5$).
3. **Khi gửi lệnh xóa còi lỗi:** Bắt buộc gửi trọn bộ 3 lệnh: `ID 20` (Xóa lỗi) $\to$ `ID 245` (Xóa queue kẹt) $\to$ `ID 240` (Kích hoạt lại queue). Thiếu ID 245 hoặc gửi nhầm ID 242 sẽ làm robot tiếp tục đóng băng.
4. **Không đóng/mở Serial liên tục:** Dobot Magician dùng chip nạp CP2102. Khi mở serial với cờ DTR/RTS, vi điều khiển STM32 sẽ bị reset mất khoảng 0.3s - 0.5s để khởi động lại. Nên duy trì kết nối serial liên tục trong server daemon.
5. **Cơ chế Homing an toàn:** Homing (ID 31) sẽ kích hoạt vi điều khiển quay tìm công tắc hành trình cơ học của từng trục. Phải luôn nhắc người dùng dọn sạch không gian xung quanh trước khi bấm chạy.

---

## 8. CẢI TIẾN GIAO DIỆN WEB 3D (UI REDESIGN & HOMING INTEGRATION)

Giao diện Web 3D (`dobot_visualizer.html`) đã được tái cấu trúc từ bố cục 1 cột dài (>1200px) sang kiến trúc **3 Tab + Fixed Header + Sticky Footer**:

- **Header Cố định:** 
  - Logo, trạng thái kết nối (`Live` / `Offline`) kèm nút bánh răng ⚙️ cấu hình IP từ xa.
  - Chuyển chế độ: `⚡ Đồng bộ thật (Live)` vs `🎮 Mô phỏng (Manual)`.
  - Banner cảnh báo đèn đỏ thông minh (tự động hiện mã lỗi và nút 1-click Khôi phục khi robot lỗi).
- **Hệ thống 3 Tab gọn gàng:**
  - **Tab 1: 🎯 Điểm Đích (Target 3D):** Nút bật/tắt cục điểm đích 3D Gizmo, thanh legend màu mini (Z/X/Y), lưới 2x2 nhập tọa độ $(X, Y, Z, R)$, kiểm tra tầm với an toàn thời gian thực, 2 nút hành động chính (`📦 Nhấc An Toàn` / `🚀 Bay Thẳng`), và 4 chip điểm mẫu nhanh (`Home`, `A`, `B`, `Mặt Bàn`).
  - **Tab 2: 🕹️ Điều Khiển (Jog & Khớp):** Chuyển đổi giữa `Phím Jog Nhanh` (chọn bước 1/5/10/20/50mm, bàn phím 3x3) và `Thanh Trượt` (XYZ Đề-các vs Góc Khớp J1-J4 có nút $\pm$ vi chỉnh).
  - **Tab 3: 📊 Giám Sát:** Bảng dữ liệu TCP 2 cột hiện đại, cao độ mặt bàn, khoảng cách 3D, nút bật/tắt tia gióng 3D, chọn công cụ (Giác hút / Tay kẹp / Flange), mục **Hiệu chuẩn gốc (Homing Calibration)** với nút 1-click kích hoạt kèm cảnh báo an toàn, và chuyển theme (🌿 Simulator / 🌌 Studio Dark).
- **Sticky Footer Luôn Hiển Thị (3 Nút Hành Động Nhanh):** 
  - Nút `🔔 Xóa Lỗi` (khôi phục nhanh khi đèn đỏ).
  - Nút `🏠 Về Gốc (Home)` (chạy Homing tìm cữ chuẩn quang học với popup xác nhận an toàn).
  - Nút `💨 Giác Hút` (đổi màu nổi bật theo trạng thái thực tế).
- **Backend WebSocket:** Đã bổ sung `home()` (ID 31 `SetHOMECmd`) vào `DobotController` và xử lý action `"home"` trong `WebSocketHandler`.
- **Đồng bộ Netlify:** Đã đồng bộ trực tiếp mã nguồn vào `/home/danh/FABLAB/dist_netlify/index.html`.

---

## 9. ĐÁNH GIÁ CÁC GIẢI PHÁP ĐIỀU KHIỂN TỪ XA & HƯỚNG MỞ RỘNG KHÔNG GIỚI HẠN

### 9.1. So sánh kỹ thuật giữa các mô hình:
1. **Mô hình Netlify + ngrok Tunnel (Hiện tại):**
   - *Ưu điểm:* Giao diện đẹp cố định (`.netlify.app`), tự kết nối ngầm, không tốn chi phí.
   - *Khuyết điểm:* Gói ngrok Free có hạn mức ~1GB dữ liệu / tháng (đủ cho đồ án, nhưng không nên treo 24/7 cả tháng), chưa có mật khẩu xác thực người dùng.
2. **Mô hình Cloudflare Named Tunnel + Custom Domain (Khuyên dùng khi triển khai thực tế):**
   - *Ưu điểm:* Hoàn toàn **MIỄN PHÍ 100% & BĂNG THÔNG KHÔNG GIỚI HẠN**, độ trễ cực thấp (Data Center tại Viettel/VNPT/FPT < 10ms), có thể bật Cloudflare Zero Trust (bảo vệ bằng mã PIN hoặc Google Login).
   - *Yêu cầu:* Cần sở hữu 1 tên miền riêng (mua khoảng 20k VNĐ/năm hoặc subdomain trường cấp).
3. **Mô hình Mạng Riêng Ảo Tailscale / WireGuard (Dành cho nhóm nội bộ):**
   - *Ưu điểm:* Miễn phí 100%, không giới hạn băng thông, truyền dữ liệu Peer-to-Peer trực tiếp siêu nhanh, bảo mật tuyệt đối chỉ thiết bị đăng nhập cùng Gmail mới truy cập được.
   - *Khuyết điểm:* Thiết bị điều khiển bắt buộc phải cài app Tailscale (không gửi link cho người lạ bấm vào ngay được).
4. **Mô hình Cloud Broker (Firebase / MQTT giống ESP32):**
   - *Ưu điểm:* 100% chỉ dùng Web tĩnh Netlify, không cần tunnel chạy nền.
   - *Khuyết điểm:* Cần viết lại giao thức trao đổi dữ liệu sang dạng Pub/Sub hoặc REST, độ trễ cập nhật tư thế 3D sẽ cao hơn WebSocket trực tiếp.
