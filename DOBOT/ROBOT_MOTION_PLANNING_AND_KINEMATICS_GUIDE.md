# GIÁO TRÌNH NỀN TẢNG: ĐỘNG HỌC & CÁC THUẬT TOÁN QUY HOẠCH QUỸ ĐẠO CÁNH TAY ROBOT
**Dành cho Kỹ sư, Lập trình viên & Học viên FABLAB**

---

## 1. BẢN CHẤT CỦA BÀI TOÁN: TỪ ĐIỂM A ĐẾN ĐIỂM B TRONG ROBOTICS

Khi con người bảo: *"Hãy đưa bàn tay từ vị trí A sang vị trí B"*, não bộ của chúng ta tự động ước lượng không gian, né tránh các vật cản trên đường và điều khiển hàng chục nhóm cơ bắp co giãn nhịp nhàng.

Đối với một cánh tay robot công nghiệp (như Dobot Magician):
- Robot **không có mắt nhìn tự nhiên** (nếu không gắn camera thị giác máy tính).
- Robot **chỉ có các động cơ quay quanh trục** (Joints/Motors).
- Tọa độ mục tiêu bạn muốn đến lại nằm trong **hệ tọa độ không gian 3 chiều của thế giới thực (Cartesian Space: X, Y, Z)**.

Do đó, để đi từ điểm A đến điểm B, hệ thống phải giải quyết đồng thời 3 câu hỏi lớn:
1. **Động học nghịch (IK):** Để đầu gắp đứng ở $(X, Y, Z)$, mỗi khớp của robot phải quay góc bao nhiêu độ?
2. **Quy hoạch đường đi (Path Planning):** Giữa A và B có vật cản không? Đầu gắp nên đi thẳng, đi cong hay nhảy hình cổng?
3. **Quy hoạch quỹ đạo theo thời gian (Trajectory Generation):** Động cơ tăng tốc thế nào, chạy đều ra sao, hãm tốc lúc nào để robot không bị giật, rung lắc hoặc cháy động cơ?

> [!NOTE]
> **Phân biệt "Đường đi" (Path) và "Quỹ đạo" (Trajectory):**
> - **Đường đi (Path):** Chỉ thuần túy là chuỗi các điểm hình học trong không gian mà đầu robot sẽ đi qua (ví dụ: một đường thẳng hay một parabol). Không có khái niệm thời gian.
> - **Quỹ đạo (Trajectory):** Là **Đường đi + Yếu tố thời gian** ($\text{Vị trí}(t), \text{Vận tốc}(t), \text{Gia tốc}(t)$). Đây mới là thứ thực sự được nạp vào vi điều khiển để điều khiển động cơ.

---

## 2. TẠI SAO KHÔNG PHẢI CHỈ ĐƠN GIẢN LÀ MỘT ĐƯỜNG THẲNG?

Nhiều người mới tiếp cận Robot thường nghĩ: *"Từ A đến B thì cứ kẻ một đường thẳng nối 2 điểm rồi cho robot đi theo là tối ưu và đơn giản nhất chứ?"*

Thực tế trong cơ điện tử và robotics, **"đi thẳng" lại là một trong những chuyển động phức tạp, nguy hiểm và tiêu tốn tài nguyên nhất**.

### 2.1. Nghịch lý giữa Không gian Descartes và Không gian Khớp
- **Mắt người nhìn:** Thấy đầu gắp đi theo một đường thẳng tắp rất tự nhiên.
- **Thực tế cơ học phía sau:** Động cơ không thể "đi thẳng". Động cơ chỉ có thể **quay tròn**.
- Để đầu mũi robot di chuyển trên một đoạn thẳng tắp trong không gian, các góc khớp phải liên tục biến thiên với các hàm lượng giác phi tuyến cực kỳ phức tạp. Khớp vai có thể phải quay chậm lại trong khi khớp cùi chỏ lại phải tăng tốc đột ngột để bù trừ độ lệch.

