// Resolve current user from URL param, localStorage, or backend session
let currentUserId = null;
let currentUsername = null;
let qrPollTimer = null;

async function initUser() {
    // 1. Check URL query param (?user_id=...)
    const urlParams = new URLSearchParams(window.location.search);
    const paramUid = urlParams.get('user_id');

    // 2. Check localStorage
    const storedUid = localStorage.getItem('mindmesh_user_id');
    const storedUserRaw = localStorage.getItem('mindmesh_user');
    let parsedUser = null;
    if (storedUserRaw) {
        try { parsedUser = JSON.parse(storedUserRaw); } catch (e) {}
    }

    currentUserId = paramUid || storedUid || (parsedUser && (parsedUser.user_id || parsedUser.id || parsedUser.username));
    currentUsername = localStorage.getItem('mindmesh_username') || (parsedUser && (parsedUser.username || parsedUser.user)) || currentUserId;

    // 3. Check backend session if not found
    if (!currentUserId) {
        try {
            const res = await fetch('/api/auth/me');
            if (res.ok) {
                const data = await res.json();
                if (data.authenticated && data.user) {
                    currentUserId = data.user.user_id || data.user.id || data.user.username;
                    currentUsername = data.user.username || data.user.user || currentUserId;
                    localStorage.setItem('mindmesh_user', JSON.stringify(data.user));
                    localStorage.setItem('mindmesh_user_id', currentUserId);
                    localStorage.setItem('mindmesh_username', currentUsername);
                }
            }
        } catch (e) {
            console.log("Could not check session");
        }
    }

    // If still no user, redirect to login
    if (!currentUserId) {
        window.location.href = '/login';
        return;
    }

    const activeUserEl = document.getElementById('active-user-id');
    if (activeUserEl) {
        activeUserEl.value = currentUsername || currentUserId;
        activeUserEl.title = `User ID: ${currentUserId}`;
    }

    loadAccounts();
}

function showAlert(msg, color = '#6366f1') {
    const box = document.getElementById('alert-box');
    if (!box) return;
    box.style.borderColor = color;
    box.innerText = msg;
    box.style.display = 'block';
    setTimeout(() => {
        box.style.display = 'none';
    }, 4000);
}

async function switchUser() {
    const inputEl = document.getElementById('active-user-id');
    const val = inputEl ? inputEl.value.trim() : '';
    if (!val) {
        showAlert('Please enter a username or user ID', '#ef4444');
        return;
    }

    try {
        const res = await fetch(`/accounts?user_id=${encodeURIComponent(val)}`);
        if (res.ok) {
            const data = await res.json();
            currentUserId = data.user_id || val;
            currentUsername = val;
            localStorage.setItem('mindmesh_user_id', currentUserId);
            localStorage.setItem('mindmesh_username', currentUsername);
            showAlert(`Active user: ${currentUsername}`, '#10b981');
            renderAccounts(data.accounts || []);
            return;
        }
    } catch (e) {}

    currentUserId = val;
    currentUsername = val;
    localStorage.setItem('mindmesh_user_id', val);
    localStorage.setItem('mindmesh_username', val);
    showAlert(`Switched active user: ${val}`);
    loadAccounts();
}


async function loadAccounts() {
    try {
        const res = await fetch(`/accounts?user_id=${encodeURIComponent(currentUserId)}`);
        const data = await res.json();
        renderAccounts(data.accounts || []);
    } catch (err) {
        console.error("Error loading accounts:", err);
    }
}

