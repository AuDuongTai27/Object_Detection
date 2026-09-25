"""
Công cụ chụp ảnh mẫu trực tiếp từ Camera / Webcam.
Hỗ trợ:
- Nhấn trực tiếp các NÚT BẤM BẰNG CHUỘT trên cửa sổ Camera
- Hoặc bấm phím tắt trên bàn phím (SPACE, C, S, Q)
- Tự động nhận diện và chuyển đổi giữa Webcam và Camera USB ngoài
"""

import os
import sys
import time
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

try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass

WINDOW_NAME = "Camera Capture - Teachable Machine"

# Trạng thái toàn cục cho tương tác chuột
mouse_action = None


def on_mouse_click(event, x, y, flags, param):
    global mouse_action
    if event == cv2.EVENT_LBUTTONDOWN:
        buttons = param.get("buttons", [])
        for btn in buttons:
            bx1, by1, bx2, by2 = btn["rect"]
            if bx1 <= x <= bx2 and by1 <= y <= by2:
                mouse_action = btn["action"]
                break


def detect_available_cameras(max_tested=4):
    """Quét tìm tất cả camera (cả webcam và camera USB ngoài)."""
    available_cams = []
    os.environ["OPENCV_LOG_LEVEL"] = "OFF"
    for i in range(max_tested):
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(i, backend)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                available_cams.append((i, f"{w}x{h}"))
            cap.release()
    return available_cams


def open_camera(cam_index):
    """Mở camera với DirectShow trên Windows để tránh bị đơ/treo."""
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(cam_index, backend)
    # Cấu hình kích thước khung hình
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cap