### 2.2. Hiểm họa "Điểm kỳ dị" (Kinematic Singularity)
Đây là lý do số 1 khiến các kỹ sư điều khiển robot đau đầu:
- **Khái niệm:** Điểm kỳ dị là vị trí mà tại đó cánh tay robot bị mất đi một hoặc nhiều bậc tự do di chuyển (ví dụ: khi cánh tay duỗi thẳng tắp ra hết cỡ, hoặc khi gập sát vào thân).
- **Hậu quả:** Tại điểm kỳ dị, ma trận Jacobian bị suy biến ($\det(J) = 0$). Để đầu gắp giữ nguyên vận tốc đi thẳng qua điểm đó, **vận tốc góc của động cơ bước phải tiến tới vô cùng ($\omega \to \infty$)**.
- **Hiện tượng thực tế:** Động cơ bước bị đuối lực, khựng giật cơ học dữ dội, chip vi điều khiển quá tải, còi báo động hú liên tục và robot khóa cứng ngắt nguồn điện (đèn LED chuyển màu đỏ).

### 2.3. Rủi ro va chạm vật lý trên mặt bàn làm việc
Trong các ứng dụng gắp thả (Pick and Place):
- Điểm lấy hàng và điểm thả hàng thường nằm sát mặt bàn ($Z \approx -50\text{ mm}$).
- Giữa 2 điểm có thể có chướng ngại vật (hộp linh kiện, cốc nước, phôi chưa gắp, cạnh bàn).
- Nếu robot đi thẳng nối liền 2 điểm $\to$ Mũi hút sẽ quét ngang qua mặt bàn ở độ cao thấp, húc đổ mọi vật cản hoặc gãy đầu giác hút.

---

## 3. CÁC THUẬT TOÁN DI CHUYỂN PHỔ BIẾN HIỆN NAY (SO SÁNH ƯU & NHƯỢC ĐIỂM)

Trong ngành công nghiệp robot (từ Dobot, ABB, KUKA đến Universal Robots), các thuật toán điều khiển di chuyển được chia thành 4 nhóm chính:

```
                  CÁC THUẬT TOÁN DI CHUYỂN ROBOT
                                │
   ┌────────────────┬───────────┴───────────┬────────────────┐
   ▼                ▼                       ▼                ▼
Nhóm 1: PTP      Nhóm 2: Cartesian       Nhóm 3: Bậc cao   Nhóm 4: Tự động
(Nội suy khớp)   (Nội suy thẳng/tròn)    (Spline, Bézier)  (RRT, PRM, AI)
```

---

### Nhóm 1: Nội suy không gian khớp (PTP Joint Interpolation - MOVJ)
*Phương pháp:* Không quan tâm đầu gắp đi đường cong méo mó thế nào trong không gian 3D. Thuật toán chỉ lấy góc ban đầu $(J_1^A, J_2^A, J_3^A)$ và góc đích $(J_1^B, J_2^B, J_3^B)$, sau đó xoay đều các khớp để cùng bắt đầu và cùng dừng lại cùng một lúc.

* **Điểm mạnh:**
  - **Miễn nhiễm 100% với điểm kỳ dị (Singularity):** Không bao giờ bị lỗi quá tốc độ động cơ hay đỏ đèn.
  - **Tiết kiệm năng lượng và êm ái nhất:** Các khớp chuyển động với vận tốc đều, động cơ ít chịu ứng suất xoắn.
  - **Tính toán cực nhanh:** Vi điều khiển giá rẻ (như STM32, Arduino) có thể tính toán xong trong vài chục microsecond.
* **Điểm yếu:**
  - Đầu gắp đi theo một đường cong hình cung trong không gian, mắt người không dự đoán chính xác được đường đi nếu môi trường có nhiều vật cản chật hẹp.
* **Ứng dụng:** Di chuyển nhanh tự do trong không gian thoáng, gắp thả linh kiện, hàn điểm (Spot Welding).

---

### Nhóm 2: Nội suy không gian thực (Cartesian Linear/Circular - MOVL / MOVC)
*Phương pháp:* Ép đầu gắp phải bám theo một đường thẳng tắp (MOVL) hoặc một cung tròn hoàn hảo (MOVC) trong không gian $XYZ$. Thuật toán chia đường thẳng thành hàng nghìn điểm cực nhỏ cách nhau vài mili-giây, và giải bài toán động học nghịch IK liên tục tại từng điểm.

