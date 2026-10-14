// =========================================================================
// --- MODULE: TEACH & PLAYBACK SYSTEM ---
// =========================================================================

        function addCurrentRobotPoseToTeach() {
            const x = Math.round(lastKnownRobotPose.x * 10) / 10;
            const y = Math.round(lastKnownRobotPose.y * 10) / 10;
            const zTcp = Math.round(lastKnownRobotPose.zTcp * 10) / 10;
            const r = Math.round(lastKnownRobotPose.r * 10) / 10;
            const idx = teachWaypoints.length + 1;

            teachWaypoints.push({
                id: 'pt_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4),
                name: `Điểm ${idx}`,
                x: x,
                y: y,
                zTcp: zTcp,
                r: r,
                moveType: 'safe',
                suction: 'keep',
                delay: 1.0
            });

            renderTeachList();
            showToast(`📍 Đã lưu vị trí Robot: X=${x}, Y=${y}, Z=${zTcp}`);
        }

        function addTargetGizmoPoseToTeach() {
            if (!targetBeaconGroup) return;
            const railOffset = (typeof isRailModeActive !== 'undefined' && isRailModeActive) ? (-500 + currentRailL) : 0;
            const railYOffset = (typeof isRailModeActive !== 'undefined' && isRailModeActive) ? 42 : 0;
            const x = Math.round(targetBeaconGroup.position.x * 10) / 10;
            const y = Math.round(-(targetBeaconGroup.position.z - railOffset) * 10) / 10;
            const zTcp = Math.round((targetBeaconGroup.position.y - L1_BASE - railYOffset) * 10) / 10;
            const r = parseFloat(document.getElementById('inp-target-r').value) || 0;
            const idx = teachWaypoints.length + 1;

            teachWaypoints.push({
                id: 'pt_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4),
                name: `Cục Đích ${idx}`,
                x: x,
                y: y,
                zTcp: zTcp,
                r: Math.round(r * 10) / 10,
                moveType: 'safe',
                suction: 'keep',
                delay: 1.0
            });

            renderTeachList();
            showToast(`🎯 Đã lưu Cục Đích: X=${x}, Y=${y}, Z=${zTcp}`);
        }

        function renderTeachList() {
            const container = document.getElementById('teach-list-container');
            const countEl = document.getElementById('teach-count');
            if (countEl) countEl.innerText = teachWaypoints.length;
            if (!container) return;

            if (teachWaypoints.length === 0) {
                container.innerHTML = `
                    <div style="text-align: center; color: #64748b; font-size: 11.5px; padding: 25px 10px; border: 1px dashed rgba(255,255,255,0.1); border-radius: 8px;">
                        Chưa có điểm nào.<br>
                        Bấm <b>📍 Lưu Robot Thật</b> hoặc <b>🎯 Lưu Cục Đích 3D</b> để bắt đầu dạy kịch bản!
                    </div>
                `;
                return;
            }

            let html = '';
            teachWaypoints.forEach((pt, idx) => {
                const isCurrent = (isPlaybackRunning && playbackCurrentIndex === idx);
                const isSafe = (pt.moveType === 'safe');
                html += `
                    <div class="teach-card ${isCurrent ? 'active-step' : ''} ${isSafe ? 'type-safe' : 'type-direct'}" id="teach-step-${idx}">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="display: flex; align-items: center; gap: 6px;">
                                <span class="teach-step-pill">#${idx + 1}</span>
                                <input type="text" value="${pt.name}" onchange="updateTeachPointProp(${idx}, 'name', this.value)"
                                    style="background: transparent; border: none; border-bottom: 1px solid rgba(255,255,255,0.18); color: #fff; font-size: 11.5px; font-weight: 600; width: 85px; outline: none; padding: 1px 2px;">
                            </div>
                            <span style="font-family: monospace; font-size: 10.5px; color: #38bdf8; font-weight: bold; background: rgba(56,189,248,0.1); padding: 1px 5px; border-radius: 4px;">
                                X:${pt.x.toFixed(0)} Y:${pt.y.toFixed(0)} Z:${pt.zTcp.toFixed(0)}
                            </span>
                            <div style="display: flex; gap: 3px;">
                                <button class="btn-teach-action" onclick="executeSingleTeachPoint(${idx})" title="Chạy thử điểm này">▶️</button>
                                <button class="btn-teach-action btn-teach-del" onclick="deleteTeachPoint(${idx})" title="Xóa điểm này">🗑️</button>
                            </div>
                        </div>
                        <div style="display: flex; gap: 5px; margin-top: 5px; align-items: center;">
                            <select class="teach-select" onchange="updateTeachPointProp(${idx}, 'moveType', this.value); renderTeachList();" style="flex: 1.1;">
                                <option value="safe" ${pt.moveType === 'safe' ? 'selected' : ''}>📦 Safe Jump</option>
                                <option value="direct" ${pt.moveType === 'direct' ? 'selected' : ''}>🚀 Direct PTP</option>
                            </select>
                            <select class="teach-select" onchange="updateTeachPointProp(${idx}, 'suction', this.value)" style="flex: 1.1;">
                                <option value="keep" ${pt.suction === 'keep' ? 'selected' : ''}>💨 Giữ nguyên</option>
                                <option value="on" ${pt.suction === 'on' ? 'selected' : ''}>💨 Bật hút</option>
                                <option value="off" ${pt.suction === 'off' ? 'selected' : ''}>❌ Tắt/Xả</option>
                            </select>
                            <div style="display: flex; align-items: center; gap: 2px;">
                                <input type="number" class="teach-input-num" value="${pt.delay || 1.0}" step="0.5" min="0" max="30"
                                    onchange="updateTeachPointProp(${idx}, 'delay', parseFloat(this.value) || 0)">
                                <span style="font-size: 11px; color: #cbd5e1; font-weight: 600;">s</span>
                            </div>
                        </div>
                    </div>
                `;
            });

            container.innerHTML = html;
        }

        function updateTeachPointProp(idx, prop, value) {
            if (teachWaypoints[idx]) {
                teachWaypoints[idx][prop] = value;
            }
        }

        function deleteTeachPoint(idx) {
            if (isPlaybackRunning) {
                showToast("⚠️ Vui lòng dừng kịch bản trước khi xóa điểm!");
                return;
            }
            teachWaypoints.splice(idx, 1);
            renderTeachList();
        }

        function clearAllTeachPoints() {
            if (teachWaypoints.length === 0) return;
            if (confirm("Bạn có chắc chắn muốn xóa toàn bộ danh sách điểm đã dạy?")) {
                if (isPlaybackRunning) stopPlayback();
                teachWaypoints = [];
                renderTeachList();
                showToast("🗑️ Đã xóa sạch danh sách điểm!");
            }
        }

        function togglePlaybackLoop(checked) {
            playbackLoop = checked;
        }

        async function executeSingleTeachPoint(idx) {
            const pt = teachWaypoints[idx];
            if (!pt) return;
            const zFlange = pt.zTcp + toolOffset;
            if (isSimulationMode()) {
                showToast(`🎮 [Mô phỏng 3D] Di chuyển tới ${pt.name} (X=${pt.x}, Y=${pt.y}, Z=${pt.zTcp})`);
                await animateRobotCartesian(pt.x, pt.y, pt.zTcp, pt.r, pt.moveType, pt.moveType === 'safe' ? 550 : 400);
            } else {
                if (pt.moveType === 'safe') {
                    sendAction('safe_jump', { x: pt.x, y: pt.y, z: zFlange, r: pt.r });
                } else {
                    sendAction('move_xyz', { x: pt.x, y: pt.y, z: zFlange, r: pt.r, mode: 1 });
                }
                showToast(`▶️ Đang di chuyển tới ${pt.name} (X=${pt.x}, Y=${pt.y}, Z=${pt.zTcp})`);
            }

            if (pt.suction === 'on') {
                setSuctionState(true);
            } else if (pt.suction === 'off') {
                setSuctionState(false);
            }
        }

        function setSuctionState(enable) {
            isSuctionOn = enable;
            const btn = document.getElementById('btn-suction');
            if (btn) {
                btn.classList.toggle('active-suction', isSuctionOn);
                btn.innerText = isSuctionOn ? "💨 Tắt Giác Hút" : "💨 Giác Hút";
            }
            sendAction('suction', isSuctionOn);
        }

        function waitForRobotToReach(tx, ty, tzFlange, timeoutMs=7000) {
            return new Promise(resolve => {
                const startTime = Date.now();
                const timer = setInterval(() => {
                    if (!isPlaybackRunning) {
                        clearInterval(timer);
                        resolve();
                        return;
                    }
                    const cur = lastKnownRobotPose;
                    if (cur) {
                        const dx = cur.x - tx;
                        const dy = cur.y - ty;
                        const dz = cur.z - tzFlange;
                        const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
                        // Khi robot tới gần mục tiêu < 3.0mm, chuyển tiếp bước tiếp theo
                        if (dist < 3.0) {
                            clearInterval(timer);
                            resolve();
                            return;
                        }
                    }
                    if (Date.now() - startTime > timeoutMs) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 80);
            });
        }

        async function startPlayback() {
            if (teachWaypoints.length === 0) {
                showToast("⚠️ Danh sách điểm đang trống! Hãy thêm điểm trước.");
                return;
            }

            if (isPlaybackRunning && isPlaybackPaused) {
                isPlaybackPaused = false;
                document.getElementById('btn-playback-pause').innerText = "⏸️ Tạm Dừng";
                document.getElementById('playback-status-bar').innerText = "Đang tiếp tục...";
                return;
            }

            isPlaybackRunning = true;
            isPlaybackPaused = false;
            document.getElementById('btn-playback-run').disabled = true;
            document.getElementById('btn-playback-pause').disabled = false;
            document.getElementById('btn-playback-stop').disabled = false;

            let loopCount = 0;
            try {
                do {
                    loopCount++;
                    for (let i = 0; i < teachWaypoints.length; i++) {
                        if (!isPlaybackRunning) break;

                        while (isPlaybackPaused && isPlaybackRunning) {
                            await sleepMs(100);
                        }
                        if (!isPlaybackRunning) break;

                        playbackCurrentIndex = i;
                        renderTeachList();
                        const pt = teachWaypoints[i];
                        const statusBar = document.getElementById('playback-status-bar');
                        const isSim = isSimulationMode();
                        if (statusBar) {
                            statusBar.innerText = `${isSim ? '🎮 [Mô phỏng 3D]' : 'Đang chạy'}: Bước ${i+1}/${teachWaypoints.length} (${pt.name})${playbackLoop ? ` | Vòng ${loopCount}` : ''}`;
                            statusBar.style.color = isSim ? "#38bdf8" : "#4ade80";
                        }

                        // 1. Gửi lệnh di chuyển & Chờ hoàn thành
                        const zFlange = pt.zTcp + toolOffset;
                        if (isSim) {
                            const ok = await animateRobotCartesian(pt.x, pt.y, pt.zTcp, pt.r, pt.moveType, pt.moveType === 'safe' ? 550 : 400, () => isPlaybackRunning, () => isPlaybackPaused);
                            if (!ok && !isPlaybackRunning) break;
                        } else {
                            if (pt.moveType === 'safe') {
                                sendAction('safe_jump', { x: pt.x, y: pt.y, z: zFlange, r: pt.r });
                            } else {
                                sendAction('move_xyz', { x: pt.x, y: pt.y, z: zFlange, r: pt.r, mode: 1 });
                            }
                            // 2. Chờ robot hoàn thành di chuyển
                            await waitForRobotToReach(pt.x, pt.y, zFlange, 7000);
                        }
                        if (!isPlaybackRunning) break;

                        // 3. Xử lý giác hút nếu có cài đặt
                        if (pt.suction === 'on') {
                            setSuctionState(true);
                            await sleepMs(350);
                        } else if (pt.suction === 'off') {
                            setSuctionState(false);
                            await sleepMs(350);
                        }

                        // 4. Thời gian dừng chờ
                        const waitTime = Math.max(0, (pt.delay || 1.0) * 1000);
                        if (waitTime > 0) {
                            await sleepMs(waitTime);
                        }
                    }
                } while (isPlaybackRunning && playbackLoop);
            } catch (err) {
                console.error("Lỗi khi chạy kịch bản:", err);
            } finally {
                stopPlayback();
            }
        }

        function pausePlayback() {
            if (!isPlaybackRunning) return;
            isPlaybackPaused = !isPlaybackPaused;
            const btn = document.getElementById('btn-playback-pause');
            const status = document.getElementById('playback-status-bar');
            if (isPlaybackPaused) {
                if (btn) btn.innerText = "▶️ Tiếp Tục";
                if (status) {
                    status.innerText = "⏸️ Kịch bản đang tạm dừng";
                    status.style.color = "#facc15";
                }
            } else {
                if (btn) btn.innerText = "⏸️ Tạm Dừng";
                if (status) {
                    status.innerText = "Đang tiếp tục...";
                    status.style.color = "#4ade80";
                }
            }
        }

        function stopPlayback() {
            isPlaybackRunning = false;
            isPlaybackPaused = false;
            playbackCurrentIndex = -1;
            const btnRun = document.getElementById('btn-playback-run');
            const btnPause = document.getElementById('btn-playback-pause');
            const btnStop = document.getElementById('btn-playback-stop');
            const statusBar = document.getElementById('playback-status-bar');

            if (btnRun) btnRun.disabled = false;
            if (btnPause) {
                btnPause.disabled = true;
                btnPause.innerText = "⏸️ Tạm Dừng";
            }
            if (btnStop) btnStop.disabled = true;
            if (statusBar) {
                statusBar.innerText = "Trạng thái: Sẵn sàng";
                statusBar.style.color = "#cbd5e1";
            }
            renderTeachList();
        }

        function loadSampleTeachPreset() {
            if (isPlaybackRunning) {
                showToast("⚠️ Vui lòng dừng kịch bản trước khi nạp mẫu!");
                return;
            }
            teachWaypoints = [
                {
                    id: 'sample_1',
                    name: 'Điểm Chờ',
                    x: 240.0,
                    y: 0.0,
                    zTcp: 30.0,
                    r: 0.0,
                    moveType: 'safe',
                    suction: 'off',
                    delay: 0.5
                },
                {
                    id: 'sample_2',
                    name: 'Hạ Hút Phôi (A)',
                    x: 200.0,
                    y: 120.0,
                    zTcp: -110.0,
                    r: 0.0,
                    moveType: 'safe',
                    suction: 'on',
                    delay: 1.0
                },
                {
                    id: 'sample_3',
                    name: 'Nhấc An Toàn',
                    x: 200.0,
                    y: 120.0,
                    zTcp: 35.0,
                    r: 0.0,
                    moveType: 'direct',
                    suction: 'keep',
                    delay: 0.5
                },
                {
                    id: 'sample_4',
                    name: 'Thả Khay (B)',
                    x: 267.7,
                    y: 28.7,
                    zTcp: -103.5,
                    r: 0.0,
                    moveType: 'safe',
                    suction: 'off',
                    delay: 1.0
                }
            ];
            renderTeachList();
            showToast("📦 Đã nạp kịch bản mẫu Gắp Thả 4 bước!");
        }

        function exportTeachProgramJSON() {
            if (teachWaypoints.length === 0) {
                showToast("⚠️ Chưa có điểm nào để xuất!");
                return;
            }
            const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(teachWaypoints, null, 2));
            const downloadAnchor = document.createElement('a');
            downloadAnchor.setAttribute("href", dataStr);
            downloadAnchor.setAttribute("download", `dobot_teach_program_${new Date().toISOString().slice(0, 10)}.json`);
            document.body.appendChild(downloadAnchor);
            downloadAnchor.click();
            downloadAnchor.remove();
            showToast("💾 Đã xuất file kịch bản JSON!");
        }

        function importTeachProgramJSON(event) {
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = (e) => {
                try {
                    const loaded = JSON.parse(e.target.result);
                    if (Array.isArray(loaded)) {
                        teachWaypoints = loaded;
                        renderTeachList();
                        showToast(`📂 Đã nạp thành công ${loaded.length} điểm từ file JSON!`);
                    } else {
                        alert("Định dạng file JSON không hợp lệ (Phải là mảng các điểm)!");
                    }
                } catch (err) {
                    alert("Lỗi khi đọc file JSON: " + err.message);
                }
            };
            reader.readAsText(file);
            event.target.value = '';
        }

        