function renderAccounts(accounts) {
    const tbody = document.getElementById('accounts-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    let hasGmail = false;
    let hasTelegram = false;
    let hasWhatsApp = false;

    if (!accounts || accounts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No accounts connected for this user yet.</td></tr>';
    } else {
        accounts.forEach(acc => {
            const tr = document.createElement('tr');
            const isActive = acc.is_active === true || acc.is_active === 't' || acc.is_active === 1;
            const src = (acc.source || '').toUpperCase();
            tr.innerHTML = `
                <td><span class="account-badge">${src}</span></td>
                <td style="font-weight: 600;">${acc.account_identifier}</td>
                <td><span class="badge ${isActive ? 'connected' : 'disconnected'}">${isActive ? 'Active' : 'Inactive'}</span></td>
                <td style="color: var(--text-muted);">${acc.created_at ? new Date(acc.created_at).toLocaleString() : '-'}</td>
                <td><button class="disconnect-btn" onclick="disconnectSpecificAccount('${src}', '${acc.account_identifier}')">Disconnect</button></td>
            `;
            tbody.appendChild(tr);

            if (src === 'GMAIL' && isActive) {
                hasGmail = true;
                const el = document.getElementById('gmail-connected-info');
                if (el) el.innerText = acc.account_identifier;
            }
            if (src === 'TELEGRAM' && isActive) {
                hasTelegram = true;
                const el = document.getElementById('telegram-connected-info');
                if (el) el.innerText = 'ID: ' + acc.account_identifier;
            }
            if (src === 'WHATSAPP' && isActive) {
                hasWhatsApp = true;
                const el = document.getElementById('whatsapp-connected-info');
                if (el) el.innerText = acc.account_identifier;
            }
        });
    }

    // Update Gmail card
    const gBadge = document.getElementById('gmail-badge');
    const gActions = document.getElementById('gmail-actions');
    const gInfo = document.getElementById('gmail-connected-info');
    if (gBadge && gActions) {
        if (hasGmail) {
            gBadge.className = 'badge connected';
            gBadge.innerText = 'Connected';
            gActions.innerHTML = `
                <button class="btn btn-outline" onclick="connectGmail()">Reconnect</button>
                <button class="btn btn-danger" onclick="disconnectAccount('GMAIL')">Disconnect</button>
            `;
        } else {
            gBadge.className = 'badge disconnected';
            gBadge.innerText = 'Disconnected';
            if (gInfo) gInfo.innerText = '';
            gActions.innerHTML = `<button class="btn" onclick="connectGmail()">Connect with Google</button>`;
        }
    }

    // Update Telegram card
    const tBadge = document.getElementById('telegram-badge');
    const tStep1 = document.getElementById('telegram-step-1');
    const tStep2 = document.getElementById('telegram-step-2');
    const tActions = document.getElementById('telegram-connected-actions');
    const tInfo = document.getElementById('telegram-connected-info');
    if (tBadge) {
        if (hasTelegram) {
            tBadge.className = 'badge connected';
            tBadge.innerText = 'Connected';
            if (tStep1) tStep1.style.display = 'none';
            if (tStep2) tStep2.style.display = 'none';
            if (tActions) tActions.style.display = 'block';
        } else {
            tBadge.className = 'badge disconnected';
            tBadge.innerText = 'Disconnected';
            if (tInfo) tInfo.innerText = '';
            if (tStep1) tStep1.style.display = 'block';
            if (tStep2) tStep2.style.display = 'none';
            if (tActions) tActions.style.display = 'none';
        }
    }

    // Update WhatsApp card
    const wBadge = document.getElementById('whatsapp-badge');
    const wInit = document.getElementById('whatsapp-initial-actions');
    const wQR = document.getElementById('whatsapp-qr-box');
    const wActions = document.getElementById('whatsapp-connected-actions');
    const wInfo = document.getElementById('whatsapp-connected-info');
    if (wBadge) {
        if (hasWhatsApp) {
            wBadge.className = 'badge connected';
            wBadge.innerText = 'Connected';
            if (wInit) wInit.style.display = 'none';
            if (wQR) wQR.style.display = 'none';
            if (wActions) wActions.style.display = 'block';
            if (qrPollTimer) clearInterval(qrPollTimer);
        } else {
            wBadge.className = 'badge disconnected';
            wBadge.innerText = 'Disconnected';
            if (wInfo) wInfo.innerText = '';
            if (wInit) wInit.style.display = 'block';
            if (wActions) wActions.style.display = 'none';
        }
    }
}

// ==================== GMAIL ====================
function connectGmail() {
    window.location.href = `/auth/gmail?user_id=${encodeURIComponent(currentUserId)}`;
}

// ==================== TELEGRAM ====================

async function sendTelegramCode() {
    const phone = document.getElementById('tg-phone').value.trim();

    showAlert('Sending code to Telegram...');
    try {
        const res = await fetch('/auth/telegram/send-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: currentUserId, phone: phone })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showAlert('Code sent! Check your Telegram app.', '#10b981');
            document.getElementById('telegram-step-1').style.display = 'none';
            document.getElementById('telegram-step-2').style.display = 'block';
        } else {
            showAlert(data.detail || data.message || 'Failed to send code.', '#ef4444');
        }
    } catch (err) {
        showAlert('Error sending code: ' + err.message, '#ef4444');
    }
}


async function verifyTelegramCode() {
    const codeInput = document.getElementById('tg-code');
    const passwordInput = document.getElementById('tg-password');
    const code = codeInput ? codeInput.value.trim() : '';
    const password = passwordInput ? passwordInput.value.trim() : '';

    if (!code) {
        showAlert('Please enter the OTP code.', '#ef4444');
        if (codeInput) codeInput.focus();
        return;
    }

    showAlert('Verifying code with Telegram...');
    try {
        const res = await fetch('/auth/telegram/verify-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: currentUserId, code: code, password: password || null })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showAlert('Telegram successfully connected!', '#10b981');

            // Immediately transition Telegram card UI to Connected state
            const tBadge = document.getElementById('telegram-badge');
            const tStep1 = document.getElementById('telegram-step-1');
            const tStep2 = document.getElementById('telegram-step-2');
            const tActions = document.getElementById('telegram-connected-actions');
            const tInfo = document.getElementById('telegram-connected-info');
            if (tBadge) {
                tBadge.className = 'badge connected';
                tBadge.innerText = 'Connected';
            }
            if (tStep1) tStep1.style.display = 'none';
            if (tStep2) tStep2.style.display = 'none';
            if (tActions) tActions.style.display = 'block';
            if (tInfo && data.telegram_id) {
                tInfo.innerText = 'ID: ' + data.telegram_id;
            }

            // Reload accounts list from backend
            await loadAccounts();
        } else if (data.needs_password) {
            showAlert('Two-factor password required. Enter your 2FA password.', '#f59e0b');
            if (passwordInput) {
                passwordInput.style.borderColor = '#f59e0b';
                passwordInput.focus();
            }
        } else {
            showAlert(data.detail || data.message || 'Verification failed.', '#ef4444');
        }
    } catch (err) {
        showAlert('Verification error: ' + err.message, '#ef4444');
    }
}

function resetTelegramForm() {
    document.getElementById('telegram-step-1').style.display = 'block';
    document.getElementById('telegram-step-2').style.display = 'none';
}

// ==================== WHATSAPP ====================
async function startWhatsAppLogin() {
    showAlert('Starting WhatsApp session...');
    const initActions = document.getElementById('whatsapp-initial-actions');
    const box = document.getElementById('whatsapp-qr-box');
    const img = document.getElementById('whatsapp-qr-img');
    const inst = box ? box.querySelector('.qr-instructions') : null;

    if (initActions) initActions.style.display = 'none';
    if (box) {
        box.style.display = 'flex';
        if (img) img.style.display = 'none';
        if (inst) inst.innerText = 'Starting WhatsApp service and preparing QR code...';
    }

    try {
        const res = await fetch('/auth/whatsapp/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: currentUserId })
        });
        const data = await res.json();

        // Start polling QR code
        pollWhatsAppQR();
    } catch (err) {
        showAlert('Error starting WhatsApp login: ' + err.message, '#ef4444');
        if (initActions) initActions.style.display = 'block';
        if (box) box.style.display = 'none';
    }
}