* **Điểm mạnh:**
  - Đường đi thẳng tuyệt đối, con người nhìn vào thấy rất trực quan và an toàn khi thao tác gần vật cản.
  - Rút ngắn khoảng cách không gian giữa 2 điểm.
* **Điểm yếu:**
  - **Dễ dính điểm kỳ dị:** Nếu đường thẳng vô tình cắt ngang qua vùng gần thân robot hoặc duỗi thẳng cánh tay $\to$ Lỗi hệ thống lập tức.
  - Động cơ phải liên tục tăng/giảm tốc phi tuyến, dễ gây rung lắc nếu bộ khung cơ khí không đủ cứng vững.
* **Ứng dụng:** Bôi keo, tra dầu, cắt Laser/Plasma, hàn đường liên tục (Seam Welding), luồn đầu công cụ vào khe hẹp.

---

### Nhóm 3: Đường cong liên tục bậc cao (Spline / B-Spline / Bézier)
*Phương pháp:* Khi robot phải đi qua một chuỗi nhiều điểm liên tiếp ($A \to B \to C \to D$), thay vì đến từng điểm rồi khựng lại dừng hẳn rồi mới đi tiếp, thuật toán tạo ra một đường cong mềm mại "lướt" qua các điểm với gia tốc liên tục bậc 2 (không bị gián đoạn đạo hàm gia tốc).

* **Điểm mạnh:**
  - Robot di chuyển với tốc độ cực cao mà không bị rung giật ở các khúc cua.
  - Thời gian hoàn thành chu trình sản xuất (Cycle time) nhanh hơn 30% - 50%.
* **Điểm yếu:**
  - Thuật toán toán học phức tạp, yêu cầu bộ vi xử lý có bộ tính dấu phẩy động (FPU) mạnh.
  - Nếu bán kính cua lớn, đầu robot có thể bị "văng" ra ngoài tọa độ mong muốn (Blend Tolerance).
* **Ứng dụng:** Sơn công nghiệp, phay CNC cánh tay robot, vẽ tranh nghệ thuật.

---

### Nhóm 4: Quy hoạch đường đi tự động trong không gian ngẫu nhiên (RRT / PRM / TrajOpt)
*Phương pháp:* Thường kết hợp với cảm biến đo khoảng cách LiDAR hoặc Camera chiều sâu 3D (Intel RealSense). Robot xây dựng bản đồ không gian chứa các vật cản ngẫu nhiên, sau đó thuật toán (như *Rapidly-exploring Random Tree*) bắn các nhánh cây ngẫu nhiên trong không gian để tự tìm một đường uốn lượn né sạch mọi chướng ngại vật mà không cần người lập trình phải dạy từng điểm.

* **Điểm mạnh:** Tự hành hoàn toàn, thích ứng với môi trường làm việc thay đổi liên tục khi có người đi lại.
* **Điểm yếu:** Đòi hỏi máy tính công nghiệp mạnh (IPC chạy ROS/ROS2, GPU), thời gian tính toán mất từ vài trăm mili-giây đến vài giây.
* **Ứng dụng:** Robot kho hàng, cánh tay robot gắp hàng lộn xộn trong thùng (Bin Picking), robot y tế phẫu thuật.

---

### 📊 Bảng so sánh tổng hợp các phương pháp

| Thuật toán | Quỹ đạo đầu gắp | Tốc độ tính toán | Nguy cơ dính lỗi kỳ dị | Rung lắc cơ khí | Ứng dụng phù hợp nhất |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PTP (MOVJ)** | Đường cong tự nhiên | ⚡ Cực nhanh ($< 0.1\text{ ms}$) | 🟢 **Không bao giờ bị** | Rất thấp (êm) | Gắp thả nhanh, Homing |
| **Linear (MOVL)** | Đoạn thẳng tuyệt đối | 🟡 Trung bình ($1 - 5\text{ ms}$) | 🔴 **Rất cao khi gần thân/xa** | Trung bình | Cắt gọt, bôi keo, luồn khe |
| **Spline / B-Spline**| Đường uốn lượn mượt | 🟠 Khá nặng ($10 - 20\text{ ms}$) | 🟡 Có nguy cơ | Rất thấp (lướt mượt) | Sơn, phay, vẽ liên tục |
| **RRT / PRM (AI)** | Tự né tránh vật cản | 🔴 Rất nặng ($100 - 2000\text{ ms}$) | 🟡 Phụ thuộc đường tìm | Phụ thuộc quỹ đạo | Môi trường có người/vật cản ngẫu nhiên |

