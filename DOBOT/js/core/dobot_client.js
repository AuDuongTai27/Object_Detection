// =========================================================================
// --- CORE: DOBOT COMMUNICATION CLIENT, TELEMETRY & SAFETY LIMITS ---
// =========================================================================

        const L1_BASE = 138;
        const L2_REAR = 135;
        const L3_FORE = 147;
        const L4_WRIST = 59;
        
        let toolOffset = 59.5;
        let currentMode = "live";
        let isRobotHardwareConnected = false;
        let isRobotConnected = false;
        let isRobotConnecting = false;

        // Trạng thái tọa độ & cấu hình an toàn toàn cục
        let lastKnownRobotPose = { x: 250, y: 0, z: 50, r: 0, zTcp: -9.5 };
        let cachedSafetyLimits = {
            z_min_standalone: -65.0,
            z_min_rail: -180.0,
            z_max: 165.0,
            safe_travel_z: 30.0,
            r_min: 140.0,
            r_max: 330.0
        };
        let isSafetyInputsDirty = false;
        let currentVisualRMin = null;
        let currentVisualRMax = null;

        // Trạng thái Dạy điểm (Teach & Playback) & Blockly
        let teachWaypoints = [];
        let isPlaybackRunning = false;
        let isPlaybackPaused = false;
        let playbackCurrentIndex = -1;
        let playbackLoop = false;
        let isBlocklyRunning = false;
        let blocklyWorkspace = null;
        let isPanelPinnedExpanded = false;

        function isSimulationMode() {
            if (currentMode === 'manual') return true;
            if (!isRobotConnected && !isRobotHardwareConnected) return true;
            if (!ws || ws.readyState !== WebSocket.OPEN) return true;
            return false;
        }

        let coordSystem = "cartesian";
        let isSuctionOn = false;
        let currentToolType = "suction";
        let showProjections = true;
        let ws = null;
        let currentX = 210, currentY = 0, currentZ = 66, currentR = 0;
        let isInteractingWithSliders = false;
        let lastRawJoints = { j1: 0, j2: 0, j3: 0, j4: 0 };
        let jogStep = 10;




        const DEFAULT_ROBOT_CLOUD_WS = "wss://rebuild-thinner-spur.ngrok-free.dev/ws";

        // --- WebSocket Connection ---
        function initWebSocket() {
            const loc = window.location;
            let wsUrl = localStorage.getItem('dobot_ws_url');

            if (!wsUrl) {
                // Nếu đang host trên Netlify / Vercel / GitHub Pages
                if (loc.hostname.includes("netlify.app") || loc.hostname.includes("vercel.app") || loc.hostname.includes("github.io")) {
                    wsUrl = DEFAULT_ROBOT_CLOUD_WS;
                } else if (loc.protocol === "http:" || loc.protocol === "https:") {
                    const proto = (loc.protocol === "https:") ? "wss:" : "ws:";
                    wsUrl = `${proto}//${loc.host}/ws`;
                } else {
                    wsUrl = "ws://localhost:8080/ws";
                }
            }

            try {
                ws = new WebSocket(wsUrl);
            } catch (err) {
                console.warn("WebSocket init error:", err);
                return;
            }

            const badge = document.getElementById('status-badge');
            const statusText = document.getElementById('status-text');

            ws.onopen = () => {
                console.log("WebSocket connected to:", wsUrl);
                badge.style.background = "";
                badge.style.borderColor = "";
                badge.style.color = "";
            };

            ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                if (msg.type === "pose") {
                    const navRobotBadge = document.getElementById('nav-robot-badge');
                    const navRobotText = document.getElementById('nav-robot-text');

                    if (msg.connected && msg.data) {
                        isRobotConnected = true;
                        isRobotHardwareConnected = true;
                        badge.className = "status-badge live";
                        badge.style.background = "";
                        badge.style.borderColor = "";
                        badge.style.color = "";
                        statusText.innerText = `● Đang đồng bộ thật (${msg.port})`;
                        
                        if (navRobotBadge) {
                            navRobotBadge.className = "sys-badge online";
                            navRobotText.innerText = `Robot: ${msg.port}`;
                        }
                        const btnRobot = document.getElementById('btn-toggle-robot');
                        if (btnRobot && !isRobotConnecting) {
                            btnRobot.innerText = "⏹️ Ngắt";
                            btnRobot.style.background = "#dc2626";
                            btnRobot.style.borderColor = "#f87171";
                        }

                        if (currentMode === "live") {
                            renderRobot(msg.data.j1, msg.data.j2, msg.data.j3, msg.data.j4, msg.data.x, msg.data.y, msg.data.z);
                        }
                    } else {
                        isRobotConnected = false;
                        isRobotHardwareConnected = false;
                        badge.className = "status-badge offline";
                        statusText.innerText = "○ Chưa kết nối Robot (Bấm nút Kết Nối khi cắm cáp USB)";

                        if (navRobotBadge) {
                            navRobotBadge.className = "sys-badge offline";
                            navRobotText.innerText = "Robot: Chưa kết nối";
                        }
                        const btnRobot = document.getElementById('btn-toggle-robot');
                        if (btnRobot && !isRobotConnecting) {
                            btnRobot.innerText = "🔌 Kết Nối";
                            btnRobot.style.background = "#2563eb";
                            btnRobot.style.borderColor = "#38bdf8";
                        }
                    }

                    // Hiển thị hoặc ẩn banner báo động lỗi
                    const alarmBanner = document.getElementById('alarm-banner');
                    const alarmDesc = document.getElementById('alarm-desc');
                    if (alarmBanner && alarmDesc) {
                        if (msg.has_alarm && msg.alarms && msg.alarms.length > 0) {
                            alarmBanner.style.display = "block";
                            const errs = msg.alarms.map(a => `• [${a.hex}] ${a.desc}`).join("<br>");
                            alarmDesc.innerHTML = errs;
                        } else {
                            alarmBanner.style.display = "none";
                        }
                    }

                    // Cập nhật thông tin hệ ray trượt và vùng an toàn từ WebSocket
                    if (msg.rail) {
                        updateRailTelemetry(msg.rail);
                    }
                    if (msg.safety) {
                        updateSafetyTelemetry(msg.safety);
                    }
                    if (typeof updateHandRobotStatusBadge === 'function') {
                        updateHandRobotStatusBadge();
                    }
                } else if (msg.type === "train_status") {
                    if (typeof updateTrainDashboard === "function") {
                        updateTrainDashboard(msg.data);
                    }
                } else if (msg.type === "vision_status") {
                    if (typeof updateVisionDashboard === "function") {
                        updateVisionDashboard(msg.data);
                    }
                } else if (msg.type === "feedback") {
                    showToast(msg.msg);
                }
            };

            ws.onclose = () => {
                isRobotConnected = false;
                isRobotHardwareConnected = false;
                badge.className = "status-badge offline";
                statusText.innerText = "○ Chưa bật Server hoặc chưa cắm USB (Tự thử lại...)";
                setTimeout(initWebSocket, 2500);
            };

            ws.onerror = () => {
                isRobotConnected = false;
                isRobotHardwareConnected = false;
                try { ws.close(); } catch(e){}
            };
        }

        // =========================================================================
        // CÁC HÀM XỬ LÝ ĐIỀU KHIỂN RAY TRƯỢT & VÙNG AN TOÀN TRÊN GIAO DIỆN
        // =========================================================================
        function updateRailTelemetry(rail) {
            // Khi đang chạy hoạt hình trượt ray trên giao diện mô phỏng, không để telemetry định kỳ làm ngắt quãng
            if (isRailAnimating) return;

            // Nếu kết nối robot thật: nhận vị trí thực tế
            // Nếu mô phỏng: chỉ nhận nếu server đang chủ động điều khiển chuyển động (is_moving / is_homing)
            if (isRobotConnected) {
                currentRailL = (rail.pos !== undefined) ? rail.pos : currentRailL;
            } else if (rail.is_moving || rail.is_homing) {
                currentRailL = (rail.pos !== undefined) ? rail.pos : currentRailL;
            }
            // Trong mô phỏng khi server nghỉ, giữ nguyên vị trí ray hiện tại của client!

            isRailModeActive = Boolean(rail.mode);
            isRailHardwareMoving = Boolean(rail.is_moving || rail.is_homing);

            // Cập nhật vị trí trên mô hình 3D & Vùng an toàn bám theo Dobot
            const railZ = (-500 + currentRailL);
            if (isRailModeActive) {
                railGroup.visible = true;
                railCarriage.position.z = railZ;
                if (typeof workspaceZoneGroup !== 'undefined' && workspaceZoneGroup) {
                    workspaceZoneGroup.position.z = railZ;
                }
            } else {
                railGroup.visible = false;
                if (typeof workspaceZoneGroup !== 'undefined' && workspaceZoneGroup) {
                    workspaceZoneGroup.position.z = 0;
                }
            }

            // Cập nhật UI
            const disp = document.getElementById('rail-pos-display');
            if (disp) disp.innerText = currentRailL.toFixed(1) + ' mm';

            const pbar = document.getElementById('rail-progress-bar');
            if (pbar) {
                const pct = Math.min(100, Math.max(0, (currentRailL / 1000.0) * 100));
                pbar.style.width = pct + '%';
            }

            const swDot = document.getElementById('rail-switch-dot');
            const swText = document.getElementById('rail-switch-text');
            const swBadge = document.getElementById('rail-switch-badge');
            if (swDot && swText && swBadge) {
                if (rail.switch) {
                    swDot.style.background = '#ef4444';
                    swBadge.style.borderColor = '#ef4444';
                    swBadge.style.background = 'rgba(239, 68, 68, 0.2)';
                    swText.innerText = 'Cảm biến cữ GP2 (EIO 14): ĐANG CHẠM (0.0mm)';
                    swText.style.color = '#fca5a5';
                } else {
                    swDot.style.background = '#22c55e';
                    swBadge.style.borderColor = '#22c55e';
                    swBadge.style.background = 'rgba(34, 197, 94, 0.15)';
                    swText.innerText = 'Cảm biến cữ GP2 (EIO 14): Sẵn sàng';
                    swText.style.color = '#86efac';
                }
            }

            const btnMode = document.getElementById('btn-toggle-rail-mode');
            if (btnMode) {
                if (isRailModeActive) {
                    btnMode.innerText = "✓ ĐANG BẬT RAY";
                    btnMode.style.background = "#0284c7";
                } else {
                    btnMode.innerText = "🪑 ĐỂ BÀN (TẮT RAY)";
                    btnMode.style.background = "#475569";
                }
            }
        }

        function updateSafetyVisualZone(rMin, rMax) {
            if (!rMin || !rMax || rMin <= 0 || rMax <= rMin) return;
            if (currentVisualRMin === rMin && currentVisualRMax === rMax) return;
            currentVisualRMin = rMin;
            currentVisualRMax = rMax;
            try {
                if (typeof zoneMesh !== 'undefined' && zoneMesh) {
                    zoneMesh.geometry.dispose();
                    zoneMesh.geometry = new THREE.RingGeometry(rMin, rMax, 64);
                }
                if (typeof innerLimitRing !== 'undefined' && innerLimitRing) {
                    innerLimitRing.geometry.dispose();
                    innerLimitRing.geometry = new THREE.RingGeometry(Math.max(1, rMin - 1.5), rMin + 0.5, 64);
                }
                if (typeof outerLimitRing !== 'undefined' && outerLimitRing) {
                    outerLimitRing.geometry.dispose();
                    outerLimitRing.geometry = new THREE.RingGeometry(rMax - 1, rMax + 1, 64);
                }
            } catch (err) {
                console.warn("Lỗi cập nhật hình học vùng an toàn:", err);
            }
        }

        function markSafetyUnsaved() {
            const st = document.getElementById('safety-save-status');
            if (st) {
                st.innerText = '● Chưa lưu (Bấm Lưu cài đặt)';
                st.style.color = '#f59e0b';
            }
        }

        function markSafetySaved() {
            const st = document.getElementById('safety-save-status');
            if (st) {
                st.innerText = '● Đã đồng bộ an toàn';
                st.style.color = '#86efac';
            }
        }

        function updateSafetyLiveStatus() {
            const flangeZ = (lastKnownRobotPose && lastKnownRobotPose.z !== undefined) ? lastKnownRobotPose.z : (currentZ + toolOffset);
            const tcpZ = (lastKnownRobotPose && lastKnownRobotPose.zTcp !== undefined) ? lastKnownRobotPose.zTcp : currentZ;
            const curR = Math.hypot(currentX, currentY);

            const container = document.getElementById('safety-live-info');
            if (container) {
                const zMin = isRailModeActive ? (cachedSafetyLimits?.z_min_rail ?? -180) : (cachedSafetyLimits?.z_min_standalone ?? -65);
                const zMax = cachedSafetyLimits?.z_max ?? 165;
                const rMin = cachedSafetyLimits?.r_min ?? 140;
                const rMax = cachedSafetyLimits?.r_max ?? 330;

                const isSafeZ = (flangeZ >= zMin - 1.0 && flangeZ <= zMax + 1.0);
                const isSafeR = (curR >= rMin - 1.0 && curR <= rMax + 1.0);
                const isSafe = isSafeZ && isSafeR;

                const pillBg = isSafe ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.25)';
                const pillColor = isSafe ? '#86efac' : '#fca5a5';
                const pillBorder = isSafe ? '#10b981' : '#ef4444';
                const pillText = isSafe ? '✓ ĐANG Ở VÙNG AN TOÀN' : '⚠ CẢNH BÁO: NGOÀI VÙNG AN TOÀN!';

                container.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-size: 11px; font-weight: 700; color: #38bdf8;">📡 TỌA ĐỘ ROBOT THỰC TẾ:</span>
                        <span style="display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 10px; font-weight: bold; background: ${pillBg}; color: ${pillColor}; border: 1px solid ${pillBorder};">
                            ${pillText}
                        </span>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; font-size: 11px; text-align: center;">
                        <div style="background: rgba(0,0,0,0.3); padding: 5px 4px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.06);">
                            <div style="color: #94a3b8; font-size: 9.5px;">Flange Z (Khớp Z)</div>
                            <div style="font-weight: bold; color: ${isSafeZ ? '#e2e8f0' : '#f87171'}; font-size: 12px;">${flangeZ.toFixed(1)} <span style="font-size: 9px; color: #64748b;">mm</span></div>
                        </div>
                        <div style="background: rgba(0,0,0,0.3); padding: 5px 4px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.06);">
                            <div style="color: #94a3b8; font-size: 9.5px;">TCP Z (Đầu Hút)</div>
                            <div style="font-weight: bold; color: #38bdf8; font-size: 12px;">${tcpZ.toFixed(1)} <span style="font-size: 9px; color: #64748b;">mm</span></div>
                        </div>
                        <div style="background: rgba(0,0,0,0.3); padding: 5px 4px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.06);">
                            <div style="color: #94a3b8; font-size: 9.5px;">Bán Kính R</div>
                            <div style="font-weight: bold; color: ${isSafeR ? '#e2e8f0' : '#f87171'}; font-size: 12px;">${curR.toFixed(1)} <span style="font-size: 9px; color: #64748b;">mm</span></div>
                        </div>
                    </div>
                    ${!isSafe ? `
                    <div style="margin-top: 6px; font-size: 10px; color: #fca5a5; background: rgba(239, 68, 68, 0.15); padding: 4px 8px; border-radius: 4px; border: 1px solid rgba(239, 68, 68, 0.3);">
                        ${!isSafeZ ? `• Flange Z (${flangeZ.toFixed(1)}mm) nằm ngoài dải an toàn [${zMin}, ${zMax}]mm.<br>` : ''}
                        ${!isSafeR ? `• Bán kính R (${curR.toFixed(1)}mm) nằm ngoài dải an toàn [${rMin}, ${rMax}]mm.` : ''}
                    </div>` : ''}
                `;
            }
        }

        function updateSafetyTelemetry(safety, forceInputs = false) {
            if (!safety) return;
            cachedSafetyLimits = Object.assign({}, cachedSafetyLimits || {}, safety);

            const inpZRail = document.getElementById('inp-safety-z-min-rail');
            const inpZStand = document.getElementById('inp-safety-z-min-standalone');
            const inpSafeZ = document.getElementById('inp-safety-safe-z');
            const inpZMax = document.getElementById('inp-safety-z-max');
            const inpRMin = document.getElementById('inp-safety-r-min');
            const inpRMax = document.getElementById('inp-safety-r-max');

            // Cập nhật giá trị vào input nếu được chỉ định ép buộc (forceInputs) hoặc người dùng chưa chỉnh sửa
            const canUpdateInputs = forceInputs || (!isSafetyInputsDirty && (!document.activeElement || document.activeElement.tagName !== 'INPUT'));
            if (canUpdateInputs) {
                if (inpZRail && safety.z_min_rail !== undefined) inpZRail.value = safety.z_min_rail;
                if (inpZStand && safety.z_min_standalone !== undefined) inpZStand.value = safety.z_min_standalone;
                if (inpSafeZ && safety.safe_travel_z !== undefined) inpSafeZ.value = safety.safe_travel_z;
                if (inpZMax && safety.z_max !== undefined) inpZMax.value = safety.z_max;
                if (inpRMin && safety.r_min !== undefined) inpRMin.value = safety.r_min;
                if (inpRMax && safety.r_max !== undefined) inpRMax.value = safety.r_max;
            }

            if (safety.r_min && safety.r_max) {
                updateSafetyVisualZone(safety.r_min, safety.r_max);
            }

            updateSafetyLiveStatus();
        }

        function sendRailJog(dist) {
            const speed = parseFloat(document.getElementById('slider-rail-speed')?.value || 100);
            const targetPos = Math.max(0, Math.min(1000, currentRailL + dist));
            
            // Cập nhật vị trí tức thời trên 3D & giao diện khi đang ở chế độ mô phỏng hoặc chưa kết nối
            if (!isRobotConnected || currentMode === 'manual') {
                currentRailL = targetPos;
                updateRailTelemetry({
                    mode: isRailModeActive,
                    pos: currentRailL,
                    switch: currentRailL <= 0.5,
                    is_homing: false,
                    is_moving: false
                });
            }
            sendAction('rail_jog', { dist: dist, speed: speed });
            showToast(`🚄 Đang Jog Ray: ${dist > 0 ? '+' : ''}${dist} mm...`);
        }

        function sendRailMoveFromInput() {
            const pos = Math.max(0, Math.min(1000, parseFloat(document.getElementById('inp-rail-target-l')?.value || 0)));
            const speed = parseFloat(document.getElementById('slider-rail-speed')?.value || 100);
            
            if (!isRobotConnected || currentMode === 'manual') {
                currentRailL = pos;
                updateRailTelemetry({
                    mode: isRailModeActive,
                    pos: currentRailL,
                    switch: currentRailL <= 0.5,
                    is_homing: false,
                    is_moving: false
                });
            }
            sendAction('rail_move', { pos: pos, speed: speed });
            showToast(`🚀 Đang chạy ray tới vị trí L = ${pos} mm...`);
        }

        function sendRailHome() {
            if (!isRobotConnected || currentMode === 'manual') {
                currentRailL = 5.0;
                updateRailTelemetry({
                    mode: isRailModeActive,
                    pos: 5.0,
                    switch: false,
                    is_homing: false,
                    is_moving: false
                });
                showToast('🎉 Mô phỏng: Ray đã về gốc và thoát cữ ra L = 5.0 mm an toàn.');
            }
            sendAction('rail_home');
            showToast(`🏠 Đang bắt đầu quy trình dò gốc ray (Homing và tự động thoát cữ an toàn)...`);
        }

        function sendRailStop() {
            sendAction('rail_stop');
            showToast(`🛑 Đã gửi lệnh dừng khẩn cấp ray trượt!`);
        }

        function toggleRailMode() {
            const nextMode = !isRailModeActive;
            isRailModeActive = nextMode;
            updateRailTelemetry({
                mode: isRailModeActive,
                pos: currentRailL,
                switch: currentRailL <= 0.5
            });
            sendAction('set_rail_mode', { enabled: nextMode });
            showToast(`⚙️ Đã chuyển chế độ: ${nextMode ? 'Ray trượt 1000mm' : 'Để bàn độc lập'}`);
        }

        // TÍNH NĂNG TƯƠNG TÁC LẤY TỌA ĐỘ ROBOT THỰC TẾ
        function captureCurrentZAsMin() {
            const currentZFlange = (lastKnownRobotPose && lastKnownRobotPose.z !== undefined) ? lastKnownRobotPose.z : (currentZ + toolOffset);
            const currentZTcp = (lastKnownRobotPose && lastKnownRobotPose.zTcp !== undefined) ? lastKnownRobotPose.zTcp : currentZ;
            
            isSafetyInputsDirty = true;
            markSafetyUnsaved();

            if (isRailModeActive) {
                const inp = document.getElementById('inp-safety-z-min-rail');
                if (inp) inp.value = currentZFlange.toFixed(1);
                showToast(`🎯 Đã gán Flange Z = ${currentZFlange.toFixed(1)}mm (Đầu hút ${currentZTcp.toFixed(1)}mm) làm Z Min Ray! Bấm "Lưu" để áp dụng.`);
            } else {
                const inp = document.getElementById('inp-safety-z-min-standalone');
                if (inp) inp.value = currentZFlange.toFixed(1);
                showToast(`🎯 Đã gán Flange Z = ${currentZFlange.toFixed(1)}mm làm Z Min Để bàn! Bấm "Lưu" để áp dụng.`);
            }
            updateSafetyLiveStatus();
        }

        function captureCurrentZAsSafe() {
            const currentZFlange = (lastKnownRobotPose && lastKnownRobotPose.z !== undefined) ? lastKnownRobotPose.z : (currentZ + toolOffset);
            isSafetyInputsDirty = true;
            markSafetyUnsaved();
            const inp = document.getElementById('inp-safety-safe-z');
            if (inp) inp.value = currentZFlange.toFixed(1);
            showToast(`🛫 Đã gán Flange Z = ${currentZFlange.toFixed(1)}mm làm Safe Travel Z! Bấm "Lưu" để áp dụng.`);
            updateSafetyLiveStatus();
        }

        async function saveSafetyLimits() {
            const zRail = parseFloat(document.getElementById('inp-safety-z-min-rail')?.value || -180);
            const zStand = parseFloat(document.getElementById('inp-safety-z-min-standalone')?.value || -65);
            const safeZ = parseFloat(document.getElementById('inp-safety-safe-z')?.value || 30);
            const zMax = parseFloat(document.getElementById('inp-safety-z-max')?.value || 165);
            const rMin = parseFloat(document.getElementById('inp-safety-r-min')?.value || 140);
            const rMax = parseFloat(document.getElementById('inp-safety-r-max')?.value || 330);

            if (rMin <= 0 || rMax <= rMin) {
                showToast("⚠️ Lỗi: Bán kính R Max phải lớn hơn R Min!");
                return;
            }
            if (zRail >= zMax || zStand >= zMax) {
                showToast("⚠️ Lỗi: Z Max phải cao hơn Z Min!");
                return;
            }

            const limits = {
                z_min_rail: zRail,
                z_min_standalone: zStand,
                safe_travel_z: safeZ,
                z_max: zMax,
                r_min: rMin,
                r_max: rMax
            };

            cachedSafetyLimits = Object.assign({}, cachedSafetyLimits || {}, limits);
            isSafetyInputsDirty = false;
            markSafetySaved();
            updateSafetyVisualZone(rMin, rMax);
            updateSafetyLiveStatus();

            try {
                const res = await fetch('/api/workspace/safety', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_rail_mode: isRailModeActive, limits: limits })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    showToast("💾 Đã lưu cấu hình vùng an toàn thành công!");
                } else {
                    showToast(`❌ Lỗi lưu cấu hình: ${data.error || 'Server từ chối'}`);
                }
            } catch (err) {
                sendAction('update_safety_limits', { limits: limits });
                showToast("💾 Đã gửi cập nhật vùng an toàn qua WebSocket!");
            }
        }

        async function resetSafetyLimitsToDefaults() {
            const defs = {
                z_min_rail: -180.0,
                z_min_standalone: -65.0,
                safe_travel_z: 30.0,
                z_max: 165.0,
                r_min: 140.0,
                r_max: 330.0
            };
            updateSafetyTelemetry(defs, true);
            isSafetyInputsDirty = true;
            markSafetyUnsaved();
            showToast("↩️ Đã khôi phục thông số mặc định! Bấm 'Lưu' để ghi nhớ.");
        }

        async function fetchSafetyLimits(forceInputs = true) {
            try {
                const res = await fetch('/api/workspace/safety');
                const data = await res.json();
                if (data.status === 'ok' && data.limits) {
                    updateSafetyTelemetry(data.limits, forceInputs);
                    markSafetySaved();
                    isSafetyInputsDirty = false;
                }
            } catch(e) {}
        }

        function sendAction(action, payload=null) {
            if (action === 'emergency_stop') {
                if (typeof isPlaybackRunning !== 'undefined' && isPlaybackRunning) stopPlayback();
                if (typeof isBlocklyRunning !== 'undefined' && isBlocklyRunning) stopBlocklyCode();
            }
            if (ws && ws.readyState === WebSocket.OPEN) {
                let data = { action: action };
                if (payload && typeof payload === 'object') {
                    data = Object.assign(data, payload);
                } else if (payload !== null) {
                    data.value = payload;
                }
                ws.send(JSON.stringify(data));
            }
        }

        async function handleToggleRobotConnect() {
            if (isRobotConnecting) return;
            const btn = document.getElementById('btn-toggle-robot');

            if (!isRobotConnected) {
                isRobotConnecting = true;
                if (btn) btn.innerText = "⏳ Đang dò...";
                showToast("🔌 Đang dò tìm và kết nối Dobot Magician qua USB...");
                try {
                    const res = await fetch('/api/robot/connect', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'}
                    });
                    const data = await res.json();
                    if (data.success && data.connected) {
                        isRobotConnected = true;
                        isRobotHardwareConnected = true;
                        showToast(`✅ ${data.message}`);
                        if (btn) {
                            btn.innerText = "⏹️ Ngắt";
                            btn.style.background = "#dc2626";
                            btn.style.borderColor = "#f87171";
                        }
                    } else {
                        showToast(`❌ ${data.error || 'Không tìm thấy Dobot'}`);
                        if (btn) {
                            btn.innerText = "🔌 Kết Nối";
                            btn.style.background = "#2563eb";
                            btn.style.borderColor = "#38bdf8";
                        }
                    }
                } catch(e) {
                    showToast(`❌ Lỗi kết nối: ${e.message}`);
                    if (btn) {
                        btn.innerText = "🔌 Kết Nối";
                        btn.style.background = "#2563eb";
                        btn.style.borderColor = "#38bdf8";
                    }
                } finally {
                    isRobotConnecting = false;
                }
            } else {
                isRobotConnecting = true;
                showToast("🔄 Đang ngắt kết nối Dobot...");
                try {
                    await fetch('/api/robot/disconnect', { method: 'POST' });
                    isRobotConnected = false;
                    showToast("✅ Đã ngắt kết nối Dobot Magician.");
                    if (btn) {
                        btn.innerText = "🔌 Kết Nối";
                        btn.style.background = "#2563eb";
                        btn.style.borderColor = "#38bdf8";
                    }
                } catch(e) {
                    showToast(`❌ Lỗi: ${e.message}`);
                } finally {
                    isRobotConnecting = false;
                }
            }
        }

        function toggleSuction() {
            isSuctionOn = !isSuctionOn;
            const btn = document.getElementById('btn-suction');
            btn.classList.toggle('active-suction', isSuctionOn);
            btn.innerText = isSuctionOn ? "💨 Tắt Giác Hút" : "💨 Giác Hút";
            sendAction('suction', isSuctionOn);
        }

        function triggerHoming() {
            const confirmed = confirm(
                "⚠️ CẢNH BÁO AN TOÀN KHI HOMING:\n\n" +
                "• Cánh tay robot sẽ tự động quay để tìm công tắc hành trình của từng khớp.\n" +
                "• Hãy chắc chắn không gian xung quanh cánh tay hoàn toàn thoáng đãng, không có vật cản!\n\n" +
                "Bạn có muốn tiếp tục chạy Homing ngay bây giờ?"
            );
            if (confirmed) {
                if (typeof isSimulationMode === 'function' && isSimulationMode()) {
                    showToast('🏠 [Mô phỏng 3D] Đang Homing về gốc...');
                    animateRobotCartesian(250, 0, 50, 0, 'safe', 600);
                } else {
                    sendAction('home');
                    showToast('🏠 Đang thực hiện Homing về gốc tọa độ chuẩn...');
                }
            }
        }

        window.addEventListener('resize', () => {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        });

        function animate() {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);

            // Cập nhật vị trí nhãn HUD nổi bám theo cục điểm đích 3D
            if (isTargetGizmoActive && targetBeaconGroup) {
                const railOffset = (typeof isRailModeActive !== 'undefined' && isRailModeActive) ? (-500 + currentRailL) : 0;
                const railYOffset = (typeof isRailModeActive !== 'undefined' && isRailModeActive) ? 42 : 0;
                const x = targetBeaconGroup.position.x;
                const y = -(targetBeaconGroup.position.z - railOffset);
                const zTcp = targetBeaconGroup.position.y - L1_BASE - railYOffset;
                const rHoriz = Math.sqrt(x * x + y * y);
                const rMin = cachedSafetyLimits?.r_min ?? 140;
                const rMax = cachedSafetyLimits?.r_max ?? 330;
                const zMin = isRailModeActive ? (cachedSafetyLimits?.z_min_rail ?? -180) : (cachedSafetyLimits?.z_min_standalone ?? -65);
                const zMax = cachedSafetyLimits?.z_max ?? 165;
                const zFlange = zTcp + toolOffset;
                const isValid = (rHoriz >= rMin && rHoriz <= rMax && zFlange >= zMin && zFlange <= zMax);
                updateBeaconHudLabel(targetBeaconGroup.position, x, y, zTcp, isValid);
            }
        }

        // =====================================================================
        // QUẢN LÝ MENU BẢNG ĐIỀU KHIỂN: KÉO (DRAG), RESIZE, BẬT TẮT, THU GỌN
        // =====================================================================
        const panelEl = document.getElementById('panel');
        const panelTitleBar = document.getElementById('panel-title-bar');
        const floatingToggleBtn = document.getElementById('floating-toggle-btn');
        const btnWinCollapse = document.getElementById('btn-win-collapse');
        const btnWinSize = document.getElementById('btn-win-size');
        const resizeCorner = document.getElementById('panel-resize-corner');
        const resizeEdgeR = document.getElementById('panel-resize-r');
        const resizeEdgeB = document.getElementById('panel-resize-b');

        let isPanelCollapsed = false;
        let isPanelMaximized = false;

        function showPanel() {
            panelEl.style.display = 'flex';
            if (floatingToggleBtn) floatingToggleBtn.style.display = 'none';
            const btnReopen = document.getElementById('btn-reopen-panel');
            if (btnReopen) btnReopen.style.display = 'none';
        }

        function hidePanel() {
            panelEl.style.display = 'none';
            if (floatingToggleBtn) floatingToggleBtn.style.display = 'flex';
            const btnReopen = document.getElementById('btn-reopen-panel');
            if (btnReopen && currentStudioTab === '3d') btnReopen.style.display = 'flex';
            showToast("Đã ẩn bảng điều khiển. Bấm nút '📋 Mở Bảng Điều Khiển' hoặc nhấn phím 'M' để mở lại.");
        }

        function togglePanel() {
            if (panelEl.style.display === 'none') {
                showPanel();
            } else {
                hidePanel();
            }
        }

        function togglePanelCollapse() {
            isPanelCollapsed = !isPanelCollapsed;
            if (isPanelCollapsed) {
                panelEl.classList.add('collapsed');
                btnWinCollapse.innerHTML = '▲';
                btnWinCollapse.title = 'Mở rộng menu';
            } else {
                panelEl.classList.remove('collapsed');
                btnWinCollapse.innerHTML = '─';
                btnWinCollapse.title = 'Thu gọn menu';
            }
        }

        function togglePanelMaximize() {
            if (isPanelCollapsed) togglePanelCollapse();
            isPanelMaximized = !isPanelMaximized;
            if (isPanelMaximized) {
                panelEl.classList.add('maximized');
                btnWinSize.innerHTML = '⤡';
                btnWinSize.title = 'Thu nhỏ về kích thước chuẩn (380px)';
            } else {
                panelEl.classList.remove('maximized');
                panelEl.style.width = '380px';
                btnWinSize.innerHTML = '⤢';
                btnWinSize.title = 'Phóng to chiều rộng (540px)';
            }
        }