function pollWhatsAppQR() {
    if (qrPollTimer) clearInterval(qrPollTimer);

    const box = document.getElementById('whatsapp-qr-box');
    const img = document.getElementById('whatsapp-qr-img');
    const initActions = document.getElementById('whatsapp-initial-actions');
    const inst = box ? box.querySelector('.qr-instructions') : null;

    qrPollTimer = setInterval(async () => {
        try {
            const res = await fetch(`/auth/whatsapp/qr?user_id=${encodeURIComponent(currentUserId)}`);
            const data = await res.json();

            if (data.status === 'scan_qr' && data.qr_data_url) {
                if (img) {
                    img.src = data.qr_data_url;
                    img.style.display = 'block';
                }
                if (box) box.style.display = 'flex';
                if (inst) inst.innerText = 'Open WhatsApp > Settings > Linked Devices > Link a Device';
            } else if (data.status === 'connected' || data.status === 'already_connected') {
                clearInterval(qrPollTimer);
                if (box) box.style.display = 'none';
                showAlert('WhatsApp successfully connected!', '#10b981');

                // Immediately update card to connected state
                const wBadge = document.getElementById('whatsapp-badge');
                const wActions = document.getElementById('whatsapp-connected-actions');
                const wInfo = document.getElementById('whatsapp-connected-info');
                if (wBadge) {
                    wBadge.className = 'badge connected';
                    wBadge.innerText = 'Connected';
                }
                if (initActions) initActions.style.display = 'none';
                if (wActions) wActions.style.display = 'block';
                if (wInfo && data.account_identifier) {
                    wInfo.innerText = data.account_identifier;
                }

                await loadAccounts();
            } else if (data.status === 'error') {
                clearInterval(qrPollTimer);
                if (box) box.style.display = 'none';
                if (initActions) initActions.style.display = 'block';
                showAlert('WhatsApp error: ' + (data.message || 'Process error'), '#ef4444');
            } else if (data.status === 'waiting_for_qr') {
                if (inst && (!img || img.style.display === 'none')) {
                    inst.innerText = 'Generating QR code, please wait a moment...';
                }
            }
        } catch (err) {
            console.error('QR polling error', err);
        }
    }, 1000);
}

// ==================== DISCONNECT ====================
async function disconnectAccount(source) {
    if (!confirm(`Are you sure you want to disconnect ${source}?`)) return;

    try {
        const res = await fetch('/accounts/disconnect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: currentUserId, source: source })
        });
        const data = await res.json();
        if (data.success) {
            showAlert(`${source} disconnected.`, '#10b981');
            loadAccounts();
        }
    } catch (err) {
        showAlert('Disconnect failed: ' + err.message, '#ef4444');
    }
}

async function disconnectSpecificAccount(source, identifier) {
    if (!confirm(`Disconnect ${source} (${identifier})?`)) return;

    try {
        const res = await fetch('/accounts/disconnect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: currentUserId, source: source, account_identifier: identifier })
        });
        const data = await res.json();
        if (data.success) {
            showAlert('Account disconnected.', '#10b981');
            loadAccounts();
        }
    } catch (err) {
        showAlert('Disconnect failed: ' + err.message, '#ef4444');
    }
}

// Initialize on load
window.onload = () => {
    initUser();
    const params = new URLSearchParams(window.location.search);
    if (params.get('connected') === 'gmail') {
        showAlert('Gmail connected successfully!', '#10b981');
    }
};