---

## 4. THUẬT TOÁN HỆ THỐNG DOBOT CỦA CHÚNG TA ĐANG DÙNG LÀ GÌ?

Trong dự án Dobot Magician FABLAB của chúng ta, chúng ta đang sử dụng một **Kiến trúc phối hợp 2 tầng (Hybrid Two-Stage Motion Architecture)** cực kỳ thông minh:

```
[ Giao diện Web / Python ]
          │
          ▼
TẦNG 1: Thuật toán Cổng An Toàn (Safe Arch / Jump Trajectory)
          │  Chia thành 3 điểm trung gian: [Nhấc Z] ➔ [Bay ngang] ➔ [Hạ Z]
          ▼
TẦNG 2: Thuật toán Nội suy góc khớp PTPMOVJ (Mode 1) + S-Curve Profile trên STM32
          │  Nội suy góc khớp đồng bộ, triệt tiêu kỳ dị, làm mượt gia tốc
          ▼
[ Động cơ quay êm ái, an toàn 100% ]
```

### Chi tiết cách hoạt động:
1. **Ở Tầng 1 (Cấp Python - `dobot_live_server.py`):**
   - Khi bạn bấm tọa độ đích hoặc kéo Beacon 3D trên Web, server không gửi lệnh đi chéo trực tiếp.
   - Server tính toán ra một quỹ đạo hình cổng gồm 3 chặng:
     - **Chặng 1 (Nhấc cao):** Giữ nguyên $X, Y$ hiện tại, nhấc thẳng trục $Z$ lên $Z_{\text{safe}} = \max(Z_{\text{hiện tại}}, Z_{\text{đích}}) + 25\text{ mm}$.
     - **Chặng 2 (Bay ngang):** Di chuyển trên cao độ an toàn $Z_{\text{safe}}$ đến tọa độ $(X_{\text{đích}}, Y_{\text{đích}})$. Lúc này đầu hút đã bay cao bên trên mọi vật cản.
     - **Chặng 3 (Hạ xuống):** Giữ nguyên $(X_{\text{đích}}, Y_{\text{đích}})$, hạ thẳng trục $Z$ xuống độ cao làm việc $Z_{\text{đích}}$.

2. **Ở Tầng 2 (Cấp Firmware STM32 của Dobot):**
   - Mỗi chặng trong 3 chặng trên đều được gửi đi với chế độ **`mode 1` (`PTPMOVJXYZ`)**.
   - Bộ điều khiển tính toán thời gian đồng bộ cho cả 4 khớp: khớp nào đi xa nhất sẽ làm chuẩn, các khớp còn lại chạy chậm lại tương ứng để cùng về đích đúng một thời điểm $t = T$.
   - Đồng thời áp dụng **Cấu hình vận tốc chữ S (S-Curve Velocity Profile)**: Gia tốc tăng dần từ 0 $\to$ Vận tốc đều $\to$ Hãm tốc từ từ về 0.

### Đánh giá Ưu & Nhược điểm giải pháp của chúng ta:
* **Điểm mạnh (Ưu điểm vượt trội):**
  - **Miễn dịch 100% với lỗi đỏ đèn (Singularity):** Kể từ khi chuyển sang cơ chế này, robot không còn bị rú còi hay kẹt lỗi phần cứng.
  - **Bảo vệ an toàn vật cản:** Nhờ có quỹ đạo Jump, mũi hút không bao giờ quẹt ngang làm vỡ phôi hay gãy đầu giác hút.
  - **Bảo vệ tuổi thọ cơ khí:** Nhờ S-Curve và đồng bộ góc khớp, cánh tay dừng lại không bị giật hay nảy (overshoot).
