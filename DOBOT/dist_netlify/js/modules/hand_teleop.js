// =========================================================================
// --- MODULE: MEDIAPIPE HAND TELEOPERATION & 1-EURO ADAPTIVE FILTER ---
// =========================================================================


        // =====================================================================
        // --- TAB 6: ĐIỀU KHIỂN CỬ CHỈ TAY MEDIAPIPE (HAND TELEOPERATION) ---
        // =====================================================================
        let handMediaPipeInstance = null;
        let handCameraStream = null;
        let handCameraRunning = false;
        let isHandMirrored = true;
        let isTeleopMasterActive = false;
        let handAnimationId = null;

        // Trạng thái Hiệu Chuẩn Mốc 0 & Độ Nhạy
        let handLastSeenLandmarks = null;
        let handLastSeenNorm = { x: 0.5, y: 0.5, scale: 0.18 };
        let handCalib = {
            calibrated: false,
            centerNormX: 0.50,
            centerNormY: 0.50,
            centerScale: 0.18
        };
        let handSensitivity = 1.0;
        let handCustomLimits = {
            xMin: 180.0,
            xMax: 300.0,
            yMin: -150.0,
            yMax: 150.0,
            zMin: -125.0,
            zMax: 80.0
        };

        // Cấu hình vùng khoảng cách bàn tay tới Camera (Depth Range: 20cm - 60cm)
        let handDistMinCm = 20.0;
        let handDistMaxCm = 60.0;
        let handCurrentDistCm = 35.0;

        function updateHandDistanceRange() {
            const minVal = parseFloat(document.getElementById('inp-hand-dist-min')?.value) || 20.0;
            const maxVal = parseFloat(document.getElementById('inp-hand-dist-max')?.value) || 60.0;
            handDistMinCm = Math.min(minVal, maxVal);
            handDistMaxCm = Math.max(minVal, maxVal);
            showToast(`📏 Vùng khoảng cách tay: ${handDistMinCm} cm ➔ ${handDistMaxCm} cm`);
        }

        // Thuật toán 1-Euro Filter Thích Nghi Vận Tốc (Velocity-Adaptive 1-Euro Filter)
        class OneEuroFilter {
            constructor(minCutoff = 0.8, beta = 0.05, dCutoff = 1.0) {
                this.minCutoff = minCutoff;
                this.beta = beta;
                this.dCutoff = dCutoff;
                this.xPrev = null;
                this.dxPrev = 0;
                this.tPrev = null;
            }
            filter(val, timestamp, dynamicBeta = null) {
                if (this.xPrev === null) {
                    this.xPrev = val;
                    this.tPrev = timestamp;
                    return val;
                }
                const dt = Math.max(0.001, (timestamp - this.tPrev) / 1000);
                this.tPrev = timestamp;
                const dx = (val - this.xPrev) / dt;
                const aD = this.alpha(dt, this.dCutoff);
                const dxHat = aD * dx + (1 - aD) * this.dxPrev;
                this.dxPrev = dxHat;
                const activeBeta = (dynamicBeta !== null) ? dynamicBeta : this.beta;
                const cutoff = this.minCutoff + activeBeta * Math.abs(dxHat);
                const a = this.alpha(dt, cutoff);
                const xHat = a * val + (1 - a) * this.xPrev;
                this.xPrev = xHat;
                return xHat;
            }
            alpha(dt, cutoff) {
                const tau = 1.0 / (2 * Math.PI * cutoff);
                return 1.0 / (1.0 + tau / dt);
            }
            reset() {
                this.xPrev = null;
                this.dxPrev = 0;
                this.tPrev = null;
            }
        }

        const euroX = new OneEuroFilter(0.8, 0.06);
        const euroY = new OneEuroFilter(0.8, 0.06);
        const euroZ = new OneEuroFilter(0.8, 0.06);

        // Chế độ Động Học & Tăng Tốc Thích Ứng Khi Vung Tay Nhanh
        let handTeleopMotionMode = 1; // 1: MOVJ_XYZ (Nội suy góc khớp - Khuyến nghị siêu nhanh & mượt), 2: MOVL_XYZ (Đường thẳng)
        let isAdaptiveFastEnabled = true;
        let prevRawDobotX = 230.0;
        let prevRawDobotY = 0.0;
        let prevRawDobotZ = 20.0;
        let lastHandVelTime = 0;
        let currentHandVelocityMmS = 0.0;

        // Trạng thái mượt & Rate limit
        let lastHandSendTime = 0;
        let handSmoothX = 230.0;
        let handSmoothY = 0.0;
        let handSmoothZ = 20.0;
        let handLastTargetX = 230.0;
        let handLastTargetY = 0.0;
        let handLastTargetZ = 20.0;
        let handCurrentSuction = false;
        let handFistDebounceCounter = 0;
        let handOpenDebounceCounter = 0;

        // Cấu hình thời gian giữ cử chỉ chuẩn: Đúng 2.0 giây (2000 ms) cho tất cả cử chỉ Hold
        const HOLD_DURATION_MS = 2000.0;
        let holdStartLike = 0, lastSeenLike = 0;
        let holdStartDislike = 0, lastSeenDislike = 0;
        let holdStartOk = 0, lastSeenOk = 0;
        let holdStartPick1 = 0, lastSeenPick1 = 0;
        let holdStartPick2 = 0, lastSeenPick2 = 0;
        let holdStartPick3 = 0, lastSeenPick3 = 0;
        let holdStartPick4 = 0, lastSeenPick4 = 0;
        let holdStartRock = 0, lastSeenRock = 0;

        let handRecoveryCooldown = 0;
        let isGestureRecovering = false;
        let isAutoTaskBusy = false;
        let autoTaskCooldownUntil = 0;
        let isAutoSortActive = false;
        let activeGestureText = "🖐️ TAY MỞ (HÚT: TẮT)";
        let activeGestureColor = "#38bdf8";
        let activeGesturePct = 0;

        // FPS tracking
        let handFpsFrameCount = 0;
        let handFpsLastTime = performance.now();
        let handCurrentFps = 0;

        function setHandMotionMode(mode) {
            handTeleopMotionMode = mode;
            const btnMovj = document.getElementById('btn-mode-movj');
            const btnMovl = document.getElementById('btn-mode-movl');
            if (btnMovj && btnMovl) {
                if (mode === 1) {
                    btnMovj.style.background = '#0284c7';
                    btnMovj.style.borderColor = '#38bdf8';
                    btnMovj.style.color = '#fff';
                    btnMovj.style.fontWeight = '700';
                    btnMovl.style.background = '#1e293b';
                    btnMovl.style.borderColor = '#475569';
                    btnMovl.style.color = '#94a3b8';
                    btnMovl.style.fontWeight = 'normal';
                } else {
                    btnMovl.style.background = '#0284c7';
                    btnMovl.style.borderColor = '#38bdf8';
                    btnMovl.style.color = '#fff';
                    btnMovl.style.fontWeight = '700';
                    btnMovj.style.background = '#1e293b';
                    btnMovj.style.borderColor = '#475569';
                    btnMovj.style.color = '#94a3b8';
                    btnMovj.style.fontWeight = 'normal';
                }
            }
            const metricMode = document.getElementById('teleop-metric-mode');
            if (metricMode) {
                metricMode.innerText = mode === 1 ? "⚡ MOVJ (Khớp)" : "📐 MOVL (Thẳng)";
            }
            showToast(mode === 1 ? "⚡ Đã chọn MOVJ: Chuyển động góc khớp siêu nhanh & mượt!" : "📐 Đã chọn MOVL: Chuyển động đường thẳng tuyệt đối.");
        }

        function toggleAdaptiveFast(enabled) {
            isAdaptiveFastEnabled = !!enabled;
            showToast(isAdaptiveFastEnabled ? "🚀 Đã bật Tăng Tốc Thích Ứng khi vung tay nhanh!" : "⚖️ Đã tắt Tăng Tốc Thích Ứng.");
        }

        function updateHandSettingsUI() {
            const hz = document.getElementById('slider-hand-hz')?.value || 20;
            const ema = document.getElementById('slider-hand-ema')?.value || 0.25;
            const deadband = document.getElementById('slider-hand-deadband')?.value || 1.5;
            const fistThresh = document.getElementById('slider-hand-fist-thresh')?.value || 0.65;

            const lblHz = document.getElementById('val-hand-hz');
            const lblEma = document.getElementById('val-hand-ema');
            const lblDeadband = document.getElementById('val-hand-deadband');
            const lblFist = document.getElementById('val-hand-fist-thresh');

            if (lblHz) lblHz.innerText = hz + ' Hz';
            if (lblEma) lblEma.innerText = parseFloat(ema).toFixed(2);
            if (lblDeadband) lblDeadband.innerText = parseFloat(deadband).toFixed(1) + ' mm';
            if (lblFist) lblFist.innerText = Math.round(fistThresh * 100) + '%';

            // Cập nhật tham số 1-Euro Filter từ slider
            const minCut = Math.max(0.1, parseFloat(ema) * 2.5);
            euroX.minCutoff = minCut;
            euroY.minCutoff = minCut;
            euroZ.minCutoff = minCut;
        }

        function updateCustomLimits() {
            const xmin = parseFloat(document.getElementById('inp-lim-xmin')?.value) || 180;
            const xmax = parseFloat(document.getElementById('inp-lim-xmax')?.value) || 300;
            const ymin = parseFloat(document.getElementById('inp-lim-ymin')?.value) || -150;
            const ymax = parseFloat(document.getElementById('inp-lim-ymax')?.value) || 150;
            const zmin = parseFloat(document.getElementById('inp-lim-zmin')?.value) || -125;
            const zmax = parseFloat(document.getElementById('inp-lim-zmax')?.value) || 80;

            handCustomLimits.xMin = Math.min(xmin, xmax);
            handCustomLimits.xMax = Math.max(xmin, xmax);
            handCustomLimits.yMin = Math.min(ymin, ymax);
            handCustomLimits.yMax = Math.max(ymin, ymax);
            handCustomLimits.zMin = Math.min(zmin, zmax);
            handCustomLimits.zMax = Math.max(zmin, zmax);
        }

        function syncZPickFromDropTargets() {
            let pickZ = -122.2;
            if (typeof dropTargetsConfig !== 'undefined' && dropTargetsConfig.pick_z !== undefined) {
                pickZ = parseFloat(dropTargetsConfig.pick_z);
            }
            const inpZMin = document.getElementById('inp-lim-zmin');
            if (inpZMin) {
                inpZMin.value = pickZ.toFixed(1);
                updateCustomLimits();
            }
            showToast(`📍 Đã đồng bộ Z_min = ${pickZ.toFixed(1)} mm từ cấu hình khay gắp thực tế!`);
        }

        function setHandSensitivity(s) {
            handSensitivity = s;
            const btnSlow = document.getElementById('btn-sens-slow');
            const btnNorm = document.getElementById('btn-sens-norm');
            const btnFast = document.getElementById('btn-sens-fast');

            [btnSlow, btnNorm, btnFast].forEach(b => {
                if (b) {
                    b.style.background = '#1e293b';
                    b.style.borderColor = '#475569';
                    b.style.color = '#94a3b8';
                    b.style.fontWeight = 'normal';
                }
            });

            if (s === 0.5 && btnSlow) {
                btnSlow.style.background = '#0284c7';
                btnSlow.style.borderColor = '#38bdf8';
                btnSlow.style.color = '#fff';
                btnSlow.style.fontWeight = '700';
                showToast("🎯 Đã chuyển sang chế độ 0.5x (Siêu Tinh Chỉnh cho phôi nhỏ)");
            } else if (s === 1.5 && btnFast) {
                btnFast.style.background = '#0284c7';
                btnFast.style.borderColor = '#38bdf8';
                btnFast.style.color = '#fff';
                btnFast.style.fontWeight = '700';
                showToast("⚡ Đã chuyển sang chế độ 1.5x (Biên độ vung tay rộng)");
            } else if (btnNorm) {
                btnNorm.style.background = '#0284c7';
                btnNorm.style.borderColor = '#38bdf8';
                btnNorm.style.color = '#fff';
                btnNorm.style.fontWeight = '700';
                showToast("⚖️ Đã chuyển về chế độ 1.0x (Tiêu Chuẩn)");
            }
        }

        function calibrateHandNeutral() {
            if (!handLastSeenLandmarks) {
                showToast("⚠️ Chưa phát hiện bàn tay! Hãy giơ tay trước camera trước khi bấm lấy mốc.");
                return;
            }
            handCalib.calibrated = true;
            handCalib.centerNormX = handLastSeenNorm.x;
            handCalib.centerNormY = handLastSeenNorm.y;
            handCalib.centerScale = handLastSeenNorm.scale;

            euroX.reset();
            euroY.reset();
            euroZ.reset();

            const badge = document.getElementById('hand-calib-status-badge');
            if (badge) {
                badge.style.background = "rgba(16, 185, 129, 0.25)";
                badge.style.color = "#34d399";
                badge.style.borderColor = "#10b981";
                badge.innerText = `Mốc 0: X=${(handCalib.centerNormX).toFixed(2)}, Y=${(handCalib.centerNormY).toFixed(2)}`;
            }

            showToast("🎯 ĐÃ HIỆU CHUẨN TÂM MỐC 0! Mọi chuyển động nay sẽ tính từ tư thế thoải mái này của bạn.");
        }

        function resetHandNeutral() {
            handCalib.calibrated = false;
            handCalib.centerNormX = 0.50;
            handCalib.centerNormY = 0.50;
            handCalib.centerScale = 0.18;

            euroX.reset();
            euroY.reset();
            euroZ.reset();

            const badge = document.getElementById('hand-calib-status-badge');
            if (badge) {
                badge.style.background = "rgba(14, 165, 233, 0.2)";
                badge.style.color = "#38bdf8";
                badge.style.borderColor = "rgba(56, 189, 248, 0.4)";
                badge.innerText = "Mốc: Mặc định";
            }
            showToast("🔄 Đã đặt lại tâm mốc 0 về giữa khung hình camera.");
        }

        async function initHandTeleopTab() {
            updateHandSettingsUI();
            updateCustomLimits();
            updateHandRobotStatusBadge();
            await populateHandCameraDevices();
        }

        function updateHandRobotStatusBadge() {
            const badge = document.getElementById('hand-robot-badge');
            if (badge) {
                if (isRobotConnected || isRobotHardwareConnected) {
                    badge.className = "sys-badge live";
                    badge.innerText = "DOBOT: ĐÃ KẾT NỐI ●";
                } else {
                    badge.className = "sys-badge offline";
                    badge.innerText = "DOBOT: CHƯA KẾT NỐI ○";
                }
            }
        }

        async function populateHandCameraDevices() {
            const selectEl = document.getElementById('hand-cam-select');
            if (!selectEl) return;
            try {
                if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
                    selectEl.innerHTML = '<option value="">-- Trình duyệt không hỗ trợ Camera API --</option>';
                    return;
                }
                const devices = await navigator.mediaDevices.enumerateDevices();
                const videoDevices = devices.filter(d => d.kind === 'videoinput');
                if (videoDevices.length === 0) {
                    selectEl.innerHTML = '<option value="">-- Không tìm thấy camera nào --</option>';
                    return;
                }
                const currentVal = selectEl.value;
                selectEl.innerHTML = '';
                videoDevices.forEach((dev, idx) => {
                    const opt = document.createElement('option');
                    opt.value = dev.deviceId;
                    opt.text = dev.label || `Camera ${idx + 1}`;
                    selectEl.appendChild(opt);
                });
                if (currentVal && Array.from(selectEl.options).some(o => o.value === currentVal)) {
                    selectEl.value = currentVal;
                }
            } catch (err) {
                console.warn("Lỗi dò tìm camera:", err);
            }
        }

        function toggleHandMirror() {
            isHandMirrored = !isHandMirrored;
            showToast(isHandMirrored ? "🔄 Đã bật chế độ lật gương (Mirror)" : "🔄 Đã tắt chế độ lật gương");
        }

        function toggleTeleopMaster(forceState = null) {
            if (forceState !== null) {
                if (isTeleopMasterActive === !!forceState) return;
                isTeleopMasterActive = !!forceState;
            } else {
                isTeleopMasterActive = !isTeleopMasterActive;
            }
            const btn = document.getElementById('btn-teleop-master');
            const txt = document.getElementById('teleop-master-text');
            const statusBadge = document.getElementById('hand-status-badge');

            if (isTeleopMasterActive) {
                if (btn) btn.className = "btn-teleop-master on";
                if (txt) txt.innerText = "🟢 ĐANG PHÁT LỆNH ĐIỀU KHIỂN (CLICK ĐỂ TẮT)";
                if (statusBadge) {
                    statusBadge.className = "sys-badge live";
                    statusBadge.innerText = "🟢 TELEOP BẬT";
                }
                showToast("🚀 ĐÃ KÍCH HOẠT ĐIỀU KHIỂN DOBOT! Robot sẽ di chuyển bám sát tay bạn.");
            } else {
                if (btn) btn.className = "btn-teleop-master off";
                if (txt) txt.innerText = "KÍCH HOẠT PHÁT LỆNH ĐẾN DOBOT (ĐANG TẮT)";
                if (statusBadge) {
                    statusBadge.className = "sys-badge offline";
                    statusBadge.innerText = "🔴 TELEOP TẮT";
                }
                sendAction('suction', false);
                handCurrentSuction = false;
                const metricSuction = document.getElementById('teleop-metric-suction');
                if (metricSuction) {
                    metricSuction.innerText = "OFF (ĐÃ TẮT)";
                    metricSuction.style.color = "#94a3b8";
                }
                showToast("⏹️ Đã tắt phát lệnh điều khiển Dobot. Chuyển về chế độ preview.");
            }
        }

        async function triggerPickColor(color) {
            if (isAutoTaskBusy || performance.now() < autoTaskCooldownUntil) return;
            isAutoTaskBusy = true;
            autoTaskCooldownUntil = performance.now() + 8000;
            
            const colorNames = {
                'cube_red': 'ĐỎ',
                'cube_green': 'XANH LÁ',
                'cube_blue': 'XANH DƯƠNG',
                'cube_yellow': 'VÀNG'
            };
            const nameVN = colorNames[color] || color;
            showToast(`🎯 CỬ CHỈ: ĐANG TÌM & GẮP KHỐI ${nameVN}...`);

            try {
                const res = await fetch('/api/vision/pick_color', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ color: color })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(`🚀 ${data.message || `Đang gắp khối ${nameVN}`}!`);
                } else {
                    showToast(`⚠️ ${data.error || `Không thể gắp khối ${nameVN}`}`);
                    isAutoTaskBusy = false;
                }
            } catch (err) {
                showToast(`❌ Lỗi kết nối Vision: ${err.message}`);
                isAutoTaskBusy = false;
            }
        }

        async function triggerToggleAutoSort() {
            if (performance.now() < autoTaskCooldownUntil) return;
            autoTaskCooldownUntil = performance.now() + 3000;

            isAutoSortActive = !isAutoSortActive;
            showToast(isAutoSortActive ? "🤖 CỬ CHỈ 🤟: ĐÃ BẬT TỰ ĐỘNG PHÂN LOẠI (AUTO SORT)!" : "⏹️ CỬ CHỈ 🤟: ĐÃ TẮT TỰ ĐỘNG PHÂN LOẠI.");
            try {
                await fetch('/api/vision/hand_auto_sort', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enable: isAutoSortActive })
                });
            } catch(err) {
                showToast(`❌ Lỗi Auto Sort: ${err.message}`);
            }
        }

        // Định kỳ kiểm tra đồng bộ cờ bận gắp thả & trạng thái Auto Sort từ hệ thống
        async function checkAutoTaskBusy() {
            try {
                const res = await fetch('/api/vision/hand_status');
                const data = await res.json();
                if (data) {
                    if (data.auto_sort_enabled !== undefined) {
                        isAutoSortActive = Boolean(data.auto_sort_enabled);
                    }
                    const isPicking = Boolean(data.is_picking);
                    if (isPicking) {
                        isAutoTaskBusy = true;
                    } else if (isAutoTaskBusy && performance.now() > autoTaskCooldownUntil) {
                        isAutoTaskBusy = false;
                    }
                }
            } catch(e) {}
        }
        setInterval(checkAutoTaskBusy, 1000);

        async function toggleHandCamera() {
            if (handCameraRunning) {
                stopHandCamera();
            } else {
                await startHandCamera();
            }
        }

        async function startHandCamera() {
            const btn = document.getElementById('btn-hand-cam-toggle');
            const videoEl = document.getElementById('hand-raw-video');
            const selectEl = document.getElementById('hand-cam-select');
            const resSelect = document.getElementById('hand-cam-res-select');
            const placeholder = document.getElementById('hand-cam-placeholder');

            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                showToast("❌ Trình duyệt không hỗ trợ truy cập Webcam!");
                return;
            }

            try {
                if (btn) {
                    btn.innerText = "⏳ Đang mở...";
                    btn.disabled = true;
                }

                const resMode = resSelect ? resSelect.value : '720p';
                let idealW = 1280;
                let idealH = 720;
                if (resMode === '1080p') {
                    idealW = 1920;
                    idealH = 1080;
                } else if (resMode === '480p') {
                    idealW = 640;
                    idealH = 480;
                }

                const deviceId = selectEl ? selectEl.value : null;
                const videoConstraints = {
                    width: { ideal: idealW },
                    height: { ideal: idealH },
                    frameRate: { ideal: 30, min: 15 }
                };
                if (deviceId) {
                    videoConstraints.deviceId = { exact: deviceId };
                }

                handCameraStream = await navigator.mediaDevices.getUserMedia({
                    video: videoConstraints,
                    audio: false
                });
                videoEl.srcObject = handCameraStream;
                await videoEl.play();

                // Đồng bộ độ phân giải thật của webcam vào canvas
                const canvas = document.getElementById('hand-teleop-canvas');
                if (canvas && videoEl.videoWidth && videoEl.videoHeight) {
                    canvas.width = videoEl.videoWidth;
                    canvas.height = videoEl.videoHeight;
                    console.log(`[HandCam] Camera đã kích hoạt ở độ phân giải: ${videoEl.videoWidth}x${videoEl.videoHeight}`);
                }

                if (placeholder) placeholder.style.display = 'none';

                if (!handMediaPipeInstance) {
                    initMediaPipeHands();
                }

                handCameraRunning = true;
                if (btn) {
                    btn.innerText = "⏹️ Tắt Camera";
                    btn.style.background = "#e11d48";
                    btn.style.borderColor = "#f43f5e";
                    btn.disabled = false;
                }

                showToast(`📷 Camera đã bật (${videoEl.videoWidth || idealW}x${videoEl.videoHeight || idealH} HD Sắc Nét)!`);
                runHandProcessLoop();
            } catch (err) {
                console.error("Lỗi mở camera:", err);
                showToast("❌ Không thể mở camera: " + (err.message || err.name));
                if (btn) {
                    btn.innerText = "▶️ Bật Camera";
                    btn.disabled = false;
                }
            }
        }

        function stopHandCamera() {
            handCameraRunning = false;
            if (handAnimationId) {
                cancelAnimationFrame(handAnimationId);
                handAnimationId = null;
            }
            if (handCameraStream) {
                handCameraStream.getTracks().forEach(t => t.stop());
                handCameraStream = null;
            }
            const videoEl = document.getElementById('hand-raw-video');
            if (videoEl) videoEl.srcObject = null;

            const btn = document.getElementById('btn-hand-cam-toggle');
            if (btn) {
                btn.innerText = "▶️ Bật Camera";
                btn.style.background = "#0284c7";
                btn.style.borderColor = "#38bdf8";
            }

            const placeholder = document.getElementById('hand-cam-placeholder');
            if (placeholder) placeholder.style.display = 'block';

            const canvas = document.getElementById('hand-teleop-canvas');
            if (canvas) {
                const ctx = canvas.getContext('2d');
                ctx.clearRect(0, 0, canvas.width, canvas.height);
            }

            const trackBadge = document.getElementById('hand-tracking-badge');
            if (trackBadge) {
                trackBadge.className = "hand-badge tracking-off";
                trackBadge.innerText = "○ CHƯA THẤY TAY";
            }

            if (isTeleopMasterActive) {
                toggleTeleopMaster();
            }
            showToast("⏹️ Đã tắt camera.");
        }

        function initMediaPipeHands() {
            if (typeof Hands === 'undefined') {
                console.warn("MediaPipe Hands JS chưa được tải!");
                showToast("⚠️ Thư viện MediaPipe Hands đang tải từ CDN, vui lòng đợi vài giây...");
                return;
            }

            handMediaPipeInstance = new Hands({
                locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`
            });

            handMediaPipeInstance.setOptions({
                maxNumHands: 1,
                modelComplexity: 1,
                minDetectionConfidence: 0.65,
                minTrackingConfidence: 0.65
            });

            handMediaPipeInstance.onResults(onHandResults);
            console.log("[MediaPipe] Hands model initialized.");
        }

        async function runHandProcessLoop() {
            if (!handCameraRunning) return;
            const videoEl = document.getElementById('hand-raw-video');

            if (videoEl && videoEl.readyState >= 2 && handMediaPipeInstance) {
                try {
                    await handMediaPipeInstance.send({ image: videoEl });
                } catch (e) {
                    console.warn("Lỗi gửi frame MediaPipe:", e);
                }
            }

            if (handCameraRunning) {
                handAnimationId = requestAnimationFrame(runHandProcessLoop);
            }
        }

        // Xử lý kết quả trả về từ MediaPipe Hands với độ chính xác cao & 1-Euro Filter
        function onHandResults(results) {
            const canvas = document.getElementById('hand-teleop-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');

            // Đồng bộ kích thước canvas với ảnh đầu vào để tránh mờ
            if (results.image && (canvas.width !== results.image.width || canvas.height !== results.image.height)) {
                canvas.width = results.image.width;
                canvas.height = results.image.height;
            }
            const w = canvas.width;
            const h = canvas.height;
            ctx.imageSmoothingEnabled = true;
            ctx.imageSmoothingQuality = 'high';

            // Đo FPS
            handFpsFrameCount++;
            const now = performance.now();
            if (now - handFpsLastTime >= 1000) {
                handCurrentFps = Math.round((handFpsFrameCount * 1000) / (now - handFpsLastTime));
                handFpsFrameCount = 0;
                handFpsLastTime = now;
                const fpsBadge = document.getElementById('hand-fps-badge');
                if (fpsBadge) fpsBadge.innerText = `FPS: ${handCurrentFps}`;
            }

            ctx.save();
            ctx.clearRect(0, 0, w, h);

            // Vẽ video feed nền (hỗ trợ lật gương)
            if (isHandMirrored) {
                ctx.translate(w, 0);
                ctx.scale(-1, 1);
            }
            if (results.image) {
                ctx.drawImage(results.image, 0, 0, w, h);
            }
            ctx.restore();

            const trackBadge = document.getElementById('hand-tracking-badge');
            const gestureBadge = document.getElementById('hand-gesture-badge');
            const posHud = document.getElementById('hand-pos-hud');

            // Nếu không phát hiện thấy bàn tay
            if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
                handLastSeenLandmarks = null;
                if (trackBadge) {
                    trackBadge.className = "hand-badge tracking-off";
                    trackBadge.innerText = "○ CHƯA THẤY TAY";
                }
                return;
            }

            // Có phát hiện bàn tay
            if (trackBadge) {
                trackBadge.className = "hand-badge tracking-on";
                trackBadge.innerText = "● ĐANG THEO DÕI TAY";
            }

            const landmarks = results.multiHandLandmarks[0];
            handLastSeenLandmarks = landmarks;

            // 1. Phân tích cử chỉ bàn tay chi tiết (Multi-Gesture Analysis)
            const wrist = landmarks[0];
            const middleMCP = landmarks[9];
            const palmBaseDist = Math.hypot(middleMCP.x - wrist.x, middleMCP.y - wrist.y);

            // Đo độ duỗi/gập từng ngón tay
            const dTip8 = Math.hypot(landmarks[8].x - wrist.x, landmarks[8].y - wrist.y);
            const dPip6 = Math.hypot(landmarks[6].x - wrist.x, landmarks[6].y - wrist.y);
            const dTip12 = Math.hypot(landmarks[12].x - wrist.x, landmarks[12].y - wrist.y);
            const dPip10 = Math.hypot(landmarks[10].x - wrist.x, landmarks[10].y - wrist.y);
            const dTip16 = Math.hypot(landmarks[16].x - wrist.x, landmarks[16].y - wrist.y);
            const dPip14 = Math.hypot(landmarks[14].x - wrist.x, landmarks[14].y - wrist.y);
            const dTip20 = Math.hypot(landmarks[20].x - wrist.x, landmarks[20].y - wrist.y);
            const dPip18 = Math.hypot(landmarks[18].x - wrist.x, landmarks[18].y - wrist.y);

            const isIndexExt = dTip8 > dPip6 * 1.15;
            const isIndexFold = dTip8 < dPip6 * 1.08;
            const isMiddleExt = dTip12 > dPip10 * 1.15;
            const isMiddleFold = dTip12 < dPip10 * 1.08;
            const isRingExt = dTip16 > dPip14 * 1.15;
            const isRingFold = dTip16 < dPip14 * 1.08;
            const isPinkyExt = dTip20 > dPip18 * 1.15;
            const isPinkyFold = dTip20 < dPip18 * 1.08;

            const thumbTip = landmarks[4];
            const thumbIP = landmarks[3];
            const thumbMCP = landmarks[2];
            const indexMCP = landmarks[5];

            // Tâm lòng bàn tay (Palm Center)
            const palmCenterX = (landmarks[0].x + landmarks[5].x + landmarks[17].x) / 3;
            const palmCenterY = (landmarks[0].y + landmarks[5].y + landmarks[17].y) / 3;
            const distThumbToPalm = Math.hypot(thumbTip.x - palmCenterX, thumbTip.y - palmCenterY);
            const distThumbWrist = Math.hypot(thumbTip.x - wrist.x, thumbTip.y - wrist.y);

            // Ngón cái duỗi xòe ra ngoài (Thumb Extended - khi bàn tay mở 5 ngón hoặc like/dislike/rock)
            const isThumbExt = distThumbWrist > palmBaseDist * 0.85 && distThumbToPalm > palmBaseDist * 0.52;

            // Ngón cái gập ép vào trong lòng bàn tay (Thumb Folded / Tucked - khi giơ 4 ngón hoặc nắm tay)
            const isThumbFold = distThumbToPalm < palmBaseDist * 0.40 || distThumbWrist < palmBaseDist * 0.65;

            // Đếm số ngón duỗi và gập
            let extendedFingersCount = 0;
            if (isIndexExt) extendedFingersCount++;
            if (isMiddleExt) extendedFingersCount++;
            if (isRingExt) extendedFingersCount++;
            if (isPinkyExt) extendedFingersCount++;
            if (isThumbExt) extendedFingersCount++;

            let foldedFingersCount = 0;
            if (isIndexFold) foldedFingersCount++;
            if (isMiddleFold) foldedFingersCount++;
            if (isRingFold) foldedFingersCount++;
            if (isPinkyFold) foldedFingersCount++;
            if (isThumbFold) foldedFingersCount++;

            // Kiểm tra các ngón dài
            const isAnyLongFingerExt = isIndexExt || isMiddleExt || isRingExt || isPinkyExt;
            const isAllLongFingersFold = isIndexFold && isMiddleFold && isRingFold && isPinkyFold;

            // Khoảng cách chụm ngón cái và ngón trỏ (Pinch distance)
            const distThumbIndex = Math.hypot(thumbTip.x - landmarks[8].x, thumbTip.y - landmarks[8].y);
            const isPinchOk = distThumbIndex < palmBaseDist * 0.42;

            // Khoảng cách thân ngón cái (từ đốt MCP 2 tới đầu ngón 4)
            const lenThumb = Math.hypot(thumbTip.x - thumbMCP.x, thumbTip.y - thumbMCP.y);

            // A. NHÓM CỬ CHỈ HOẠT ĐỘNG BẤT CỨ LÚC NÀO (ANYTIME GESTURES)
            // 1. Like 👍 (Thumbs Up: 4 ngón dài gập, ngón cái giơ THẲNG LÊN TRỜI, đầu ngón cái cao vượt hẳn khớp ngón trỏ)
            // Trong nắm tay thông thường, ngón cái gập quặp ngang nên thumbTip.y KHÔNG BAO GIỜ cao hơn indexMCP.y - 0.05
            const isLikeDetected = isAllLongFingersFold && (thumbTip.y < indexMCP.y - 0.05) && (thumbTip.y < thumbIP.y - 0.04) && (thumbTip.y < thumbMCP.y - 0.06) && (lenThumb > palmBaseDist * 0.45);

            // 2. Dislike 👎 (Thumbs Down: 4 ngón dài gập, ngón cái chúc THẲNG XUỐNG ĐẤT, đầu ngón cái thấp hơn hẳn cổ tay)
            const isDislikeDetected = isAllLongFingersFold && (thumbTip.y > wrist.y + 0.02) && (thumbTip.y > thumbMCP.y + 0.06) && (lenThumb > palmBaseDist * 0.45);

            // 3. OK Sign 👌 (Gỡ lỗi: Ngón cái chạm trỏ tạo chữ O, 3 ngón kia duỗi)
            const isOkDetected = isPinchOk && isMiddleExt && isRingExt && isPinkyExt;

            // B. NHÓM CỬ CHỈ TÁC VỤ KHI ĐANG BẬT PHÁT LỆNH (ACTION GESTURES)
            // 4. 1 ngón ☝️ (Gắp Đỏ: chỉ ngón trỏ duỗi, các ngón khác gập)
            const isPick1Detected = isTeleopMasterActive && isIndexExt && isMiddleFold && isRingFold && isPinkyFold && !isMiddleExt && !isRingExt && !isPinkyExt && !isPinchOk && !isLikeDetected && !isDislikeDetected;

            // 5. 2 ngón ✌️ (Gắp Xanh Lá: ngón trỏ & giữa duỗi, áp út & út gập)
            const isPick2Detected = isTeleopMasterActive && isIndexExt && isMiddleExt && isRingFold && isPinkyFold && !isRingExt && !isPinkyExt && !isPinchOk && !isOkDetected;

            // 6. 3 ngón 3️⃣ (Gắp Xanh Dương: ngón trỏ & giữa & áp út duỗi, út gập)
            const isPick3Detected = isTeleopMasterActive && isIndexExt && isMiddleExt && isRingExt && isPinkyFold && !isPinkyExt && !isPinchOk;

            // 7. 4 ngón 4️⃣ (Gắp Vàng: 4 ngón duỗi, ngón cái PHẢI GẬP ÉP VÀO LÒNG BÀN TAY)
            // Khi mở 5 ngón bình thường, isThumbExt=true nên isPick4Detected sẽ KHÔNG bao giờ bị kích hoạt nhầm!
            const isPick4Detected = isTeleopMasterActive && isIndexExt && isMiddleExt && isRingExt && isPinkyExt && isThumbFold && !isThumbExt && !isPinchOk;

            // 8. Rock / Love 🤟 (Bật/Tắt Auto Sort: ngón cái + trỏ + út duỗi)
            const isRockDetected = isTeleopMasterActive && isThumbExt && isIndexExt && isPinkyExt && isMiddleFold && isRingFold && !isMiddleExt && !isRingExt && !isPinchOk;

            // ĐO THỜI GIAN GIỮ CỬ CHỈ (ĐÚNG 2.0 GIÂY = 2000 MS CHO TẤT CẢ CÁC LỆNH HOLD)
            activeGesturePct = 0;

            if (isLikeDetected) {
                if (!holdStartLike) holdStartLike = now;
                lastSeenLike = now;
                const elapsed = now - holdStartLike;
                activeGesturePct = Math.min(100, Math.round((elapsed / HOLD_DURATION_MS) * 100));
                activeGestureText = `👍 LIKE: BẬT PHÁT LỆNH (${activeGesturePct}%)`;
                activeGestureColor = "#38bdf8";
                if (elapsed >= HOLD_DURATION_MS) {
                    holdStartLike = 0;
                    toggleTeleopMaster(true);
                }
            } else {
                if (now - lastSeenLike > 180) holdStartLike = 0;
            }

            if (isDislikeDetected) {
                if (!holdStartDislike) holdStartDislike = now;
                lastSeenDislike = now;
                const elapsed = now - holdStartDislike;
                activeGesturePct = Math.min(100, Math.round((elapsed / HOLD_DURATION_MS) * 100));
                activeGestureText = `👎 DISLIKE: TẮT PHÁT LỆNH (${activeGesturePct}%)`;
                activeGestureColor = "#f87171";
                if (elapsed >= HOLD_DURATION_MS) {
                    holdStartDislike = 0;
                    toggleTeleopMaster(false);
                }
            } else {
                if (now - lastSeenDislike > 180) holdStartDislike = 0;
            }

            if (isOkDetected) {
                if (!holdStartOk) holdStartOk = now;
                lastSeenOk = now;
                const elapsed = now - holdStartOk;
                activeGesturePct = Math.min(100, Math.round((elapsed / HOLD_DURATION_MS) * 100));
                activeGestureText = `👌 OK: GIỮ ĐỂ GỠ LỖI (${activeGesturePct}%)`;
                activeGestureColor = "#34d399";
                if (elapsed >= HOLD_DURATION_MS && now > handRecoveryCooldown) {
                    handRecoveryCooldown = now + 4000;
                    holdStartOk = 0;
                    isGestureRecovering = true;
                    sendAction('recover_pose');
                    euroX.reset();
                    euroY.reset();
                    euroZ.reset();
                    showToast("🛡️ CỬ CHỈ 👌 OK: ĐÃ GỠ LỖI ĐÈN ĐỎ & ĐƯA DOBOT VỀ AN TOÀN!");
                    setTimeout(() => { isGestureRecovering = false; }, 3000);
                }
            } else {
                if (now - lastSeenOk > 180) holdStartOk = 0;
            }

            // NẾU ROBOT ĐANG BẬN GẮP HOẶC ĐANG CHẠY AUTO SORT:
            // VÔ HIỆU HÓA CÁC CỬ CHỈ GẮP (1..4) VÀ CỬ CHỈ BẬT HÚT NẮM/MỞ TAY.
            // CHỈ DUY TRÌ CÁC CỬ CHỈ ĐIỀU KHIỂN HỆ THỐNG: 👍 BẬT LỆNH, 👎 TẮT LỆNH, 👌 GỠ LỖI AN TOÀN, VÀ 🤟 ĐỂ TẮT AUTO SORT!
            const isTaskLocked = isAutoTaskBusy || isAutoSortActive;

            if (isTaskLocked) {
                holdStartPick1 = 0;
                holdStartPick2 = 0;
                holdStartPick3 = 0;
                holdStartPick4 = 0;
            } else {
                if (isPick1Detected) {
                    if (!holdStartPick1) holdStartPick1 = now;
                    lastSeenPick1 = now;
                    const elapsed = now - holdStartPick1;
                    activeGesturePct = Math.min(100, Math.round((elapsed / HOLD_DURATION_MS) * 100));
                    activeGestureText = `☝️ 1 NGÓN: GẮP ĐỎ (${activeGesturePct}%)`;
                    activeGestureColor = "#ef4444";
                    if (elapsed >= HOLD_DURATION_MS) {
                        holdStartPick1 = 0;
                        triggerPickColor('cube_red');
                    }
                } else {
                    if (now - lastSeenPick1 > 180) holdStartPick1 = 0;
                }

                if (isPick2Detected) {
                    if (!holdStartPick2) holdStartPick2 = now;
                    lastSeenPick2 = now;
                    const elapsed = now - holdStartPick2;
                    activeGesturePct = Math.min(100, Math.round((elapsed / HOLD_DURATION_MS) * 100));
                    activeGestureText = `✌️ 2 NGÓN: GẮP XANH LÁ (${activeGesturePct}%)`;
                    activeGestureColor = "#22c55e";
                    if (elapsed >= HOLD_DURATION_MS) {
                        holdStartPick2 = 0;
                        triggerPickColor('cube_green');
                    }
                } else {
                    if (now - lastSeenPick2 > 180) holdStartPick2 = 0;
                }

                if (isPick3Detected) {
                    if (!holdStartPick3) holdStartPick3 = now;
                    lastSeenPick3 = now;
                    const elapsed = now - holdStartPick3;
                    activeGesturePct = Math.min(100, Math.round((elapsed / HOLD_DURATION_MS) * 100));
                    activeGestureText = `3️⃣ 3 NGÓN: GẮP XANH DƯƠNG (${activeGesturePct}%)`;
                    activeGestureColor = "#3b82f6";
                    if (elapsed >= HOLD_DURATION_MS) {
                        holdStartPick3 = 0;
                        triggerPickColor('cube_blue');
                    }
                } else {
                    if (now - lastSeenPick3 > 180) holdStartPick3 = 0;
                }

                if (isPick4Detected) {
                    if (!holdStartPick4) holdStartPick4 = now;
                    lastSeenPick4 = now;
                    const elapsed = now - holdStartPick4;
                    activeGesturePct = Math.min(100, Math.round((elapsed / HOLD_DURATION_MS) * 100));
                    activeGestureText = `4️⃣ 4 NGÓN: GẮP VÀNG (${activeGesturePct}%)`;
                    activeGestureColor = "#eab308";
                    if (elapsed >= HOLD_DURATION_MS) {
                        holdStartPick4 = 0;
                        triggerPickColor('cube_yellow');
                    }
                } else {
                    if (now - lastSeenPick4 > 180) holdStartPick4 = 0;
                }
            }

            if (isRockDetected) {
                if (!holdStartRock) holdStartRock = now;
                lastSeenRock = now;
                const elapsed = now - holdStartRock;
                activeGesturePct = Math.min(100, Math.round((elapsed / HOLD_DURATION_MS) * 100));
                activeGestureText = isAutoSortActive ? `🤟 ROCK: DỪNG AUTO SORT (${activeGesturePct}%)` : `🤟 ROCK: BẬT AUTO SORT (${activeGesturePct}%)`;
                activeGestureColor = "#a855f7";
                if (elapsed >= HOLD_DURATION_MS) {
                    holdStartRock = 0;
                    triggerToggleAutoSort();
                }
            } else {
                if (now - lastSeenRock > 180) holdStartRock = 0;
            }

            // C. CỬ CHỈ LIÊN TỤC: NẮM TAY (BẬT HÚT) & MỞ TAY (TẮT HÚT)
            const isAnySpecialHold = (holdStartLike > 0 || holdStartDislike > 0 || holdStartOk > 0 || 
                                      holdStartPick1 > 0 || holdStartPick2 > 0 || holdStartPick3 > 0 || 
                                      holdStartPick4 > 0 || holdStartRock > 0);

            // NẮM TAY (HÚT): 4 ngón dài đều gập, không có ngón dài nào duỗi, không phải giơ Like 👍 hay Dislike 👎
            // Khi người dùng nắm cả bàn tay lại, hệ thống nhận diện tức thì và bật giác hút!
            const isFistDetected = isAllLongFingersFold && !isAnyLongFingerExt && !isLikeDetected && !isDislikeDetected;

            // MỞ TAY (NHẢ): Khi có ít nhất 3 ngón duỗi và không phải nắm tay
            const isHandOpenDetected = extendedFingersCount >= 3 && !isAllLongFingersFold;

            if (!isAnySpecialHold && !isTaskLocked) {
                if (isFistDetected) {
                    handFistDebounceCounter++;
                    handOpenDebounceCounter = 0;
                } else if (isHandOpenDetected) {
                    handOpenDebounceCounter++;
                    handFistDebounceCounter = 0;
                }
            }

            let isSuctionActive = handCurrentSuction;
            if (!isAnySpecialHold && !isGestureRecovering && !isTaskLocked) {
                if (handFistDebounceCounter >= 2) {
                    isSuctionActive = true;
                } else if (handOpenDebounceCounter >= 2) {
                    isSuctionActive = false;
                }
            }

            // Cập nhật nhãn và màu sắc hiển thị
            if (isGestureRecovering) {
                activeGestureText = "🛡️ ĐANG GỠ LỖI & VỀ AN TOÀN...";
                activeGestureColor = "#34d399";
            } else if (isAutoSortActive && !holdStartRock && !holdStartDislike && !holdStartOk) {
                activeGestureText = "🤖 ĐANG CHẠY AUTO SORT (🤟 ĐỂ DỪNG)...";
                activeGestureColor = "#a855f7";
            } else if (isAutoTaskBusy && !holdStartDislike && !holdStartOk) {
                activeGestureText = "🦾 ROBOT ĐANG GẮP VẬT THỂ TỰ ĐỘNG...";
                activeGestureColor = "#f59e0b";
            } else if (!isAnySpecialHold) {
                if (isSuctionActive) {
                    activeGestureText = "✊ NẮM TAY (HÚT: BẬT)";
                    activeGestureColor = "#ef4444";
                } else {
                    activeGestureText = "🖐️ TAY MỞ (HÚT: TẮT)";
                    activeGestureColor = "#38bdf8";
                }
            }

            if (gestureBadge) {
                gestureBadge.innerText = activeGestureText;
                gestureBadge.style.color = activeGestureColor;
                gestureBadge.style.background = activeGesturePct > 0 ? "rgba(255, 255, 255, 0.12)" : "";
            }

            const metricGesture = document.getElementById('teleop-metric-gesture');
            if (metricGesture) {
                metricGesture.innerText = activeGestureText;
                metricGesture.style.color = activeGestureColor;
            }

            // 2. Tọa độ tâm bàn tay chuẩn hóa & Ước lượng khoảng cách tay (cm)
            let palmX = (landmarks[0].x + landmarks[5].x + landmarks[17].x) / 3;
            let palmY = (landmarks[0].y + landmarks[5].y + landmarks[17].y) / 3;
            let palmZ = landmarks[0].z || 0;

            let normX = isHandMirrored ? (1.0 - palmX) : palmX;
            let normY = palmY;

            // Ước lượng khoảng cách từ camera (cm): D = 5.8 / palmBaseDist (D ~ 20cm khi palmBaseDist ~ 0.29; D ~ 60cm khi palmBaseDist ~ 0.097)
            const rawEstimatedCm = 5.8 / Math.max(0.04, palmBaseDist);
            handCurrentDistCm = Math.round(Math.max(10, Math.min(100, rawEstimatedCm)));

            handLastSeenNorm = { x: normX, y: normY, scale: palmBaseDist, distCm: handCurrentDistCm };

            if (posHud) {
                posHud.innerText = `Tay: (${normX.toFixed(2)}, ${normY.toFixed(2)}) | Cách: ${handCurrentDistCm} cm`;
            }

            const distHud = document.getElementById('hand-dist-hud');
            if (distHud) {
                distHud.innerText = `Khoảng cách: ${handCurrentDistCm} cm (${handDistMinCm}-${handDistMaxCm}cm)`;
            }

            const lblDist = document.getElementById('lbl-live-hand-dist');
            if (lblDist) {
                lblDist.innerText = `${handCurrentDistCm} cm`;
                lblDist.style.color = (handCurrentDistCm >= handDistMinCm && handCurrentDistCm <= handDistMaxCm) ? '#38bdf8' : '#f59e0b';
            }

            // 3. ÁNH XẠ TOẠ ĐỘ DOBOT CÓ HIỆU CHUẨN MỐC 0 & ĐỘ NHẠY
            const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
            let rawDobotX, rawDobotY, rawDobotZ;

            const xSpan = handCustomLimits.xMax - handCustomLimits.xMin;
            const ySpan = handCustomLimits.yMax - handCustomLimits.yMin;
            const zSpan = handCustomLimits.zMax - handCustomLimits.zMin;
            const xMid = (handCustomLimits.xMin + handCustomLimits.xMax) / 2;
            const yMid = (handCustomLimits.yMin + handCustomLimits.yMax) / 2;
            const zMid = (handCustomLimits.zMin + handCustomLimits.zMax) / 2;

            if (handCalib.calibrated) {
                // Chế độ đã hiệu chuẩn mốc 0: Tính từ độ lệch so với tư thế tự nhiên của người dùng
                const deltaX = (normX - handCalib.centerNormX) * handSensitivity;
                const deltaY = (normY - handCalib.centerNormY) * handSensitivity;
                const deltaScale = (palmBaseDist - handCalib.centerScale) * handSensitivity;

                rawDobotY = yMid + deltaX * (ySpan * 1.5);
                rawDobotZ = zMid - deltaY * (zSpan * 1.6);
                rawDobotX = xMid + deltaScale * (xSpan * 5.5);
            } else {
                // Chế độ mặc định: Ánh xạ theo khoảng cách tay [handDistMinCm, handDistMaxCm] (mặc định 20cm - 60cm)
                const rangeNormX = clamp((normX - 0.15) / 0.70, 0, 1);
                const rangeNormY = clamp((normY - 0.15) / 0.70, 0, 1);

                const distSpan = Math.max(5.0, handDistMaxCm - handDistMinCm);
                const distClamped = Math.max(handDistMinCm, Math.min(handDistMaxCm, rawEstimatedCm));
                // 1.0 khi tay ở gần nhất (20cm) -> Dobot vươn ra xa (X_max)
                // 0.0 khi tay ở xa nhất (60cm) -> Dobot rút về gần (X_min)
                const distProgress = (handDistMaxCm - distClamped) / distSpan;

                rawDobotY = handCustomLimits.yMin + rangeNormX * ySpan;
                rawDobotZ = handCustomLimits.zMax - rangeNormY * zSpan;
                rawDobotX = handCustomLimits.xMin + distProgress * xSpan;
            }

            // 3.1. KẸP BÁN KÍNH AN TOÀN TRÁNH VÙNG LỖI KẸT KHỚP (RADIAL SAFETY BOUNDARY)
            const curRadius = Math.hypot(rawDobotX, rawDobotY);
            if (curRadius > 290.0) {
                const radScale = 290.0 / curRadius;
                rawDobotX *= radScale;
                rawDobotY *= radScale;
            } else if (curRadius < 185.0 && curRadius > 0.001) {
                const radScale = 185.0 / curRadius;
                rawDobotX *= radScale;
                rawDobotY *= radScale;
            }

            // 4. TÍNH VẬN TỐC TAY & BỘ LỌC 1-EURO FILTER THÍCH NGHI VẬN TỐC (VELOCITY-ADAPTIVE)
            const dtVel = (now - lastHandVelTime) / 1000.0;
            if (dtVel > 0.005 && lastHandVelTime > 0) {
                const instantDist = Math.hypot(rawDobotX - prevRawDobotX, rawDobotY - prevRawDobotY, rawDobotZ - prevRawDobotZ);
                const instantVel = instantDist / dtVel; // mm/s
                currentHandVelocityMmS = currentHandVelocityMmS * 0.7 + instantVel * 0.3; // EMA smoothing
            }
            prevRawDobotX = rawDobotX;
            prevRawDobotY = rawDobotY;
            prevRawDobotZ = rawDobotZ;
            lastHandVelTime = now;

            // Khi vung tay nhanh (> 120 mm/s), tự động đẩy beta lên cao (tới 0.38) để triệt tiêu độ trễ lọc
            let dynamicBeta = 0.06;
            let isFastMoving = false;
            if (isAdaptiveFastEnabled) {
                if (currentHandVelocityMmS > 120) {
                    isFastMoving = true;
                    const velFactor = Math.min(1.0, (currentHandVelocityMmS - 120) / 250);
                    dynamicBeta = 0.06 + velFactor * 0.32;
                }
            }

            const filteredX = euroX.filter(rawDobotX, now, dynamicBeta);
            const filteredY = euroY.filter(rawDobotY, now, dynamicBeta);
            const filteredZ = euroZ.filter(rawDobotZ, now, dynamicBeta);

            // Kẹp trong phạm vi tùy chỉnh
            const finalX = clamp(Math.round(filteredX * 10) / 10, handCustomLimits.xMin, handCustomLimits.xMax);
            const finalY = clamp(Math.round(filteredY * 10) / 10, handCustomLimits.yMin, handCustomLimits.yMax);
            const finalZ = clamp(Math.round(filteredZ * 10) / 10, handCustomLimits.zMin, handCustomLimits.zMax);

            // 5. Vẽ Skeleton, Mốc 0 và Thước đo HUD
            drawHandSkeleton(ctx, landmarks, w, h, isHandMirrored, isSuctionActive, finalX, finalY, finalZ, isFastMoving, currentHandVelocityMmS, activeGesturePct, activeGestureText, activeGestureColor, isGestureRecovering, handCurrentDistCm);

            // Cập nhật Metrics UI
            const metricTarget = document.getElementById('teleop-metric-target');
            if (metricTarget) {
                metricTarget.innerText = `X: ${finalX.toFixed(0)} | Y: ${finalY.toFixed(0)} | Z: ${finalZ.toFixed(0)}`;
            }

            const metricActual = document.getElementById('teleop-metric-actual');
            if (metricActual && lastKnownRobotPose) {
                metricActual.innerText = `X: ${lastKnownRobotPose.x.toFixed(0)} | Y: ${lastKnownRobotPose.y.toFixed(0)} | Z: ${lastKnownRobotPose.z.toFixed(0)}`;
            }

            const metricVel = document.getElementById('teleop-metric-vel');
            if (metricVel) {
                metricVel.innerText = `${Math.round(currentHandVelocityMmS)} mm/s ${isFastMoving ? '⚡ BOOST' : ''}`;
                metricVel.style.color = isFastMoving ? '#f59e0b' : '#38bdf8';
            }

            // 6. Phát lệnh điều khiển thời gian thực (Dừng phát khi đang giữ cử chỉ tác vụ hoặc robot đang bận)
            const targetHz = parseInt(document.getElementById('slider-hand-hz')?.value) || 20;
            const sendIntervalMs = 1000 / targetHz;

            if (isTeleopMasterActive && !isAnySpecialHold && !isGestureRecovering && !isAutoTaskBusy && !isAutoSortActive && (now - lastHandSendTime >= sendIntervalMs)) {
                lastHandSendTime = now;

                const baseDeadbandMm = parseFloat(document.getElementById('slider-hand-deadband')?.value) || 1.5;
                // Khi vung tay nhanh, hạ deadband xuống để nhạy ngay lập tức
                const effectiveDeadband = isFastMoving ? Math.min(baseDeadbandMm, 0.4) : baseDeadbandMm;
                const distChange = Math.hypot(finalX - handLastTargetX, finalY - handLastTargetY, finalZ - handLastTargetZ);

                if (distChange >= effectiveDeadband) {
                    handLastTargetX = finalX;
                    handLastTargetY = finalY;
                    handLastTargetZ = finalZ;

                    const zFlange = finalZ + toolOffset;
                    // Sử dụng action 'teleop_stream' chuyên dụng (clear backlog queue và tự boost vận tốc khi fast=true)
                    sendAction('teleop_stream', { 
                        x: finalX, 
                        y: finalY, 
                        z: zFlange, 
                        r: 0, 
                        mode: handTeleopMotionMode, 
                        fast: isFastMoving 
                    });
                }

                if (isSuctionActive !== handCurrentSuction) {
                    handCurrentSuction = isSuctionActive;
                    sendAction('suction', handCurrentSuction);

                    const metricSuction = document.getElementById('teleop-metric-suction');
                    if (metricSuction) {
                        metricSuction.innerText = handCurrentSuction ? "ON (ĐANG HÚT)" : "OFF (ĐÃ TẮT)";
                        metricSuction.style.color = handCurrentSuction ? "#f87171" : "#94a3b8";
                    }
                }
            }
        }

        // Vẽ Khung Xương Bàn Tay & HUD Thước Đo Trực Quan
        function drawHandSkeleton(ctx, landmarks, w, h, mirrored, isFist, curX, curY, curZ, isFast = false, velMmS = 0, gesturePct = 0, gestureText = "", gestureColor = "#38bdf8", isRecovering = false, distCm = 35) {
            const HAND_CONNECTIONS = [
                [0, 1], [1, 2], [2, 3], [3, 4],
                [0, 5], [5, 6], [6, 7], [7, 8],
                [5, 9], [9, 10], [10, 11], [11, 12],
                [9, 13], [13, 14], [14, 15], [15, 16],
                [13, 17], [17, 18], [18, 19], [19, 20],
                [0, 17]
            ];

            const boneColor = isRecovering ? "rgba(16, 185, 129, 0.9)" : (gesturePct > 0 ? gestureColor : (isFist ? "rgba(248, 113, 113, 0.85)" : (isFast ? "rgba(245, 158, 11, 0.9)" : "rgba(56, 189, 248, 0.85)")));
            const jointColor = isRecovering ? "#10b981" : (gesturePct > 0 ? gestureColor : (isFist ? "#ef4444" : (isFast ? "#f59e0b" : "#38bdf8")));

            // Vẽ các đường nối xương
            ctx.lineWidth = isFast || gesturePct > 0 ? 4 : 3;
            ctx.strokeStyle = boneColor;
            ctx.beginPath();
            for (let pair of HAND_CONNECTIONS) {
                const p1 = landmarks[pair[0]];
                const p2 = landmarks[pair[1]];
                const x1 = mirrored ? (1 - p1.x) * w : p1.x * w;
                const y1 = p1.y * h;
                const x2 = mirrored ? (1 - p2.x) * w : p2.x * w;
                const y2 = p2.y * h;
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
            }
            ctx.stroke();

            // Vẽ các khớp đốt (Joints)
            for (let i = 0; i < landmarks.length; i++) {
                const pt = landmarks[i];
                const x = mirrored ? (1 - pt.x) * w : pt.x * w;
                const y = pt.y * h;

                ctx.beginPath();
                ctx.arc(x, y, [4, 8, 12, 16, 20].includes(i) ? 6 : 4, 0, 2 * Math.PI);
                ctx.fillStyle = [4, 8, 12, 16, 20].includes(i) ? (gesturePct > 0 ? gestureColor : (isFist ? "#ffedd5" : "#ffffff")) : jointColor;
                ctx.fill();
                ctx.strokeStyle = boneColor;
                ctx.lineWidth = 1.5;
                ctx.stroke();
            }

            // Vẽ tâm lòng bàn tay
            const palmX = (landmarks[0].x + landmarks[5].x + landmarks[17].x) / 3;
            const palmY = (landmarks[0].y + landmarks[5].y + landmarks[17].y) / 3;
            const px = mirrored ? (1 - palmX) * w : palmX * w;
            const py = palmY * h;

            ctx.beginPath();
            ctx.arc(px, py, 14, 0, 2 * Math.PI);
            ctx.strokeStyle = gesturePct > 0 ? gestureColor : (isFist ? "#ef4444" : (isFast ? "#f59e0b" : "#10b981"));
            ctx.lineWidth = 2.5;
            ctx.stroke();

            ctx.beginPath();
            ctx.arc(px, py, 4, 0, 2 * Math.PI);
            ctx.fillStyle = gesturePct > 0 ? gestureColor : (isFist ? "#f87171" : (isFast ? "#fbbf24" : "#34d399"));
            ctx.fill();

            // VẼ VÒNG TRÒN TIẾN ĐỘ GIỮ CỬ CHỈ (HOLD PROGRESS RING) QUANH TÂM TAY
            if (gesturePct > 0) {
                ctx.save();
                ctx.beginPath();
                ctx.arc(px, py, 26, -Math.PI / 2, -Math.PI / 2 + (2 * Math.PI * (gesturePct / 100)));
                ctx.strokeStyle = gestureColor || "#38bdf8";
                ctx.lineWidth = 4;
                ctx.lineCap = "round";
                ctx.stroke();

                ctx.fillStyle = gestureColor || "#38bdf8";
                ctx.font = "bold 13px Inter, sans-serif";
                ctx.textAlign = "center";
                ctx.fillText(gestureText, px, py - 34);
                ctx.restore();
            }

            // VẼ MỐC 0 CHUẨN ĐÃ HIỆU CHUẨN (CALIBRATED NEUTRAL CROSSHAIR)
            if (handCalib.calibrated) {
                const cx = mirrored ? (1 - handCalib.centerNormX) * w : handCalib.centerNormX * w;
                const cy = handCalib.centerNormY * h;

                ctx.save();
                ctx.strokeStyle = "rgba(244, 63, 94, 0.7)";
                ctx.lineWidth = 1.5;
                ctx.setLineDash([4, 4]);

                // Vòng tròn mốc 0
                ctx.beginPath();
                ctx.arc(cx, cy, 22, 0, 2 * Math.PI);
                ctx.stroke();

                // Dấu cộng tâm
                ctx.beginPath();
                ctx.moveTo(cx - 30, cy); ctx.lineTo(cx + 30, cy);
                ctx.moveTo(cx, cy - 30); ctx.lineTo(cx, cy + 30);
                ctx.stroke();

                ctx.fillStyle = "#f43f5e";
                ctx.font = "10px monospace";
                ctx.fillText("MỐC 0 CHUẨN", cx + 26, cy - 8);
                ctx.restore();
            }

            // VẼ THƯỚC ĐO CAO ĐỘ Z (VERTICAL HEIGHT GAUGE) BÊN PHẢI CANVAS
            const gaugeX = w - 18;
            const gaugeTop = 60;
            const gaugeBottom = h - 60;
            const gaugeH = gaugeBottom - gaugeTop;

            ctx.fillStyle = "rgba(0, 0, 0, 0.5)";
            ctx.fillRect(gaugeX - 6, gaugeTop, 12, gaugeH);
            ctx.strokeStyle = "rgba(255, 255, 255, 0.2)";
            ctx.strokeRect(gaugeX - 6, gaugeTop, 12, gaugeH);

            const zPct = (curZ - handCustomLimits.zMin) / (handCustomLimits.zMax - handCustomLimits.zMin);
            const zMarkerY = gaugeBottom - Math.max(0, Math.min(1, zPct)) * gaugeH;

            ctx.fillStyle = isFast ? "#f59e0b" : "#38bdf8";
            ctx.fillRect(gaugeX - 8, zMarkerY - 3, 16, 6);
            ctx.fillStyle = "#cbd5e1";
            ctx.font = "9px monospace";
            ctx.fillText(`Z: ${curZ.toFixed(0)}`, gaugeX - 48, zMarkerY + 3);
            ctx.fillStyle = "#38bdf8";
            ctx.fillText(`${distCm}cm`, gaugeX - 44, gaugeBottom + 16);

            // VẼ HUD TỐC ĐỘ VÀ TRẠNG THÁI BOOST
            if (isFast && !gesturePct && !isRecovering) {
                ctx.save();
                ctx.fillStyle = "rgba(245, 158, 11, 0.9)";
                ctx.fillRect(12, h - 34, 165, 22);
                ctx.fillStyle = "#0f172a";
                ctx.font = "bold 11px system-ui, sans-serif";
                ctx.fillText(`⚡ FAST TRACK: ${Math.round(velMmS)} mm/s`, 18, h - 19);
                ctx.restore();
            }

            // VẼ HUD CỬ CHỈ GỠ LỖI HOẶC TÁC VỤ ĐANG GIỮ
            if (isRecovering) {
                ctx.save();
                ctx.fillStyle = "rgba(16, 185, 129, 0.92)";
                ctx.fillRect(w / 2 - 140, 20, 280, 36);
                ctx.strokeStyle = "#ffffff";
                ctx.lineWidth = 1.5;
                ctx.strokeRect(w / 2 - 140, 20, 280, 36);
                ctx.fillStyle = "#ffffff";
                ctx.font = "bold 12.5px system-ui, sans-serif";
                ctx.textAlign = "center";
                ctx.fillText("🛡️ ĐANG GỠ LỖI & THU GỌN AN TOÀN...", w / 2, 43);
                ctx.restore();
            } else if (gesturePct > 0) {
                ctx.save();
                ctx.fillStyle = "rgba(15, 23, 42, 0.88)";
                ctx.fillRect(w / 2 - 140, 16, 280, 44);
                ctx.strokeStyle = gesturePct >= 100 ? "#10b981" : (gestureColor || "#38bdf8");
                ctx.lineWidth = 1.5;
                ctx.strokeRect(w / 2 - 140, 16, 280, 44);

                ctx.fillStyle = gesturePct >= 100 ? "#34d399" : (gestureColor || "#38bdf8");
                ctx.font = "bold 11.5px system-ui, sans-serif";
                ctx.textAlign = "center";
                ctx.fillText(`${gestureText}`, w / 2, 33);

                // Thanh tiến trình (Progress bar)
                ctx.fillStyle = "rgba(255, 255, 255, 0.15)";
                ctx.fillRect(w / 2 - 100, 40, 200, 10);
                ctx.fillStyle = gesturePct >= 100 ? "#10b981" : (gestureColor || "#38bdf8");
                ctx.fillRect(w / 2 - 100, 40, 200 * (gesturePct / 100), 10);
                ctx.restore();
            }
        }