def draw_ui(frame, class_name, cam_idx, img_counter, flash_message=""):
    """Vẽ giao diện hiển thị và các NÚT BẤM tương tác được bằng chuột."""
    h, w = frame.shape[:2]
    ui_frame = frame.copy()

    # --- 1. Thanh tiêu đề phía trên ---
    cv2.rectangle(ui_frame, (0, 0), (w, 45), (25, 25, 25), -1)
    cam_type = "USB Cam" if cam_idx > 0 else "Laptop Cam"
    title_text = f"Class: {class_name}  |  Camera [{cam_idx} - {cam_type}]  |  Da chup: {img_counter} anh"
    cv2.putText(ui_frame, title_text, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # --- 2. Khung ngắm vật thể ở giữa màn hình ---
    box_size = int(min(h, w) * 0.45)
    x1 = (w - box_size) // 2
    y1 = (h - box_size) // 2 - 20
    cv2.rectangle(ui_frame, (x1, y1), (x1 + box_size, y1 + box_size), (0, 255, 255), 2)
    cv2.putText(ui_frame, "Dat vat the vao giua khung", (x1 + 10, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    # --- 3. Thông báo chụp thành công (nếu có) ---
    if flash_message:
        cv2.putText(ui_frame, flash_message, (x1, y1 + box_size + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 100), 2)

    # --- 4. Thanh điều khiển & NÚT BẤM BẰNG CHUỘT phía dưới ---
    bar_height = 70
    bar_y1 = h - bar_height
    cv2.rectangle(ui_frame, (0, bar_y1), (w, h), (35, 35, 35), -1)

    # Tính toán tọa độ 4 nút bấm
    margin = 12
    btn_gap = 10
    total_gap = btn_gap * 3 + margin * 2
    btn_w = (w - total_gap) // 4
    btn_h = bar_height - 20
    btn_y1 = bar_y1 + 10
    btn_y2 = btn_y1 + btn_h

    btn_defs = [
        {"action": "capture", "text": "CHUP 1 ANH", "color": (40, 160, 40), "key": "SPACE"},
        {"action": "burst", "text": "CHUP 5 ANH", "color": (30, 120, 220), "key": "C"},
        {"action": "switch", "text": "DOI CAMERA", "color": (180, 100, 30), "key": "S / TAB"},
        {"action": "quit", "text": "THOAT", "color": (50, 50, 180), "key": "Q / ESC"},
    ]

    buttons = []
    for i, btn in enumerate(btn_defs):
        bx1 = margin + i * (btn_w + btn_gap)
        bx2 = bx1 + btn_w
        # Nền nút
        cv2.rectangle(ui_frame, (bx1, btn_y1), (bx2, btn_y2), btn["color"], -1)
        # Viền nút
        cv2.rectangle(ui_frame, (bx1, btn_y1), (bx2, btn_y2), (255, 255, 255), 1)

        # Chữ trên nút
        label_1 = btn["text"]
        label_2 = f"({btn['key']})"

        # Căn chữ vào giữa nút
        t_size1 = cv2.getTextSize(label_1, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
        tx1 = bx1 + (btn_w - t_size1[0]) // 2
        ty1 = btn_y1 + 20
        cv2.putText(ui_frame, label_1, (tx1, ty1), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

        t_size2 = cv2.getTextSize(label_2, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0]
        tx2 = bx1 + (btn_w - t_size2[0]) // 2
        ty2 = btn_y1 + 36
        cv2.putText(ui_frame, label_2, (tx2, ty2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (220, 220, 220), 1)

        buttons.append({"rect": (bx1, btn_y1, bx2, btn_y2), "action": btn["action"]})

    return ui_frame, buttons


def main():
    global mouse_action

    parser = argparse.ArgumentParser(
        description="Chụp ảnh mẫu từ Camera / Webcam (Hỗ trợ nút bấm chuột trực tiếp)."
    )
    parser.add_argument(
        "--class",
        "-c",
        dest="class_name",
        type=str,
        default="cube_yellow",
        help="Tên class cần chụp (VD: cube_yellow, cube_blue, canh_tay_robot)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="dataset_raw",
        help="Thư mục gốc chứa dataset thô (mặc định: dataset_raw)",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=None,
        help="Chỉ số camera (0: camera máy, 1: camera USB ngoài,...)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Liệt kê danh sách các camera đang cắm rồi thoát.",
    )

    args = parser.parse_args()

    print("[*] Đang quét các camera đang kết nối...")
    found_cams = detect_available_cameras()

    if not found_cams:
        print("[!] Không tìm thấy bất kỳ camera nào kết nối với máy tính.")
        return

    print("\n" + "=" * 55)
    print(" DANH SÁCH CAMERA:")
    for idx, res in found_cams:
        desc = "Camera tích hợp (Laptop)" if idx == 0 else f"Camera cắm ngoài (USB #{idx})"
        print(f"  -> Camera [{idx}]: {desc} ({res})")
    print("=" * 55)

    if args.list:
        return

    # Tự động ưu tiên camera ngoài (USB) nếu có
    if args.camera is not None:
        current_cam_idx = args.camera
    else:
        cam_indices = [idx for idx, _ in found_cams]
        if len(cam_indices) > 1 and 1 in cam_indices:
            current_cam_idx = 1
            print(f"[*] Tự động ưu tiên chọn Camera ngoài USB [Camera 1]")
        else:
            current_cam_idx = cam_indices[0]
            print(f"[*] Mở Camera [{current_cam_idx}]")

    save_dir = Path(args.output) / args.class_name
    save_dir.mkdir(parents=True, exist_ok=True)

    existing_count = len(list(save_dir.glob("*.jpg"))) + len(list(save_dir.glob("*.png")))
    img_counter = existing_count

    cap = open_camera(current_cam_idx)
    if not cap.isOpened():
        print(f"[!] Không thể mở Camera [{current_cam_idx}], đổi sang Camera [0]...")
        current_cam_idx = 0
        cap = open_camera(0)

    # Thiết lập cửa sổ OpenCV
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    try:
        cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass

    mouse_param = {"buttons": []}
    cv2.setMouseCallback(WINDOW_NAME, on_mouse_click, mouse_param)

    print(f"\n[+] Đang chụp cho class: '{args.class_name}'")
    print(f"[+] Thư mục lưu: {save_dir.resolve()}")
    print("\n💡 BẠN CÓ THỂ:")
    print("  1. DÙNG CHUỘT: Click trực tiếp vào các nút [CHUP 1 ANH], [CHUP 5 ANH], [DOI CAMERA], [THOAT]")
    print("  2. DÙNG BÀN PHÍM: Bấm SPACE (chụp), C (chụp 5), S (đổi camera), Q (thoát)")
    print("  (Lưu ý: Nếu bấm phím, hãy nhấp chuột vào cửa sổ camera một lần để nhận phím)\n")

    burst_remaining = 0
    last_burst_time = 0
    flash_msg = ""
    flash_time = 0
    available_indices = [idx for idx, _ in found_cams]

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.05)
            continue

        # Xóa thông báo chụp sau 1.2 giây
        if flash_msg and (time.time() - flash_time > 1.2):
            flash_msg = ""

        # Vẽ giao diện + các nút bấm
        display_frame, buttons = draw_ui(frame, args.class_name, current_cam_idx, img_counter, flash_msg)
        mouse_param["buttons"] = buttons

        cv2.imshow(WINDOW_NAME, display_frame)

        # Lấy sự kiện phím
        key = cv2.waitKey(20) & 0xFF

        # Xác định hành động (từ Click chuột HOẶC từ Bàn phím)
        action = None
        if mouse_action is not None:
            action = mouse_action
            mouse_action = None  # Reset sự kiện chuột
        elif key == 32:  # Phím SPACE
            action = "capture"
        elif key in [ord("c"), ord("C")]:
            action = "burst"
        elif key in [ord("s"), ord("S"), 9]:  # Phím S hoặc TAB
            action = "switch"
        elif key in [ord("q"), ord("Q"), 27]:  # Phím Q hoặc ESC
            action = "quit"

        # --- XỬ LÝ HÀNH ĐỘNG ---
        if action == "capture":
            img_counter += 1
            filename = save_dir / f"img_{img_counter:04d}.jpg"
            cv2.imwrite(str(filename), frame)
            flash_msg = f"Da chup: {filename.name}!"
            flash_time = time.time()
            print(f"[Đã chụp] {filename.name} (Camera {current_cam_idx})")

        elif action == "burst":
            burst_remaining = 5
            flash_msg = "Dang chup lien tiep 5 anh..."
            flash_time = time.time()
            print("[Burst] Bắt đầu chụp liên tiếp 5 ảnh...")

        elif action == "switch":
            if len(available_indices) > 1:
                cur_pos = available_indices.index(current_cam_idx)
                next_pos = (cur_pos + 1) % len(available_indices)
                current_cam_idx = available_indices[next_pos]

                print(f"[*] Đang chuyển sang Camera [{current_cam_idx}]...")
                cap.release()
                time.sleep(0.2)
                cap = open_camera(current_cam_idx)
                flash_msg = f"Da doi sang Camera [{current_cam_idx}]"
                flash_time = time.time()
            else:
                flash_msg = "Chi co 1 camera ket noi!"
                flash_time = time.time()

        elif action == "quit":
            break

        # Xử lý burst liên tiếp
        if burst_remaining > 0 and (time.time() - last_burst_time > 0.35):
            img_counter += 1
            filename = save_dir / f"img_{img_counter:04d}.jpg"
            cv2.imwrite(str(filename), frame)
            print(f"  [Burst {6 - burst_remaining}/5] {filename.name}")
            burst_remaining -= 1
            last_burst_time = time.time()
            flash_msg = f"Burst {5 - burst_remaining}/5: {filename.name}"
            flash_time = time.time()

    cap.release()
    cv2.destroyAllWindows()
    print(f"\n[Hoàn tất] Tổng cộng có {img_counter} ảnh trong: '{save_dir}'.")


if __name__ == "__main__":
    main()