* **Điểm yếu:**
  - Thời gian di chuyển lâu hơn một chút so với đi đường chéo trực tiếp (vì phải nhấc lên rồi mới hạ xuống).
  - Không dùng để vẽ hình nét thẳng tắp trên mặt phẳng được (nếu muốn vẽ tranh hay cắt decal, bắt buộc phải dùng chế độ nội suy thẳng `MOVL` hoặc nội suy cung tròn).

---

## 5. ĐỘNG HỌC NGHỊCH (INVERSE KINEMATICS - IK) LÀ GÌ?

### 5.1. Câu hỏi lớn: "Chỉ cần đưa tọa độ là nó tự xuất ra được góc của từng khớp hay sao?"
**Câu trả lời ngắn gọn:** Đúng là máy tính sẽ xuất ra góc của từng khớp từ tọa độ bạn nhập, **NHƯNG quá trình xử lý ngầm phía sau không hề đơn giản như một công thức cộng trừ!**

Cụ thể, có 3 thử thách lớn mà thuật toán IK phải giải quyết:

#### Thử thách 1: Vấn đề đa nghiệm (Multiple Solutions)
Một cánh tay robot để chạm được vào điểm $(X, Y, Z)$ trên bàn, nó có thể dùng nhiều tư thế khác nhau:
- **Tư thế cùi chỏ ngửa lên (Elbow Up)** hoặc **Tư thế cùi chỏ chúc xuống (Elbow Down)**.
- **Tư thế xoay đế sang trái** hoặc **Xoay đế sang phải**.

Nếu thuật toán IK không thông minh, ở điểm A nó chọn tư thế *Elbow Up*, sang điểm B nó lại giải ra nghiệm *Elbow Down* $\to$ Robot sẽ vung cả cánh tay vòng qua đầu rất nguy hiểm để đổi tư thế. Thuật toán IK thực tế phải luôn so sánh các nghiệm với vị trí hiện tại và chọn **nghiệm có độ lệch góc nhỏ nhất**.

#### Thử thách 2: Vùng vô nghiệm (Out of Reach & Collisions)
- Nếu bạn nhập $X = 500\text{ mm}$, trong khi tầm với cánh tay tối đa chỉ có $330\text{ mm}$, phương trình toán học giải tam giác sẽ xuất hiện giá trị $\cos(\beta) > 1$.
- Trong toán học, $\arccos(>1)$ là **vô nghiệm** (không tồn tại góc thực tế nào thỏa mãn). Lúc này robot phải phát cờ báo lỗi chứ không được phép chạy.

#### Thử thách 3: Hai trường phái giải Động học nghịch (IK)

1. **Phương pháp Giải tích hình học (Analytical / Geometric Method):**
   - Áp dụng các định lý lượng giác cổ điển (Định lý Pythagoras, Định lý hàm Cosin).
   - **Đặc điểm:** Chỉ áp dụng được cho các robot có cấu trúc hình học đặc biệt thỏa mãn điều kiện Pieper (như robot SCARA, Dobot 4 trục, robot 6 trục có 3 trục cổ tay đồng quy).
   - **Ưu điểm:** Tính toán cực nhanh (dưới 10 microsecond), chính xác tuyệt đối, xuất ngay ra công thức đại số đóng. **Dobot Magician sử dụng phương pháp này**.
2. **Phương pháp Lặp số (Numerical / Optimization Method):**
   - Dùng ma trận Jacobian nghịch đảo kết hợp thuật toán tối ưu hóa (như Newton-Raphson, Levenberg-Marquardt).
   - **Đặc điểm:** Dùng cho robot hình thù tự do, robot 7 trục hoặc nhiều bậc tự do thừa (Redundant Robots).
   - **Ưu điểm:** Giải được cho mọi loại robot, nhưng tốn nhiều phép tính lặp, có thể hội tụ chậm hoặc rơi vào cực tiểu cục bộ.

---

## 6. CÁC PHƯƠNG PHÁP SINH RA ĐƯỜNG ĐI THEO THỜI GIAN (VELOCITY PROFILING)

Khi đã có góc xuất phát $\theta_{\text{đầu}}$ và góc đích $\theta_{\text{đích}}$, câu hỏi đặt ra là: **Trong từng phần nghìn giây, động cơ phải quay với vận tốc bao nhiêu?**

