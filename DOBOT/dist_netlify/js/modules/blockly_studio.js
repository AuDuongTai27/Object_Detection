// =========================================================================
// --- MODULE: DOBOT BLOCKLY VISUAL PROGRAMMING STUDIO ---
// =========================================================================

        // ========================================================
        // HỆ THỐNG LẬP TRÌNH KHỐI KÉO THẢ (DOBOT BLOCKLY)
        // ========================================================
        let isBlocklyPaused = false;
        let isBlocklyInitialized = false;
        let currentCodeLang = 'python';
        let isCodeDrawerOpen = false;
        let dobotBlocksRegistered = false;
        let dobotGeneratorsRegistered = false;

        function togglePanelWidth() {
            const panel = document.getElementById('panel');
            if (!panel) return;
            panel.classList.toggle('panel-expanded');
            isPanelPinnedExpanded = panel.classList.contains('panel-expanded');
            const btn = document.getElementById('btn-toggle-expand');
            if (btn) btn.innerText = isPanelPinnedExpanded ? "◀️ Thu Gọn" : "↔️ Mở Rộng";
            setTimeout(() => {
                if (blocklyWorkspace && typeof Blockly !== 'undefined') {
                    Blockly.svgResize(blocklyWorkspace);
                }
            }, 260);
        }

        function showBlocklyStatus(msg, color='#f1f5f9') {
            const txt = document.getElementById('blockly-status-text');
            const dot = document.getElementById('blockly-status-dot');
            if (txt) {
                txt.innerText = msg;
                txt.style.color = color;
            }
            if (dot) {
                dot.style.background = color;
            }
        }

        function parseXmlText(xmlText) {
            if (window.Blockly && window.Blockly.utils && window.Blockly.utils.xml && window.Blockly.utils.xml.textToDom) {
                return window.Blockly.utils.xml.textToDom(xmlText);
            }
            if (window.Blockly && window.Blockly.Xml && window.Blockly.Xml.textToDom) {
                return window.Blockly.Xml.textToDom(xmlText);
            }
            const parser = new DOMParser();
            return parser.parseFromString(xmlText, 'text/xml').documentElement;
        }

        function registerDobotCustomBlocks() {
            if (dobotBlocksRegistered || typeof Blockly === 'undefined') return;

            Blockly.defineBlocksWithJsonArray([
                {
                    "type": "dobot_move_xyz",
                    "message0": "🦾 tới X %1 Y %2 Z %3 R %4 %5",
                    "args0": [
                        { "type": "field_number", "name": "X", "value": 240, "min": -350, "max": 350 },
                        { "type": "field_number", "name": "Y", "value": 0, "min": -350, "max": 350 },
                        { "type": "field_number", "name": "Z", "value": 30, "min": -250, "max": 200 },
                        { "type": "field_number", "name": "R", "value": 0, "min": -180, "max": 180 },
                        {
                            "type": "field_dropdown",
                            "name": "MODE",
                            "options": [
                                ["📦 Nhấc An Toàn", "safe"],
                                ["🚀 Bay Thẳng", "direct"]
                            ]
                        }
                    ],
                    "previousStatement": null,
                    "nextStatement": null,
                    "colour": "#1971c2",
                    "tooltip": "Di chuyển đầu hút robot tới tọa độ Cartesian (X, Y, Z, R)"
                },
                {
                    "type": "dobot_move_joint",
                    "message0": "🦾 quay khớp J1 %1 ° J2 %2 ° J3 %3 ° J4 %4 °",
                    "args0": [
                        { "type": "field_number", "name": "J1", "value": 0, "min": -90, "max": 90 },
                        { "type": "field_number", "name": "J2", "value": 20, "min": 0, "max": 85 },
                        { "type": "field_number", "name": "J3", "value": 40, "min": -10, "max": 85 },
                        { "type": "field_number", "name": "J4", "value": 0, "min": -90, "max": 90 }
                    ],
                    "previousStatement": null,
                    "nextStatement": null,
                    "colour": "#3b5bdb",
                    "tooltip": "Quay độc lập các khớp servo J1, J2, J3, J4"
                },
                {
                    "type": "dobot_move_relative",
                    "message0": "🦾 tương đối dX %1 dY %2 dZ %3 dR %4",
                    "args0": [
                        { "type": "field_number", "name": "DX", "value": 0, "min": -100, "max": 100 },
                        { "type": "field_number", "name": "DY", "value": 0, "min": -100, "max": 100 },
                        { "type": "field_number", "name": "DZ", "value": 10, "min": -100, "max": 100 },
                        { "type": "field_number", "name": "DR", "value": 0, "min": -180, "max": 180 }
                    ],
                    "previousStatement": null,
                    "nextStatement": null,
                    "colour": "#0c8599",
                    "tooltip": "Dịch chuyển tương đối từ vị trí hiện tại thêm dX, dY, dZ, dR"
                },
                {
                    "type": "dobot_suction",
                    "message0": "💨 giác hút %1",
                    "args0": [
                        {
                            "type": "field_dropdown",
                            "name": "STATE",
                            "options": [
                                ["💨 BẬT (Hút)", "ON"],
                                ["❌ TẮT (Nhả)", "OFF"]
                            ]
                        }
                    ],
                    "previousStatement": null,
                    "nextStatement": null,
                    "colour": "#2f9e44",
                    "tooltip": "Bật/Tắt giác hút khí nén"
                },
                {
                    "type": "dobot_wait",
                    "message0": "⏱️ dừng chờ %1 giây",
                    "args0": [
                        { "type": "field_number", "name": "TIME", "value": 1.0, "min": 0, "precision": 0.1 }
                    ],
                    "previousStatement": null,
                    "nextStatement": null,
                    "colour": "#f59f00",
                    "tooltip": "Tạm dừng chương trình trong khoảng thời gian xác định"
                },
                {
                    "type": "dobot_home",
                    "message0": "🏠 Chạy Homing về vị trí chuẩn",
                    "previousStatement": null,
                    "nextStatement": null,
                    "colour": "#e8590c",
                    "tooltip": "Hiệu chuẩn và đưa robot về tọa độ chuẩn cơ khí"
                }
            ]);

            dobotBlocksRegistered = true;
        }

        function registerDobotGenerators() {
            if (dobotGeneratorsRegistered || typeof Blockly === 'undefined') return;

            const jsGen = (window.javascript && window.javascript.javascriptGenerator) || (window.Blockly && Blockly.JavaScript);
            const pyGen = (window.python && window.python.pythonGenerator) || (window.Blockly && Blockly.Python);

            function reg(gen, type, fn) {
                if (!gen) return;
                if (gen.forBlock) gen.forBlock[type] = fn;
                gen[type] = fn;
            }

            if (jsGen) {
                reg(jsGen, 'dobot_move_xyz', function(block) {
                    const x = Number(block.getFieldValue('X')) || 0;
                    const y = Number(block.getFieldValue('Y')) || 0;
                    const z = Number(block.getFieldValue('Z')) || 0;
                    const r = Number(block.getFieldValue('R')) || 0;
                    const mode = block.getFieldValue('MODE') || 'safe';
                    return `await dobotApi.moveXYZ(${x}, ${y}, ${z}, ${r}, '${mode}', '${block.id}');\n`;
                });

                reg(jsGen, 'dobot_move_joint', function(block) {
                    const j1 = Number(block.getFieldValue('J1')) || 0;
                    const j2 = Number(block.getFieldValue('J2')) || 0;
                    const j3 = Number(block.getFieldValue('J3')) || 0;
                    const j4 = Number(block.getFieldValue('J4')) || 0;
                    return `await dobotApi.moveJoints(${j1}, ${j2}, ${j3}, ${j4}, '${block.id}');\n`;
                });

                reg(jsGen, 'dobot_move_relative', function(block) {
                    const dx = Number(block.getFieldValue('DX')) || 0;
                    const dy = Number(block.getFieldValue('DY')) || 0;
                    const dz = Number(block.getFieldValue('DZ')) || 0;
                    const dr = Number(block.getFieldValue('DR')) || 0;
                    return `await dobotApi.moveRelative(${dx}, ${dy}, ${dz}, ${dr}, '${block.id}');\n`;
                });

                reg(jsGen, 'dobot_suction', function(block) {
                    const state = block.getFieldValue('STATE');
                    return `await dobotApi.suction(${state === 'ON'}, '${block.id}');\n`;
                });

                reg(jsGen, 'dobot_wait', function(block) {
                    const time = Number(block.getFieldValue('TIME')) || 0;
                    return `await dobotApi.wait(${time}, '${block.id}');\n`;
                });

                reg(jsGen, 'dobot_home', function(block) {
                    return `await dobotApi.home('${block.id}');\n`;
                });
            }

            if (pyGen) {
                reg(pyGen, 'dobot_move_xyz', function(block) {
                    const x = block.getFieldValue('X');
                    const y = block.getFieldValue('Y');
                    const z = block.getFieldValue('Z');
                    const r = block.getFieldValue('R');
                    const mode = block.getFieldValue('MODE') || 'safe';
                    return `dobot.move_to(x=${x}, y=${y}, z=${z}, r=${r}, mode='${mode}')\n`;
                });

                reg(pyGen, 'dobot_move_joint', function(block) {
                    const j1 = block.getFieldValue('J1');
                    const j2 = block.getFieldValue('J2');
                    const j3 = block.getFieldValue('J3');
                    const j4 = block.getFieldValue('J4');
                    return `dobot.set_joint_angles(j1=${j1}, j2=${j2}, j3=${j3}, j4=${j4})\n`;
                });

                reg(pyGen, 'dobot_move_relative', function(block) {
                    const dx = block.getFieldValue('DX');
                    const dy = block.getFieldValue('DY');
                    const dz = block.getFieldValue('DZ');
                    const dr = block.getFieldValue('DR');
                    return `dobot.move_relative(dx=${dx}, dy=${dy}, dz=${dz}, dr=${dr})\n`;
                });

                reg(pyGen, 'dobot_suction', function(block) {
                    const state = block.getFieldValue('STATE');
                    return `dobot.set_suction(${state === 'ON' ? 'True' : 'False'})\n`;
                });

                reg(pyGen, 'dobot_wait', function(block) {
                    const time = block.getFieldValue('TIME');
                    return `time.sleep(${time})\n`;
                });

                reg(pyGen, 'dobot_home', function(block) {
                    return `dobot.home()\n`;
                });
            }

            dobotGeneratorsRegistered = true;
        }

        function initBlocklyWorkspaceIfNeeded() {
            if (isBlocklyInitialized) return;
            if (typeof Blockly === 'undefined') {
                console.warn("Blockly library chưa tải xong...");
                return;
            }

            try {
                registerDobotCustomBlocks();
                registerDobotGenerators();

                const blocklyContainer = document.getElementById('blocklyDiv');
                const toolboxEl = document.getElementById('blockly-toolbox');
                if (!blocklyContainer || !toolboxEl) return;

                blocklyWorkspace = Blockly.inject(blocklyContainer, {
                    toolbox: toolboxEl,
                    scrollbars: true,
                    trashcan: true,
                    renderer: 'zelos',
                    grid: {
                        spacing: 20,
                        length: 3,
                        colour: 'rgba(255, 255, 255, 0.08)',
                        snap: true
                    },
                    zoom: {
                        controls: true,
                        wheel: true,
                        startScale: 0.85,
                        maxScale: 2.0,
                        minScale: 0.4,
                        scaleSpeed: 1.1
                    },
                    theme: (window.Blockly && Blockly.Themes && Blockly.Themes.Dark) ? Blockly.Themes.Dark : undefined
                });

                blocklyWorkspace.addChangeListener((event) => {
                    if (event.isUiEvent) return;
                    updateBlocklyCodePreview();
                });

                isBlocklyInitialized = true;
                loadBlocklyPreset('pick_and_place');
            } catch (e) {
                console.error("Lỗi khởi tạo Blockly:", e);
            }
        }

        function toggleBlocklyCodeDrawer() {
            isCodeDrawerOpen = !isCodeDrawerOpen;
            const container = document.getElementById('blockly-code-container');
            const arrow = document.getElementById('drawer-arrow');
            if (container) container.style.display = isCodeDrawerOpen ? 'block' : 'none';
            if (arrow) arrow.innerText = isCodeDrawerOpen ? '▲' : '▼';
            if (isCodeDrawerOpen) updateBlocklyCodePreview();
        }

        function switchBlocklyCodeLang(lang) {
            currentCodeLang = lang;
            const btnPy = document.getElementById('btn-code-py');
            const btnJs = document.getElementById('btn-code-js');
            if (btnPy) btnPy.classList.toggle('active', lang === 'python');
            if (btnJs) btnJs.classList.toggle('active', lang === 'javascript');
            updateBlocklyCodePreview();
        }

        function updateBlocklyCodePreview() {
            if (!blocklyWorkspace || !isCodeDrawerOpen) return;
            const pre = document.getElementById('blockly-code-content');
            if (!pre) return;

            try {
                if (currentCodeLang === 'python') {
                    const pyGen = (window.python && window.python.pythonGenerator) || (window.Blockly && Blockly.Python);
                    if (pyGen) {
                        const pyBody = pyGen.workspaceToCode(blocklyWorkspace);
                        pre.innerText = `# Mã Python sinh ra từ các khối kéo thả\nimport time\nfrom dobot_api import Dobot\n\ndobot = Dobot()\ndobot.connect()\n\n${pyBody || '# Chưa có khối nào trên bàn lập trình'}\n\ndobot.disconnect()\n`;
                    } else {
                        pre.innerText = '# Trình sinh mã Python đang sẵn sàng...';
                    }
                } else {
                    const jsGen = (window.javascript && window.javascript.javascriptGenerator) || (window.Blockly && Blockly.JavaScript);
                    if (jsGen) {
                        const jsBody = jsGen.workspaceToCode(blocklyWorkspace);
                        pre.innerText = `// Mã JavaScript Async sinh ra từ các khối kéo thả\n(async () => {\n${jsBody || '  // Chưa có khối nào trên bàn lập trình\n'}})();\n`;
                    } else {
                        pre.innerText = '// Trình sinh mã JavaScript đang sẵn sàng...';
                    }
                }
            } catch (e) {
                pre.innerText = `// Lỗi sinh mã: ${e.message}`;
            }
        }

        function copyBlocklyCodeToClipboard() {
            const pre = document.getElementById('blockly-code-content');
            if (!pre || !pre.innerText || pre.innerText.startsWith('# Chưa có') || pre.innerText.startsWith('// Chưa có')) {
                showToast('⚠️ Chưa có mã nguồn để sao chép!');
                return;
            }
            const text = pre.innerText;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    showToast('📋 Đã sao chép mã nguồn vào bộ nhớ tạm!');
                }).catch(() => {
                    fallbackCopyText(text);
                });
            } else {
                fallbackCopyText(text);
            }
        }

        function fallbackCopyText(text) {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            try {
                document.execCommand('copy');
                showToast('📋 Đã sao chép mã nguồn vào bộ nhớ tạm!');
            } catch (e) {
                showToast('⚠️ Không thể sao chép tự động!');
            }
            document.body.removeChild(ta);
        }

        function waitForBlocklyRobotToReach(tx, ty, tzFlange, timeoutMs=7000) {
            return new Promise(resolve => {
                const startTime = Date.now();
                const timer = setInterval(() => {
                    if (!isBlocklyRunning) {
                        clearInterval(timer);
                        resolve();
                        return;
                    }
                    if (isBlocklyPaused) return;

                    if (!isSimulationMode()) {
                        const cur = lastKnownRobotPose;
                        if (cur) {
                            const dx = cur.x - tx;
                            const dy = cur.y - ty;
                            const dz = cur.z - tzFlange;
                            const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
                            if (dist < 3.5) {
                                clearInterval(timer);
                                resolve();
                                return;
                            }
                        }
                    } else {
                        if (Date.now() - startTime >= 400) {
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

        function waitForBlocklyJointsToReach(j1, j2, j3, j4, timeoutMs=7000) {
            return new Promise(resolve => {
                const startTime = Date.now();
                const timer = setInterval(() => {
                    if (!isBlocklyRunning) {
                        clearInterval(timer);
                        resolve();
                        return;
                    }
                    if (isBlocklyPaused) return;

                    if (!isSimulationMode()) {
                        const cur = lastRawJoints;
                        if (cur) {
                            const dj1 = Math.abs(cur.j1 - j1);
                            const dj2 = Math.abs(cur.j2 - j2);
                            const dj3 = Math.abs(cur.j3 - j3);
                            const dj4 = Math.abs(cur.j4 - j4);
                            if (dj1 < 2.5 && dj2 < 2.5 && dj3 < 2.5 && dj4 < 2.5) {
                                clearInterval(timer);
                                resolve();
                                return;
                            }
                        }
                    } else {
                        if (Date.now() - startTime >= 400) {
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

        const dobotApi = {
            async checkExecution(blockId) {
                if (!isBlocklyRunning) throw new Error('BLOCKLY_STOPPED');
                while (isBlocklyPaused && isBlocklyRunning) {
                    await sleepMs(100);
                }
                if (!isBlocklyRunning) throw new Error('BLOCKLY_STOPPED');
                if (blockId && blocklyWorkspace) {
                    blocklyWorkspace.highlightBlock(blockId);
                }
            },

            async moveXYZ(x, y, z, r, mode, blockId) {
                await this.checkExecution(blockId);
                const isSim = isSimulationMode();
                showBlocklyStatus(`${isSim ? '🎮 [Mô phỏng 3D]' : '🦾'} Di chuyển X=${x}, Y=${y}, Z=${z}, R=${r} (${mode === 'safe' ? 'Nhấc an toàn' : 'Bay thẳng'})...`, isSim ? "#38bdf8" : "#4ade80");

                const rHoriz = Math.sqrt(x * x + y * y);
                const rMin = cachedSafetyLimits?.r_min ?? 140.0;
                const rMax = cachedSafetyLimits?.r_max ?? 330.0;
                const zMinLimit = isRailModeActive ? (cachedSafetyLimits?.z_min_rail ?? -180.0) : (cachedSafetyLimits?.z_min_standalone ?? -65.0);
                const zMaxLimit = cachedSafetyLimits?.z_max ?? 165.0;
                const zFlange = z + toolOffset;
                if (rHoriz < rMin || rHoriz > rMax || zFlange < zMinLimit || zFlange > zMaxLimit) {
                    throw new Error(`Tọa độ (X=${x}, Y=${y}, Z_đầu_hút=${z}) ngoài vùng an toàn!`);
                }
                if (isSim) {
                    const ok = await animateRobotCartesian(x, y, z, r, mode, mode === 'safe' ? 550 : 400, () => isBlocklyRunning, () => isBlocklyPaused);
                    if (!ok && !isBlocklyRunning) throw new Error('BLOCKLY_STOPPED');
                } else {
                    if (mode === 'safe') {
                        sendAction('safe_jump', { x: x, y: y, z: zFlange, r: r });
                    } else {
                        sendAction('move_xyz', { x: x, y: y, z: zFlange, r: r, mode: 1 });
                    }
                    await waitForBlocklyRobotToReach(x, y, zFlange, 8000);
                }
                await this.checkExecution(blockId);
            },

            async moveJoints(j1, j2, j3, j4, blockId) {
                await this.checkExecution(blockId);
                const isSim = isSimulationMode();
                showBlocklyStatus(`${isSim ? '🎮 [Mô phỏng 3D]' : '🦾'} Quay khớp J1=${j1}°, J2=${j2}°, J3=${j3}°, J4=${j4}°...`, "#818cf8");

                if (isSim) {
                    const ok = await animateRobotJoints(j1, j2, j3, j4, 450, () => isBlocklyRunning, () => isBlocklyPaused);
                    if (!ok && !isBlocklyRunning) throw new Error('BLOCKLY_STOPPED');
                } else {
                    sendAction('move_joint', { j1: j1, j2: j2, j3: j3, j4: j4, mode: 4 });
                    await waitForBlocklyJointsToReach(j1, j2, j3, j4, 8000);
                }
                await this.checkExecution(blockId);
            },

            async moveRelative(dx, dy, dz, dr, blockId) {
                await this.checkExecution(blockId);
                const isSim = isSimulationMode();
                showBlocklyStatus(`${isSim ? '🎮 [Mô phỏng 3D]' : '🦾'} Di chuyển tương đối dX=${dx}, dY=${dy}, dZ=${dz}...`, "#2dd4bf");

                const curX = currentX || (lastKnownRobotPose && lastKnownRobotPose.x) || 250;
                const curY = currentY || (lastKnownRobotPose && lastKnownRobotPose.y) || 0;
                const curZ = currentZ !== undefined ? currentZ : ((lastKnownRobotPose && lastKnownRobotPose.zTcp !== undefined) ? lastKnownRobotPose.zTcp : 30);
                const curR = currentR || (lastKnownRobotPose && lastKnownRobotPose.r) || 0;

                await this.moveXYZ(curX + dx, curY + dy, curZ + dz, curR + dr, 'direct', blockId);
            },

            async suction(enable, blockId) {
                await this.checkExecution(blockId);
                showBlocklyStatus(`💨 Giác hút: ${enable ? 'BẬT (Hút)' : 'TẮT (Nhả)'}...`, "#4ade80");
                setSuctionState(enable);
                await sleepMs(350);
                await this.checkExecution(blockId);
            },

            async wait(sec, blockId) {
                await this.checkExecution(blockId);
                showBlocklyStatus(`⏱️ Đang dừng chờ ${sec}s...`, "#facc15");
                const totalMs = Math.max(0, sec * 1000);
                const steps = Math.ceil(totalMs / 100);
                for (let i = 0; i < steps; i++) {
                    await this.checkExecution(blockId);
                    await sleepMs(100);
                }
                await this.checkExecution(blockId);
            },

            async home(blockId) {
                await this.checkExecution(blockId);
                const isSim = isSimulationMode();
                showBlocklyStatus(`${isSim ? '🎮 [Mô phỏng 3D]' : '🏠'} Về vị trí Home an toàn...`, "#fb923c");
                if (isSim) {
                    const ok = await animateRobotCartesian(250, 0, 50, 0, 'safe', 550, () => isBlocklyRunning, () => isBlocklyPaused);
                    if (!ok && !isBlocklyRunning) throw new Error('BLOCKLY_STOPPED');
                } else {
                    sendAction('home');
                    await sleepMs(4000);
                }
                await this.checkExecution(blockId);
            }
        };

        async function runBlocklyCode() {
            if (!blocklyWorkspace) return;

            if (isBlocklyRunning) {
                if (isBlocklyPaused) {
                    isBlocklyPaused = false;
                    const btnPause = document.getElementById('btn-blockly-pause');
                    if (btnPause) btnPause.innerText = "⏸️ Tạm Dừng";
                    showBlocklyStatus("Đang tiếp tục chạy...", "#4ade80");
                }
                return;
            }

            const jsGen = (window.javascript && window.javascript.javascriptGenerator) || (window.Blockly && Blockly.JavaScript);
            if (!jsGen) {
                showToast("⚠️ Chưa sẵn sàng trình sinh mã JavaScript!");
                return;
            }

            const code = jsGen.workspaceToCode(blocklyWorkspace);
            if (!code || code.trim() === '') {
                showToast("⚠️ Bàn làm việc đang trống! Hãy kéo thả khối hoặc chọn mẫu.");
                return;
            }

            isBlocklyRunning = true;
            isBlocklyPaused = false;
            document.getElementById('btn-blockly-run').disabled = true;
            document.getElementById('btn-blockly-pause').disabled = false;
            document.getElementById('btn-blockly-stop').disabled = false;
            if (isSimulationMode()) {
                showBlocklyStatus("▶️ [Chế độ Mô Phỏng 3D] Đang chạy chương trình...", "#38bdf8");
            } else {
                showBlocklyStatus("▶️ Đang khởi chạy chương trình trên Robot thật...", "#4ade80");
            }

            try {
                const runnerFn = new Function('dobotApi', 'sleepMs', `
                    return (async () => {
                        ${code}
                    })();
                `);
                await runnerFn(dobotApi, sleepMs);
                showBlocklyStatus("✅ Hoàn thành chương trình thành công!", "#4ade80");
                showToast("✅ Đã hoàn thành chương trình khối!");
            } catch (err) {
                if (err.message === 'BLOCKLY_STOPPED') {
                    showBlocklyStatus("⏹️ Đã dừng chương trình.", "#cbd5e1");
                    showToast("⏹️ Đã dừng chương trình!");
                } else {
                    console.error("Lỗi thực thi Blockly:", err);
                    showBlocklyStatus("❌ " + err.message, "#ff6b6b");
                    showToast("❌ Lỗi: " + err.message);
                }
            } finally {
                stopBlocklyCode();
            }
        }

        function pauseBlocklyCode() {
            if (!isBlocklyRunning) return;
            isBlocklyPaused = !isBlocklyPaused;
            const btn = document.getElementById('btn-blockly-pause');
            if (isBlocklyPaused) {
                if (btn) btn.innerText = "▶️ Tiếp Tục";
                showBlocklyStatus("⏸️ Chương trình đang tạm dừng", "#facc15");
            } else {
                if (btn) btn.innerText = "⏸️ Tạm Dừng";
                showBlocklyStatus("Đang tiếp tục chạy...", "#4ade80");
            }
        }

        function stopBlocklyCode() {
            isBlocklyRunning = false;
            isBlocklyPaused = false;
            if (blocklyWorkspace) {
                blocklyWorkspace.highlightBlock(null);
            }
            const btnRun = document.getElementById('btn-blockly-run');
            const btnPause = document.getElementById('btn-blockly-pause');
            const btnStop = document.getElementById('btn-blockly-stop');

            if (btnRun) btnRun.disabled = false;
            if (btnPause) {
                btnPause.disabled = true;
                btnPause.innerText = "⏸️ Tạm Dừng";
            }
            if (btnStop) btnStop.disabled = true;
        }

        function clearBlocklyWorkspace() {
            if (!blocklyWorkspace) return;
            if (confirm("Bạn có chắc chắn muốn xóa toàn bộ các khối trên bàn làm việc?")) {
                if (isBlocklyRunning) stopBlocklyCode();
                blocklyWorkspace.clear();
                updateBlocklyCodePreview();
                showToast("🗑️ Đã xóa sạch bàn làm việc!");
            }
        }

        function addCurrentPoseToBlockly() {
            if (!blocklyWorkspace) {
                initBlocklyWorkspaceIfNeeded();
            }
            if (!blocklyWorkspace) return;
            const curX = Math.round((currentX || lastKnownRobotPose.x || 240) * 10) / 10;
            const curY = Math.round((currentY || lastKnownRobotPose.y || 0) * 10) / 10;
            const curZ = Math.round((currentZ || lastKnownRobotPose.zTcp || 30) * 10) / 10;
            const curR = Math.round((currentR || lastKnownRobotPose.r || 0) * 10) / 10;

            const block = blocklyWorkspace.newBlock('dobot_move_xyz');
            block.setFieldValue(curX, 'X');
            block.setFieldValue(curY, 'Y');
            block.setFieldValue(curZ, 'Z');
            block.setFieldValue(curR, 'R');
            block.setFieldValue('safe', 'MODE');
            block.initSvg();
            block.render();
            blocklyWorkspace.centerOnBlock(block.id);
            showToast(`📍 Đã chèn khối vị trí hiện tại: (${curX}, ${curY}, ${curZ})`);
        }

        function exportBlocklyXML() {
            if (!blocklyWorkspace || typeof Blockly === 'undefined') return;
            const xmlDom = Blockly.Xml.workspaceToDom(blocklyWorkspace);
            const xmlText = Blockly.Xml.domToPrettyText(xmlDom);
            const blob = new Blob([xmlText], { type: 'text/xml;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `dobot_blockly_${new Date().toISOString().slice(0,10)}.xml`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showToast('💾 Đã xuất file Blockly XML!');
        }

        function importBlocklyXML(event) {
            const file = event.target.files[0];
            if (!file || !blocklyWorkspace || typeof Blockly === 'undefined') return;
            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const xmlText = e.target.result;
                    const xmlDom = parseXmlText(xmlText);
                    blocklyWorkspace.clear();
                    Blockly.Xml.domToWorkspace(xmlDom, blocklyWorkspace);
                    updateBlocklyCodePreview();
                    showToast('📂 Đã nạp chương trình XML thành công!');
                } catch (err) {
                    alert('❌ Lỗi khi đọc file XML: ' + err.message);
                }
            };
            reader.readAsText(file);
            event.target.value = '';
        }

        const BLOCKLY_PRESETS = {
            pick_and_place: `<xml xmlns="https://developers.google.com/blockly/xml">
  <block type="controls_repeat_ext" x="20" y="20">
    <value name="TIMES"><shadow type="math_number"><field name="NUM">3</field></shadow></value>
    <statement name="DO">
      <block type="dobot_move_xyz">
        <field name="X">220</field><field name="Y">120</field><field name="Z">20</field><field name="R">0</field><field name="MODE">safe</field>
        <next>
          <block type="dobot_suction">
            <field name="STATE">ON</field>
            <next>
              <block type="dobot_wait">
                <field name="TIME">0.5</field>
                <next>
                  <block type="dobot_move_xyz">
                    <field name="X">220</field><field name="Y">120</field><field name="Z">70</field><field name="R">0</field><field name="MODE">direct</field>
                    <next>
                      <block type="dobot_move_xyz">
                        <field name="X">220</field><field name="Y">-120</field><field name="Z">70</field><field name="R">0</field><field name="MODE">safe</field>
                        <next>
                          <block type="dobot_move_xyz">
                            <field name="X">220</field><field name="Y">-120</field><field name="Z">20</field><field name="R">0</field><field name="MODE">direct</field>
                            <next>
                              <block type="dobot_suction">
                                <field name="STATE">OFF</field>
                                <next>
                                  <block type="dobot_wait">
                                    <field name="TIME">0.5</field>
                                    <next>
                                      <block type="dobot_move_xyz">
                                        <field name="X">220</field><field name="Y">-120</field><field name="Z">70</field><field name="R">0</field><field name="MODE">direct</field>
                                      </block>
                                    </next>
                                  </block>
                                </next>
                              </block>
                            </next>
                          </block>
                        </next>
                      </block>
                    </next>
                  </block>
                </next>
              </block>
            </next>
          </block>
        </next>
      </block>
    </statement>
    <next>
      <block type="dobot_move_xyz">
        <field name="X">240</field><field name="Y">0</field><field name="Z">50</field><field name="R">0</field><field name="MODE">safe</field>
      </block>
    </next>
  </block>
</xml>`,

            square_patrol: `<xml xmlns="https://developers.google.com/blockly/xml">
  <block type="controls_repeat_ext" x="20" y="20">
    <value name="TIMES"><shadow type="math_number"><field name="NUM">2</field></shadow></value>
    <statement name="DO">
      <block type="dobot_move_xyz">
        <field name="X">200</field><field name="Y">120</field><field name="Z">40</field><field name="R">0</field><field name="MODE">safe</field>
        <next>
          <block type="dobot_wait">
            <field name="TIME">0.4</field>
            <next>
              <block type="dobot_move_xyz">
                <field name="X">270</field><field name="Y">120</field><field name="Z">40</field><field name="R">0</field><field name="MODE">direct</field>
                <next>
                  <block type="dobot_wait">
                    <field name="TIME">0.4</field>
                    <next>
                      <block type="dobot_move_xyz">
                        <field name="X">270</field><field name="Y">-120</field><field name="Z">40</field><field name="R">0</field><field name="MODE">direct</field>
                        <next>
                          <block type="dobot_wait">
                            <field name="TIME">0.4</field>
                            <next>
                              <block type="dobot_move_xyz">
                                <field name="X">200</field><field name="Y">-120</field><field name="Z">40</field><field name="R">0</field><field name="MODE">direct</field>
                                <next>
                                  <block type="dobot_wait"><field name="TIME">0.4</field></block>
                                </next>
                              </block>
                            </next>
                          </block>
                        </next>
                      </block>
                    </next>
                  </block>
                </next>
              </block>
            </next>
          </block>
        </next>
      </block>
    </statement>
    <next>
      <block type="dobot_move_xyz">
        <field name="X">240</field><field name="Y">0</field><field name="Z">50</field><field name="R">0</field><field name="MODE">safe</field>
      </block>
    </next>
  </block>
</xml>`,

            joint_wave: `<xml xmlns="https://developers.google.com/blockly/xml">
  <block type="controls_repeat_ext" x="20" y="20">
    <value name="TIMES"><shadow type="math_number"><field name="NUM">2</field></shadow></value>
    <statement name="DO">
      <block type="dobot_move_joint">
        <field name="J1">30</field><field name="J2">20</field><field name="J3">40</field><field name="J4">0</field>
        <next>
          <block type="dobot_wait">
            <field name="TIME">0.5</field>
            <next>
              <block type="dobot_move_joint">
                <field name="J1">-30</field><field name="J2">30</field><field name="J3">30</field><field name="J4">0</field>
                <next>
                  <block type="dobot_wait"><field name="TIME">0.5</field></block>
                </next>
              </block>
            </next>
          </block>
        </next>
      </block>
    </statement>
    <next>
      <block type="dobot_move_joint">
        <field name="J1">0</field><field name="J2">20</field><field name="J3">40</field><field name="J4">0</field>
      </block>
    </next>
  </block>
</xml>`
        };

        function loadBlocklyPreset(presetKey) {
            if (!blocklyWorkspace || typeof Blockly === 'undefined') return;
            if (isBlocklyRunning) stopBlocklyCode();
            const xmlStr = BLOCKLY_PRESETS[presetKey];
            if (!xmlStr) return;
            try {
                blocklyWorkspace.clear();
                const xmlDom = parseXmlText(xmlStr);
                Blockly.Xml.domToWorkspace(xmlDom, blocklyWorkspace);
                updateBlocklyCodePreview();
                showBlocklyStatus("⚡ Đã nạp mẫu: " + presetKey, "#38bdf8");
            } catch (err) {
                console.error("Lỗi nạp preset Blockly:", err);
            }
        }

        window.addEventListener('resize', () => {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
            if (blocklyWorkspace && typeof Blockly !== 'undefined') {
                Blockly.svgResize(blocklyWorkspace);
            }
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

        

// --- 2. THU THẬP DỮ LIỆU & CAMERA ---
        function handleStreamError(elem) {
            // Legacy no-op: WebSocket tự retry trong startVideoStream.onclose
        }

        async function fetchCameraDevices(forceRefresh = false) {
            try {
                let res;
                if (forceRefresh) {
                    showToast("🔄 Đang quét lại các cổng Camera...");
                    res = await fetch('/api/camera', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ refresh: true })
                    });
                } else {
                    res = await fetch('/api/camera');
                }
                const data = await res.json();
                const selTab2 = document.getElementById('sel-cam-tab2');
                const selTab4 = document.getElementById('sel-cam-tab4');
                const selTab5 = document.getElementById('sel-cam-tab5');
                const warnTab2 = document.getElementById('warn-no-cam-tab2');
                const warnTab4 = document.getElementById('warn-no-cam-tab4');
                const warnTab5 = document.getElementById('warn-no-cam-tab5');
                const btnCapture = document.getElementById('btn-launch-capture');
                const btnSort = document.getElementById('btn-launch-sort');
                const btnCalib = document.getElementById('btn-launch-calib');

                const cams = (data.status === 'ok' && Array.isArray(data.available_cameras)) ? data.available_cameras : [];

                if (cams.length === 0) {
                    const noCamHtml = `<option value="">⚠️ Không phát hiện camera nào</option>`;
                    if (selTab2) selTab2.innerHTML = noCamHtml;
                    if (selTab4) selTab4.innerHTML = noCamHtml;
                    if (selTab5) selTab5.innerHTML = noCamHtml;

                    if (warnTab2) warnTab2.style.display = 'block';
                    if (warnTab4) warnTab4.style.display = 'block';
                    if (warnTab5) warnTab5.style.display = 'block';

                    if (btnCapture) {
                        btnCapture.disabled = true;
                        btnCapture.style.opacity = '0.45';
                        btnCapture.style.cursor = 'not-allowed';
                        btnCapture.title = 'Không thể mở vì máy tính chưa nhận diện camera!';
                    }
                    if (btnSort) {
                        btnSort.disabled = true;
                        btnSort.style.opacity = '0.45';
                        btnSort.style.cursor = 'not-allowed';
                        btnSort.title = 'Không thể mở vì máy tính chưa nhận diện camera!';
                    }
                    if (btnCalib) {
                        btnCalib.disabled = true;
                        btnCalib.style.opacity = '0.45';
                        btnCalib.style.cursor = 'not-allowed';
                        btnCalib.title = 'Không thể mở vì máy tính chưa nhận diện camera!';
                    }

                    if (forceRefresh) {
                        showToast("⚠️ Không tìm thấy camera nào đang kết nối!");
                    }
                } else {
                    const prevTab2Val = selTab2 ? selTab2.value : null;
                    const prevTab4Val = selTab4 ? selTab4.value : null;
                    const prevTab5Val = selTab5 ? selTab5.value : null;

                    const optionsHtml = cams.map((cam, idx) => 
                        `<option value="${cam.id}">${cam.name}</option>`
                    ).join('');

                    if (selTab2) {
                        selTab2.innerHTML = optionsHtml;
                        if (prevTab2Val !== null && cams.some(c => String(c.id) === String(prevTab2Val))) {
                            selTab2.value = prevTab2Val;
                        }
                    }
                    if (selTab4) {
                        selTab4.innerHTML = optionsHtml;
                        if (prevTab4Val !== null && cams.some(c => String(c.id) === String(prevTab4Val))) {
                            selTab4.value = prevTab4Val;
                        }
                    }
                    if (selTab5) {
                        selTab5.innerHTML = optionsHtml;
                        if (prevTab5Val !== null && cams.some(c => String(c.id) === String(prevTab5Val))) {
                            selTab5.value = prevTab5Val;
                        }
                    }

                    if (warnTab2) warnTab2.style.display = 'none';
                    if (warnTab4) warnTab4.style.display = 'none';
                    if (warnTab5) warnTab5.style.display = 'none';

                    if (btnCapture) {
                        btnCapture.disabled = false;
                        btnCapture.style.opacity = '1';
                        btnCapture.style.cursor = 'pointer';
                        btnCapture.title = '';
                    }
                    if (btnSort) {
                        btnSort.disabled = false;
                        btnSort.style.opacity = '1';
                        btnSort.style.cursor = 'pointer';
                        btnSort.title = '';
                    }
                    if (btnCalib) {
                        btnCalib.disabled = false;
                        btnCalib.style.opacity = '1';
                        btnCalib.style.cursor = 'pointer';
                        btnCalib.title = '';
                    }

                    if (forceRefresh) {
                        showToast(`✅ Đã tìm thấy ${cams.length} camera khả dụng!`);
                    }
                }
            } catch (err) {
                console.warn("fetchCameraDevices error:", err);
            }
        }

        async function fetchCalibInfo(showFeedback = false) {
            try {
                if (showFeedback) showToast("🔄 Đang nạp thông số Homography...");
                const res = await fetch('/api/calib/info');
                const data = await res.json();
                const statusEl = document.getElementById('txt-calib-status');
                const timeEl = document.getElementById('txt-calib-time');
                const tableBody = document.getElementById('calib-points-table-body');
                const matrixGrid = document.getElementById('calib-matrix-grid');

                if (data.status === 'ok' && data.calibrated && data.data) {
                    const cdata = data.data;
                    if (statusEl) {
                        statusEl.innerText = `✅ Đã có ma trận Homography (Sai số: ${cdata.mean_error_mm || 0} mm)`;
                        statusEl.style.color = '#4ade80';
                    }
                    if (timeEl) timeEl.innerText = cdata.created_at || 'Không rõ';

                    if (tableBody && Array.isArray(cdata.calibration_points)) {
                        tableBody.innerHTML = cdata.calibration_points.map(pt => `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <td style="padding: 8px 12px; font-weight: bold; color: #38bdf8;">Điểm ${pt.point_id}</td>
                                <td style="padding: 8px 12px; font-family: monospace; color: #cbd5e1;">(${pt.pixel_u}, ${pt.pixel_v})</td>
                                <td style="padding: 8px 12px; font-family: monospace; color: #4ade80;">X=${pt.dobot_x}, Y=${pt.dobot_y}</td>
                            </tr>
                        `).join('');
                    }

                    if (matrixGrid && Array.isArray(cdata.homography_matrix)) {
                        matrixGrid.innerHTML = cdata.homography_matrix.flat().map(val => `
                            <div style="background: rgba(255,255,255,0.03); padding: 6px 4px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.05);">
                                ${typeof val === 'number' ? val.toFixed(4) : val}
                            </div>
                        `).join('');
                    }

                    if (showFeedback) showToast("✅ Đã cập nhật thông số Homography!");
                } else {
                    if (statusEl) {
                        statusEl.innerText = '⚠️ Chưa thực hiện hiệu chuẩn (homography_dobot.json chưa có)';
                        statusEl.style.color = '#facc15';
                    }
                    if (timeEl) timeEl.innerText = '--';
                    if (tableBody) {
                        tableBody.innerHTML = '<tr><td colspan="3" style="padding: 14px; text-align: center; color: #94a3b8;">Chưa có dữ liệu 4 điểm mốc. Hãy nhấn "Mở cửa sổ hiệu chuẩn" bên trái để thực hiện.</td></tr>';
                    }
                    if (matrixGrid) {
                        matrixGrid.innerHTML = '<div style="grid-column: span 3; color: #64748b; padding: 10px;">Chưa có ma trận</div>';
                    }
                }
            } catch(e) {
                console.warn("fetchCalibInfo error:", e);
            }
        }

        async function changeCameraDevice(camId) {
            try {
                showToast(`🔄 Đang chuyển sang Camera ID: ${camId}...`);
                const res = await fetch('/api/camera', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cam_id: parseInt(camId) })
                });
                const data = await res.json();
                if (data.status === 'ok' && data.success) {
                    showToast(`✅ Đã chuyển sang Camera ID ${camId}`);
                    // Khởi động lại stream cho tab đang active
                    if (currentStudioTab === 'data') {
                        startVideoStream('img-data-stream', 'raw');
                    } else if (currentStudioTab === 'sort') {
                        startVideoStream('img-sort-stream', 'yolo');
                    }
                    fetchCameraDevices(false);
                } else {
                    showToast(`❌ Không thể mở Camera ID ${camId}`);
                }
            } catch (err) {
                showToast(`❌ Lỗi kết nối camera: ${err.message}`);
            }
        }

        async function fetchDatasetStats() {
            try {
                const res = await fetch('/api/dataset/stats');
                const data = await res.json();
                if (data && (data.status === 'ok' || data.classes)) {
                    const counts = data.counts || data.classes || {};
                    const classesList = Array.isArray(data.classes) ? data.classes : Object.keys(counts);
                    renderClassPills(classesList, counts);
                    renderStatsList(counts, data.total_images || 0);
                    const totalBadge = document.getElementById('badge-total-images');
                    if (totalBadge) totalBadge.innerText = `Tổng: ${data.total_images || 0} ảnh`;
                    fetchRecentGallery();
                }
            } catch (err) {
                console.warn("fetchDatasetStats error:", err);
            }
        }

        function renderClassPills(classes, counts) {
            const container = document.getElementById('class-pills-container');
            if (!container) return;
            const classArray = Array.isArray(classes) ? classes : Object.keys(classes || {});
            knownClasses = classArray.length > 0 ? classArray : knownClasses;
            if (!knownClasses.includes(selectedDatasetClass) && knownClasses.length > 0) {
                selectedDatasetClass = knownClasses[0];
            }

            container.innerHTML = knownClasses.map(cls => {
                const active = cls === selectedDatasetClass ? 'active' : '';
                const cnt = counts[cls] || 0;
                return `
                    <button class="class-pill ${active}" onclick="selectDatasetClass('${cls}')">
                        <span class="class-pill-dot" style="background:${getClassColor(cls)}"></span>
                        <span style="font-weight:600;">${cls}</span>
                        <span class="class-pill-count">${cnt}</span>
                    </button>
                `;
            }).join('');
        }

        function selectDatasetClass(cls) {
            selectedDatasetClass = cls;
            document.querySelectorAll('.class-pill').forEach(pill => {
                pill.classList.toggle('active', pill.innerText.includes(cls));
            });
            const lblClass = document.getElementById('txt-current-capture-class');
            const lblFolder = document.getElementById('txt-current-capture-folder');
            if (lblClass) lblClass.innerText = cls;
            if (lblFolder) lblFolder.innerText = cls;
            showToast(`🏷️ Đã chọn nhãn: ${cls}`);
        }

        function getClassColor(cls) {
            if (cls.includes('red')) return '#f87171';
            if (cls.includes('green')) return '#4ade80';
            if (cls.includes('blue')) return '#60a5fa';
            if (cls.includes('yellow')) return '#facc15';
            if (cls.includes('black')) return '#94a3b8';
            if (cls.includes('white')) return '#f8fafc';
            return '#38bdf8';
        }

        function renderStatsList(counts, total) {
            const container = document.getElementById('stats-list-container');
            if (!container) return;
            const targetPerClass = 50;
            container.innerHTML = Object.entries(counts).map(([cls, cnt]) => {
                const pct = Math.min(100, Math.round((cnt / targetPerClass) * 100));
                const col = getClassColor(cls);
                return `
                    <div class="stats-item">
                        <div class="stats-item-top">
                            <span style="display:flex; align-items:center; gap:6px;">
                                <span class="class-pill-dot" style="background:${col}"></span>
                                <b>${cls}</b>
                            </span>
                            <span style="color:#94a3b8;">${cnt} / ${targetPerClass} ảnh (${pct}%)</span>
                        </div>
                        <div class="stats-bar-track">
                            <div class="stats-bar-fill" style="width:${pct}%; background:${col};"></div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        async function handleAddNewClass() {
            const inp = document.getElementById('inp-new-class');
            const val = inp.value.trim().toLowerCase().replace(/\s+/g, '_');
            if (!val) {
                showToast("⚠️ Vui lòng nhập tên nhãn (ví dụ: cube_purple)");
                return;
            }
            try {
                const res = await fetch('/api/dataset/add_class', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ class_name: val })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    selectedDatasetClass = val;
                    inp.value = '';
                    showToast(`✅ Đã thêm nhãn mới: ${val}`);
                    fetchDatasetStats();
                } else {
                    showToast(`❌ Lỗi: ${data.message}`);
                }
            } catch (err) {
                showToast(`❌ Lỗi thêm nhãn: ${err.message}`);
            }
        }

        function triggerFlashOverlay() {
            const flash = document.getElementById('data-flash-overlay');
            if (flash) {
                flash.style.opacity = '0.7';
                setTimeout(() => { flash.style.opacity = '0'; }, 180);
            }
        }

        async function triggerSingleCapture() {
            try {
                triggerFlashOverlay();
                const res = await fetch('/api/dataset/capture', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ class_name: selectedDatasetClass })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    showToast(`📸 Đã chụp: ${data.filename} (${selectedDatasetClass})`);
                    fetchDatasetStats();
                } else {
                    showToast(`❌ Lỗi chụp ảnh: ${data.message}`);
                }
            } catch (err) {
                showToast(`❌ Lỗi mạng khi chụp ảnh: ${err.message}`);
            }
        }

        function toggleContinuousRecording() {
            isRecordingDataset = !isRecordingDataset;
            const btn = document.getElementById('btn-toggle-record');
            if (isRecordingDataset) {
                btn.classList.add('recording');
                btn.innerHTML = '<span>⏹️</span> <span>DỪNG LƯU (R)</span>';
                showToast(`🔴 Bắt đầu lưu liên tục cho nhãn [${selectedDatasetClass}]!`);
                triggerSingleCapture();
                datasetRecordTimer = setInterval(() => {
                    triggerSingleCapture();
                }, 450);
            } else {
                btn.classList.remove('recording');
                btn.innerHTML = '<span>🔴</span> <span>LƯU LIÊN TỤC (R)</span>';
                if (datasetRecordTimer) {
                    clearInterval(datasetRecordTimer);
                    datasetRecordTimer = null;
                }
                showToast(`⏹️ Đã dừng lưu liên tục.`);
                fetchDatasetStats();
            }
        }

        async function fetchRecentGallery() {
            try {
                const res = await fetch('/api/dataset/recent');
                const data = await res.json();
                const container = document.getElementById('recent-gallery-container');
                if (container && data.status === 'ok') {
                    if (data.images.length === 0) {
                        container.innerHTML = '<div style="color:#64748b; font-size:12px; padding:10px;">Chưa có ảnh nào được chụp</div>';
                        return;
                    }
                    container.innerHTML = data.images.map(img => `
                        <div class="thumb-card" title="${img.filename}">
                            <img class="thumb-img" src="${img.url}" alt="${img.class_name}">
                            <div class="thumb-badge">${img.class_name}</div>
                            <button class="thumb-del-btn" onclick="handleDeleteCapture('${img.filename}')" title="Xóa ảnh này">✕</button>
                        </div>
                    `).join('');
                }
            } catch (err) {
                console.warn("fetchRecentGallery error:", err);
            }
        }

        async function handleDeleteCapture(filename) {
            if (!confirm(`Xóa ảnh ${filename}?`)) return;
            try {
                const res = await fetch('/api/dataset/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ filename: filename })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    showToast(`🗑️ Đã xóa: ${filename}`);
                    fetchDatasetStats();
                } else {
                    showToast(`❌ Lỗi xóa: ${data.message}`);
                }
            } catch (err) {
                showToast(`❌ Lỗi: ${err.message}`);
            }
        }

        // --- 3. HUẤN LUYỆN AI 1-CLICK (KAGGLE CLOUD GPU) ---
        let activeTrainType = 'cloud'; // Huấn luyện Cloud GPU qua Kaggle API

        // Kiểm tra và hiển thị trạng thái Kaggle API
        async function checkKaggleCreds() {
            try {
                const res = await fetch('/api/train/kaggle/creds');
                const data = await res.json();
                const statusTxt = document.getElementById('kaggle-status-text');
                const btnModal = document.getElementById('btn-open-kaggle-modal');
                if (statusTxt) {
                    if (data.configured) {
                        statusTxt.innerHTML = `☁️ Kaggle Cloud: <b>@${data.username}</b> <span style="color:#22c55e;">(Sẵn sàng 🟢)</span>`;
                        if (btnModal) btnModal.innerText = '⚙️ Đổi tài khoản';
                    } else {
                        statusTxt.innerHTML = `☁️ Kaggle Cloud: <span style="color:#f59e0b;">Chưa cài Token ⚠️</span>`;
                        if (btnModal) btnModal.innerText = '🔑 Cài đặt Token';
                    }
                }
                return data;
            } catch(e) {
                console.warn("checkKaggleCreds error:", e);
                return { configured: false };
            }
        }

        function openKaggleModal() {
            const m = document.getElementById('modal-kaggle-setup');
            if (m) m.style.display = 'flex';
        }

        function closeKaggleModal() {
            const m = document.getElementById('modal-kaggle-setup');
            if (m) m.style.display = 'none';
        }

        function handleKaggleFileSelect(event) {
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const json = JSON.parse(e.target.result);
                    if (json.username && json.key) {
                        document.getElementById('inp-kaggle-user').value = json.username;
                        document.getElementById('inp-kaggle-key').value = json.key;
                        showToast(`📄 Đã nạp thông tin tài khoản @${json.username} từ file!`);
                    } else {
                        showToast("❌ File kaggle.json không đúng định dạng!");
                    }
                } catch(err) {
                    showToast("❌ Không đọc được nội dung JSON!");
                }
            };
            reader.readAsText(file);
        }

        async function handleSaveKaggleCreds() {
            const user = document.getElementById('inp-kaggle-user').value.trim();
            const key = document.getElementById('inp-kaggle-key').value.trim();
            if (!user || !key) {
                alert("Vui lòng nhập đầy đủ Username và API Key!");
                return;
            }
            const btn = document.getElementById('btn-save-kaggle');
            if (btn) btn.innerText = 'Đang xác thực...';

            try {
                const res = await fetch('/api/train/kaggle/creds', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: user, key: key })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(`✅ ${data.message || 'Lưu tài khoản thành công!'}`);
                    closeKaggleModal();
                    checkKaggleCreds();
                } else {
                    alert(`Lỗi xác thực: ${data.error}`);
                }
            } catch(e) {
                alert(`Lỗi kết nối: ${e.message}`);
            } finally {
                if (btn) btn.innerText = 'Lưu & Xác Thực';
            }
        }

        async function fetchTrainStatus() {
            try {
                const endpoint = (activeTrainType === 'cloud') ? '/api/train/kaggle/status' : '/api/train/status';
                const res = await fetch(endpoint);
                const data = await res.json();
                updateTrainDashboard(data);
            } catch (err) {
                console.warn("fetchTrainStatus error:", err);
            }
        }

        async function handleStartTraining() {
            activeTrainType = 'local';
            const modelName = document.getElementById('sel-train-model').value;
            const epochs = parseInt(document.getElementById('rng-train-epochs').value);
            const batch = parseInt(document.getElementById('sel-train-batch').value);
            let rawOutput = (document.getElementById('inp-train-output-name')?.value || '').trim() || 'best_trained.onnx';
            let outputModel = rawOutput;
            if (outputModel.toLowerCase().endsWith('.onnx')) {
                outputModel = outputModel.slice(0, -5) + '.pt';
            } else if (!outputModel.toLowerCase().endsWith('.pt')) {
                outputModel += '.pt';
            }

            if (!confirm(`Bắt đầu huấn luyện mô hình ${modelName} với ${epochs} vòng lặp (Epochs) trên máy cục bộ? Sau khi hoàn thành hệ thống sẽ TỰ ĐỘNG CHUYỂN SANG ONNX: ${rawOutput}`)) return;

            try {
                const res = await fetch('/api/train/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_name: modelName, epochs: epochs, batch: batch, output_model_name: outputModel })
                });
                const data = await res.json();
                if (data.status === 'ok' || data.success) {
                    showToast(`🚀 Đã khởi chạy tiến trình huấn luyện (Tự xuất ONNX: ${rawOutput})!`);
                    startTrainPolling();
                    fetchTrainStatus();
                } else {
                    showToast(`❌ Không thể bắt đầu: ${data.message || data.error}`);
                }
            } catch (err) {
                showToast(`❌ Lỗi khởi chạy: ${err.message}`);
            }
        }

        async function handleStartCloudTraining() {
            const creds = await checkKaggleCreds();
            if (!creds || !creds.configured) {
                openKaggleModal();
                showToast("🔑 Vui lòng cài đặt API Key Kaggle trước khi train!");
                return;
            }

            const modelName = document.getElementById('sel-train-model').value;
            const epochs = parseInt(document.getElementById('rng-train-epochs').value);
            const batch = parseInt(document.getElementById('sel-train-batch').value);
            let rawOutput = (document.getElementById('inp-train-output-name')?.value || '').trim() || 'best_trained.onnx';
            let outputModel = rawOutput;
            if (outputModel.toLowerCase().endsWith('.onnx')) {
                outputModel = outputModel.slice(0, -5) + '.pt';
            } else if (!outputModel.toLowerCase().endsWith('.pt')) {
                outputModel += '.pt';
            }

            if (!confirm(`🚀 Gửi dữ liệu lên Cloud GPU (NVIDIA Tesla T4 của Kaggle) để huấn luyện ${epochs} Epochs? Sau khi tải về sẽ tự động chuyển sang ONNX: ${rawOutput}`)) return;

            try {
                activeTrainType = 'cloud';
                const res = await fetch('/api/train/kaggle/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_name: modelName, epochs: epochs, batch: batch, output_model_name: outputModel })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(`⚡ Đã khởi động phiên huấn luyện Cloud GPU (Lưu thành: ${outputModel})!`);
                    startTrainPolling();
                    fetchTrainStatus();
                } else {
                    if (data.need_setup) openKaggleModal();
                    showToast(`❌ Không thể bắt đầu: ${data.error || data.message}`);
                }
            } catch (err) {
                showToast(`❌ Lỗi gửi Cloud: ${err.message}`);
            }
        }

        async function handleStopTraining() {
            if (!confirm("Bạn có chắc chắn muốn hủy phiên huấn luyện hiện tại?")) return;
            try {
                const endpoint = (activeTrainType === 'cloud') ? '/api/train/kaggle/stop' : '/api/train/stop';
                const res = await fetch(endpoint, { method: 'POST' });
                const data = await res.json();
                showToast(`🛑 ${data.message || 'Đã gửi lệnh dừng'}`);
                fetchTrainStatus();
            } catch (err) {
                showToast(`❌ Lỗi hủy: ${err.message}`);
            }
        }

        async function handleExportColab() {
            showToast("📦 Đang chuẩn bị dataset và nén thành file .zip...");
            try {
                const res = await fetch('/api/train/export_colab', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'ok' || data.success) {
                    showToast(`🎉 Nén thành công (${data.size_mb || 0} MB)! Đang tải xuống ${data.zip_name || 'yolo_dataset.zip'}...`);
                    const dlUrl = data.download_url || '/api/train/download_zip';
                    const a = document.createElement('a');
                    a.href = dlUrl;
                    a.download = data.zip_name || 'yolo_dataset.zip';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                } else {
                    showToast(`❌ Lỗi nén Colab: ${data.message || data.error}`);
                }
            } catch (err) {
                showToast(`❌ Lỗi tải zip: ${err.message}`);
            }
        }

        function startTrainPolling() {
            if (!trainPollTimer) {
                trainPollTimer = setInterval(fetchTrainStatus, 1000);
            }
        }

        function stopTrainPolling() {
            if (trainPollTimer) {
                clearInterval(trainPollTimer);
                trainPollTimer = null;
            }
        }

        function updateTrainDashboard(data) {
            if (!data) return;
            const badge = document.getElementById('train-status-badge');
            const btnCloud = document.getElementById('btn-start-cloud-train');
            const btnStop = document.getElementById('btn-stop-train');
            const statusMsg = document.getElementById('txt-train-status-msg');
            const pctText = document.getElementById('txt-train-progress-pct');
            const fillBar = document.getElementById('bar-train-fill');
            const lossVal = document.getElementById('metric-loss');
            const mapVal = document.getElementById('metric-map');
            const precVal = document.getElementById('metric-precision');
            const recallVal = document.getElementById('metric-recall');
            const logBox = document.getElementById('train-log-box');

            const status = data.status || 'idle';
            if (badge) {
                if (status === 'queued') {
                    badge.className = 'sys-badge online';
                    badge.innerText = 'Đang xếp hàng GPU (Queued)...';
                } else if (status === 'uploading') {
                    badge.className = 'sys-badge online';
                    badge.innerText = 'Đang tải lên Cloud...';
                } else if (status === 'downloading') {
                    badge.className = 'sys-badge online';
                    badge.innerText = 'Đang tải model về...';
                } else if (status === 'running' || status === 'training' || status === 'preparing') {
                    badge.className = 'sys-badge online';
                    badge.innerText = (data.is_cloud ? '☁️ Cloud GPU: ' : '') + `Epoch ${data.current_epoch}/${data.total_epochs}`;
                } else if (status === 'completed') {
                    badge.className = 'sys-badge online';
                    badge.innerText = 'Hoàn thành 🎉';
                } else if (status === 'stopped') {
                    badge.className = 'sys-badge offline';
                    badge.innerText = 'Đã dừng 🛑';
                } else if (status === 'error') {
                    badge.className = 'sys-badge offline';
                    badge.innerText = 'Lỗi!';
                } else {
                    badge.className = 'sys-badge offline';
                    badge.innerText = 'Chưa chạy';
                }
            }

            const isRunning = (status === 'training' || status === 'preparing' || status === 'uploading' || status === 'queued' || status === 'running' || status === 'downloading');
            if (btnCloud) btnCloud.style.display = isRunning ? 'none' : 'flex';
            if (btnStop) btnStop.style.display = isRunning ? 'flex' : 'none';

            if (statusMsg) statusMsg.innerText = data.message || 'Sẵn sàng';
            const pct = data.progress_pct || 0;
            if (pctText) pctText.innerText = `${pct}%`;
            if (fillBar) fillBar.style.width = `${pct}%`;

            if (lossVal) lossVal.innerText = (data.current_loss > 0) ? data.current_loss.toFixed(4) : '--';
            if (mapVal) {
                const m = data.current_map50 ?? data.map50 ?? 0;
                mapVal.innerText = (m > 0) ? `${(m > 1 ? m : m * 100).toFixed(1)}%` : '--';
            }
            if (precVal) {
                const p = data.current_precision ?? data.precision ?? 0;
                precVal.innerText = (p > 0) ? `${(p > 1 ? p : p * 100).toFixed(1)}%` : '--';
            }
            if (recallVal) {
                const r = data.current_recall ?? data.recall ?? 0;
                recallVal.innerText = (r > 0) ? `${(r > 1 ? r : r * 100).toFixed(1)}%` : '--';
            }

            if (logBox && data.logs && data.logs.length > 0) {
                logBox.innerText = data.logs.join('\n');
                logBox.scrollTop = logBox.scrollHeight;
            }

            if (!isRunning) {
                stopTrainPolling();
                if (status === 'completed') {
                    fetchVisionModels();
                }
            } else {
                startTrainPolling();
            }
        }

        // --- 4. AI VISION & TỰ ĐỘNG PHÂN LOẠI (AUTO SORT) ---
        async function fetchVisionModels() {
            try {
                const res = await fetch('/api/vision/models');
                const data = await res.json();
                const sel = document.getElementById('sel-vision-model');
                if (sel && data.status === 'ok' && data.models) {
                    sel.innerHTML = data.models.map(m => 
                        `<option value="${m.name}" ${m.name === data.current_model ? 'selected' : ''}>${m.label} (${m.size_mb}MB)</option>`
                    ).join('');
                }
            } catch (err) {
                console.warn("fetchVisionModels error:", err);
            }
        }

        async function handleChangeVisionModel(modelName) {
            try {
                showToast(`Đang tải mô hình YOLO: ${modelName}...`);
                const res = await fetch('/api/vision/models', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model: modelName })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    showToast(`✅ Đã nạp mô hình: ${modelName}`);
                } else {
                    showToast(`❌ Lỗi nạp mô hình: ${data.message}`);
                }
            } catch (err) {
                showToast(`❌ Lỗi kết nối mô hình: ${err.message}`);
            }
        }

        async function handleToggleAutoSort(enable) {
            try {
                const res = await fetch('/api/vision/auto_sort', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enable: enable })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    showToast(enable ? "⚡ ĐÃ BẬT TỰ ĐỘNG PHÂN LOẠI! Dobot sẽ tự gắp các khối màu." : "⏹️ Đã tắt tự động phân loại.");
                } else {
                    showToast(`❌ Lỗi: ${data.message}`);
                    document.getElementById('chk-auto-sort').checked = !enable;
                }
            } catch (err) {
                showToast(`❌ Lỗi: ${err.message}`);
            }
        }

        async function fetchVisionStatus() {
            try {
                const res = await fetch('/api/vision/status');
                const data = await res.json();
                if (data.status === 'ok') {
                    updateVisionDashboard(data);
                }
            } catch (err) {
                console.warn("fetchVisionStatus error:", err);
            }
        }

        function updateVisionDashboard(data) {
            if (!data) return;
            const chkAuto = document.getElementById('chk-auto-sort');
            if (chkAuto && typeof data.auto_sort_enabled === 'boolean') {
                chkAuto.checked = data.auto_sort_enabled;
            }

            const countEl = document.getElementById('txt-detected-count');
            const listEl = document.getElementById('detected-cubes-list');
            const cubes = data.detected_cubes || [];

            if (countEl) countEl.innerText = cubes.length;

            if (listEl) {
                if (cubes.length === 0) {
                    listEl.innerHTML = '<div style="color:#64748b; font-size:12px; padding:10px; text-align:center;">Chưa phát hiện khối màu nào trên bàn</div>';
                    return;
                }
                listEl.innerHTML = cubes.map((cube, idx) => {
                    const col = getClassColor(cube.class_name);
                    const dx = (cube.dobot_x !== null && cube.dobot_x !== undefined) ? cube.dobot_x : (cube.dobot_coord ? cube.dobot_coord.x : null);
                    const dy = (cube.dobot_y !== null && cube.dobot_y !== undefined) ? cube.dobot_y : (cube.dobot_coord ? cube.dobot_coord.y : null);
                    const dobotCoord = (dx !== null && dy !== null) ? `Dobot: (${dx}, ${dy}) mm` : 'Chưa calib';
                    return `
                        <div style="background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:8px 10px; display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <div style="display:flex; align-items:center; gap:6px;">
                                    <span class="class-pill-dot" style="background:${col}"></span>
                                    <b style="font-size:12px; color:#f8fafc;">${cube.class_name}</b>
                                    <span style="font-size:11px; color:#4ade80;">${Math.round(cube.confidence * 100)}%</span>
                                </div>
                                <div style="font-size:11px; color:#94a3b8; font-family:monospace; margin-top:2px;">
                                    ${dobotCoord}
                                </div>
                            </div>
                            <button class="btn-sync-pose" style="padding:4px 8px; font-size:11px;" onclick="pickCubeDirectly(${dx}, ${dy}, '${cube.class_name}')">
                                🦾 Gắp ngay
                            </button>
                        </div>
                    `;
                }).join('');
            }
        }

        async function pickCubeDirectly(x, y, className) {
            if (x === null || y === null) {
                showToast("⚠️ Khối này chưa có tọa độ Dobot (Cần hiệu chuẩn camera trước)!");
                return;
            }
            if (!confirm(`Ra lệnh cho Dobot gắp ${className} tại tọa độ X=${x}, Y=${y}?`)) return;
            try {
                showToast(`🚀 Đang yêu cầu Dobot gắp ${className} tại (${x}, ${y})...`);
                const res = await fetch('/api/vision/pick', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ dobot_x: x, dobot_y: y, class_name: className })
                });
                const data = await res.json();
                if (data.status === 'ok' || data.success) {
                    showToast(`✅ Dobot bắt đầu chu trình gắp thả: ${data.message || 'Thành công'}`);
                } else {
                    showToast(`❌ Lỗi gắp: ${data.message || data.error || 'Thất bại'}`);
                }
            } catch (err) {
                showToast(`❌ Lỗi mạng: ${err.message}`);
            }
        }

        async function handleVideoClickToPick(event) {
            const img = document.getElementById('img-sort-stream');
            if (!img) return;

            const rect = img.getBoundingClientRect();
            const clickX = event.clientX - rect.left;
            const clickY = event.clientY - rect.top;

            const normX = (clickX / rect.width) * 640;
            const normY = (clickY / rect.height) * 480;

            showToast(`🎯 Nhấp vào pixel: (${normX.toFixed(0)}, ${normY.toFixed(0)}). Đang tính toán gắp...`);

            try {
                const res = await fetch('/api/vision/pick', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ x: normX, y: normY })
                });
                const data = await res.json();
                if (data.status === 'ok' || data.success) {
                    showToast(`🚀 Đã nhận diện khối & bắt đầu gắp: ${data.message || 'Thành công'}`);
                } else {
                    showToast(`⚠️ ${data.message || data.error || 'Không gắp được'}`);
                }
            } catch (err) {
                showToast(`❌ Lỗi: ${err.message}`);
            }
        }

        function startVisionPolling() {
            if (!visionPollTimer) {
                visionPollTimer = setInterval(fetchVisionStatus, 1500);
            }
        }

        function stopVisionPolling() {
            if (visionPollTimer) {
                clearInterval(visionPollTimer);
                visionPollTimer = null;
            }
        }