Có 2 cấu hình vận tốc kinh điển trong ngành điều khiển:

```
1. CẤU HÌNH HÌNH THANG (Trapezoidal)      2. CẤU HÌNH CHỮ S (S-Curve)

       Vận tốc                                 Vận tốc
          ▲                                       ▲
     V_max ├───╭─────────╮                   V_max ├───╭─────────╮
           │  /           \                        │  /           \
           │ /             \                       │ /             \
           │/               \                      │/               \
         0 └┴───────┴───────┴──► Thời gian       0 └┴───────┴───────┴──► Thời gian
            Tăng    Đều   Giảm                      Tăng   Đều   Giảm
            tốc           tốc                       tốc          tốc
       Gia tốc: Bị gãy khúc đột ngột!          Gia tốc: Tăng/giảm mượt mà (Jerk êm)
```

### 1. Cấu hình hình thang (Trapezoidal Velocity Profile):
- **Nguyên lý:** Gia tốc $a$ là một hằng số. Động cơ tăng tốc đều $\to$ Chạy ở vận tốc không đổi $V_{\max}$ $\to$ Hãm phanh đều về 0.
- **Nhược điểm:** Tại thời điểm bắt đầu chuyển từ tăng tốc sang chạy đều, hoặc từ chạy đều sang giảm tốc, gia tốc bị nhảy cóc tức thời. Đạo hàm của gia tốc (gọi là **Jerk** - Độ giật) tiến tới vô cùng $\to$ Robot bị giật khựng cơ khí, gây mòn nhông hộp số và rung lắc đầu gắp.

### 2. Cấu hình chữ S (S-Curve Velocity Profile):
- **Nguyên lý:** Khống chế độ giật Jerk ở mức giới hạn ($Jerk = \frac{da}{dt} = \text{const}$).
- Gia tốc không tăng đột ngột mà tăng từ từ theo đường dốc mềm $\to$ Đồ thị vận tốc uốn cong thành hình chữ S mềm mại.
- **Ưu điểm:** Khử rung cơ khí hoàn toàn, bảo vệ bánh răng, giúp vật được giác hút giữ chặt không bị trượt văng khi robot di chuyển tốc độ cao.

---

## 7. BẢN ĐỒ KHÁI NIỆM CỐT LÕI (ROBOTICS CHEAT SHEET)

| Khái niệm | Ý nghĩa kỹ thuật | Ví dụ thực tế trên Dobot Magician |
| :--- | :--- | :--- |
| **Bậc tự do (DOF)** | Số lượng trục chuyển động độc lập của robot | Dobot có **4 DOF** ($J_1$: Đế, $J_2$: Vai, $J_3$: Khuỷu, $J_4$: Xoay đầu hút) |
| **Không gian Descartes (Cartesian)** | Tọa độ không gian 3D của thế giới thực | $(X, Y, Z, R)$ tính bằng milimet và độ |
| **Không gian Cấu hình (Joint Space / C-Space)** | Không gian các góc quay của từng động cơ | $(J_1, J_2, J_3, J_4)$ tính bằng độ góc quay trục |
| **Động học thuận (FK)** | Biết góc các khớp $\to$ Tìm vị trí đầu hút | Đọc cảm biến Encoder $\to$ Hiển thị mô hình cánh tay 3D lên Web |
| **Động học nghịch (IK)** | Biết vị trí muốn đến $\to$ Tìm góc các khớp | Nhập tọa độ đích trên Web $\to$ Chip tính ra các góc quay cần nạp vào motor |
| **Điểm kỳ dị (Singularity)**| Điểm hình học làm vận tốc khớp tiến tới vô cực | Bán kính tay duỗi quá $330\text{ mm}$ hoặc co sát trục đế $< 140\text{ mm}$ |
| **Độ lặp lại (Repeatability)** | Sai số khi quay lại cùng một vị trí nhiều lần | Dobot đạt $\pm 0.2\text{ mm}$ |
| **Tải trọng (Payload)** | Khối lượng tối đa robot mang được ở đầu công cụ | Dobot nâng tối đa $500\text{ g}$ |
