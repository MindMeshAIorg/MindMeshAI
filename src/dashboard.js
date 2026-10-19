// Global Dashboard State
let currentUserId = null;
let currentUsername = 'User';
let isGenerating = false;
let messageHistory = [];

// Initialize Dashboard
window.addEventListener('DOMContentLoaded', async () => {
    // 1. Check logged-in user in localStorage
    const savedUid = localStorage.getItem('mindmesh_user_id');
    const savedUserRaw = localStorage.getItem('mindmesh_user');

    if (savedUid && savedUserRaw) {
        try {
            const savedUser = JSON.parse(savedUserRaw);
            currentUserId = savedUid || savedUser.user_id || savedUser.id || savedUser.username;
            currentUsername = savedUser.username || savedUser.user || currentUserId;
        } catch (e) {
            console.warn("Failed to parse saved user", e);
        }
    }

    // If still not identified, verify session with backend
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
            console.log("Not authenticated via session");
        }
    }

    // If no user is logged in, redirect to login page immediately
    if (!currentUserId) {
        window.location.href = '/login';
        return;
    }

    // 2. Update user profile display
    updateUserDisplay();

    // 3. Update connectors links with user_id parameter
    updateConnectorsLinks();

    // 4. Load previous messages from backend
    loadChatHistory();

    // 5. Load notifications from JSON storage & start real-time polling
    loadNotifications();
    setInterval(loadNotifications, 3000);

    // 6. Trigger background sync for the active logged-in user
    triggerBackgroundSync();

    // 7. Focus input
    const textarea = document.getElementById('chat-textarea');
    if (textarea) textarea.focus();
});

async function triggerBackgroundSync() {
    if (!currentUserId) return;
    try {
        await fetch('/api/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: currentUserId })
        });
    } catch (e) {
        console.warn("Auto-sync request error:", e);
    }
}

function updateUserDisplay() {
    const usernameEl = document.getElementById('username-display');
    const avatarEl = document.getElementById('user-avatar');
    if (usernameEl) {
        usernameEl.textContent = currentUsername;
        usernameEl.title = `User ID: ${currentUserId}`;
    }
    if (avatarEl) {
        avatarEl.textContent = (currentUsername || 'U').charAt(0).toUpperCase();
    }
}

function updateConnectorsLinks() {
    const navConn = document.getElementById('nav-connectors');
    const headerConn = document.querySelector('.header-connectors-btn');
    const url = `/conectors.html?user_id=${encodeURIComponent(currentUserId)}`;
    if (navConn) navConn.href = url;
    if (headerConn) headerConn.href = url;
}


// Sidebar Controls
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.toggle('open');
}

// State for live notifications
let previousNotifCount = -1;
let knownNotifIds = new Set();
let currentNotifFilter = 'all';

// Notifications Drawer Controls
function toggleNotifications() {
    const drawer = document.getElementById('notification-drawer');
    const backdrop = document.getElementById('drawer-backdrop');
    if (drawer && backdrop) {
        const opening = !drawer.classList.contains('open');
        drawer.classList.toggle('open');
        backdrop.classList.toggle('active');
        if (opening) {
            loadNotifications();
        }
    }
}

async function completeNotification(chunkId, event) {
    if (event) event.stopPropagation();
    try {
        const uid = currentUserId || 'single_user';
        const res = await fetch('/api/notifications/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chunk_id: chunkId, user_id: uid })
        });
        if (res.ok) {
            await loadNotifications();
        }
    } catch (err) {
        console.warn("Failed to complete notification:", err);
    }
}

function showNotificationToast(item) {
    const container = document.getElementById('notif-toast-container');
    if (!container) return;

    const source = (item.source || '').toUpperCase();
    const cat = (item.category || '').toUpperCase();
    const chat = item.chat_name ? ` • ${item.chat_name}` : '';
    const text = (item.actual_text_in_chunk || '').slice(0, 90);

    const toast = document.createElement('div');
    toast.className = 'notif-toast';
    toast.innerHTML = `
        <div style="font-size: 1.25rem;">🔔</div>
        <div style="flex-grow: 1;">
            <div style="font-size: 0.72rem; font-weight: 700; color: #818cf8; letter-spacing: 0.03em;">
                ${source} ${cat}${chat}
            </div>
            <div style="font-size: 0.8rem; color: #f1f5f9; margin-top: 2px;">
                ${text}${text.length >= 90 ? '...' : ''}
            </div>
        </div>
    `;

    toast.onclick = () => {
        toggleNotifications();
        toast.remove();
    };

    container.appendChild(toast);
    setTimeout(() => {
        if (toast.parentElement) toast.remove();
    }, 5000);
}

async function loadNotifications() {
    const listEl = document.getElementById('notifications-list');
    const badge = document.getElementById('notif-badge');
    const headerBadge = document.getElementById('header-notif-badge');

    const uid = currentUserId || 'single_user';
    const url = `/api/notifications?user_id=${encodeURIComponent(uid)}`;

    try {
        const res = await fetch(url);
        if (!res.ok) return;
        const data = await res.json();
        const items = data.notifications || [];

        // Check for new items to trigger real-time toast alert
        if (previousNotifCount >= 0 && items.length > previousNotifCount) {
            items.forEach(it => {
                if (!knownNotifIds.has(it.chunk_id)) {
                    showNotificationToast(it);
                }
            });
        }
        knownNotifIds = new Set(items.map(it => it.chunk_id));
        previousNotifCount = items.length;

        // Update badges
        if (badge) {
            badge.textContent = items.length;
            badge.style.display = items.length > 0 ? 'flex' : 'none';
        }
        if (headerBadge) {
            headerBadge.textContent = items.length;
            headerBadge.style.display = items.length > 0 ? 'inline-flex' : 'none';
        }

        if (!listEl) return;

        if (items.length === 0) {
            listEl.innerHTML = `
                <div style="padding: 32px 16px; text-align: center; color: var(--text-muted, #94a3b8);">
                    <div style="font-size: 28px; margin-bottom: 8px;">✨</div>
                    <div style="font-size: 14px; font-weight: 500;">No pending alerts or reminders.</div>
                    <div style="font-size: 12px; margin-top: 4px; opacity: 0.7;">Run rag_runner_2.0.py to detect new tasks</div>
                </div>
            `;
            return;
        }

        listEl.innerHTML = '';
        items.forEach(it => {
            const cat = (it.category || 'WORK').toLowerCase();
            const source = (it.source || '').toUpperCase();
            const sourceLower = source.toLowerCase();

            let icon = '🔔';
            let boxClass = `${cat}-box`;
            if (cat === 'deadline') {
                icon = '⏰';
                boxClass = 'deadline-box';
            } else if (cat === 'event') {
                icon = '📅';
                boxClass = 'event-box';
            } else if (source === 'WHATSAPP') {
                icon = '💬';
                boxClass = 'whatsapp-box';
            } else if (source === 'TELEGRAM') {
                icon = '✈️';
                boxClass = 'telegram-box';
            } else if (source === 'EMAIL' || source === 'GMAIL') {
                icon = '✉️';
                boxClass = 'email-box';
            }

            const dateStr = it.timestamp ? new Date(it.timestamp).toLocaleDateString(undefined, {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
            }) : '';

            const safeText = (it.actual_text_in_chunk || '')
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;");

            const chatHtml = it.chat_name ? `<div class="notif-chat-tag">Chat: ${it.chat_name}</div>` : '';

            const el = document.createElement('div');
            el.className = `notif-item ${cat}`;
            el.setAttribute('data-category', cat);
            el.setAttribute('data-source', sourceLower);

            el.innerHTML = `
                <div class="notif-icon-box ${boxClass}">${icon}</div>
                <div class="notif-content">
                    <div class="notif-header">
                        <span class="notif-source">${source} • ${it.category}</span>
                        <span class="notif-time">${dateStr}</span>
                    </div>
                    <div class="notif-body">${safeText}</div>
                    ${chatHtml}
                    <div class="notif-actions">
                        <button class="notif-complete-btn" onclick="completeNotification('${it.chunk_id}', event)">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
                            Mark Done
                        </button>
                    </div>
                </div>
            `;
            listEl.appendChild(el);
        });

        // Reapply current filter
        applyNotificationFilter(currentNotifFilter);

    } catch (e) {
        console.warn("Could not load notifications:", e);
    }
}

function filterNotifications(filterKey) {
    currentNotifFilter = (filterKey || 'all').toLowerCase();

    // Update active tab button
    const tabs = document.querySelectorAll('.drawer-tab');
    tabs.forEach(t => t.classList.remove('active'));
    if (window.event && window.event.target) {
        window.event.target.classList.add('active');
    }

    applyNotificationFilter(currentNotifFilter);
}

function applyNotificationFilter(filterKey) {
    const items = document.querySelectorAll('.notif-item');
    items.forEach(item => {
        const cat = (item.getAttribute('data-category') || '').toLowerCase();
        const src = (item.getAttribute('data-source') || '').toLowerCase();
        if (
            filterKey === 'all'
            || cat === filterKey
            || src === filterKey
            || (filterKey === 'gmail' && (src === 'email' || src === 'gmail'))
        ) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

// Textarea Handling & Auto-resize
function autoResizeTextarea(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) {
        sendBtn.disabled = !el.value.trim() || isGenerating;
    }
}

function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

// Quick Prompt Suggestion
function sendPrompt(text) {
    const textarea = document.getElementById('chat-textarea');
    if (textarea) {
        textarea.value = text;
        autoResizeTextarea(textarea);
        sendMessage();
    }
}

// Start New Chat
function startNewChat() {
    const messagesList = document.getElementById('messages-list');
    const emptyState = document.getElementById('empty-state');
    if (messagesList) messagesList.innerHTML = '';
    if (emptyState) emptyState.style.display = 'block';
    messageHistory = [];

    const textarea = document.getElementById('chat-textarea');
    if (textarea) {
        textarea.value = '';
        autoResizeTextarea(textarea);
        textarea.focus();
    }
}

// Load Chat History from Backend
async function loadChatHistory() {
    try {
        const res = await fetch(`/api/chat/history?user_id=${encodeURIComponent(currentUserId)}`);
        if (!res.ok) return;
        const data = await res.json();
        const history = data.messages || [];

        if (history.length > 0) {
            const emptyState = document.getElementById('empty-state');
            if (emptyState) emptyState.style.display = 'none';

            history.forEach(item => {
                appendMessageToUI(item.role, item.content);
            });
        }
    } catch (e) {
        console.warn("Could not load chat history:", e);
    }
}

// Send Message
async function sendMessage() {
    if (isGenerating) return;

    const textarea = document.getElementById('chat-textarea');
    const sendBtn = document.getElementById('send-btn');
    const message = textarea.value.trim();

    if (!message) return;

    // Reset textarea
    textarea.value = '';
    autoResizeTextarea(textarea);

    // Hide empty state
    const emptyState = document.getElementById('empty-state');
    if (emptyState) emptyState.style.display = 'none';

    // Append user message
    appendMessageToUI('user', message);
    isGenerating = true;
    sendBtn.disabled = true;

    // Show assistant typing bubble
    const typingRow = appendTypingIndicator();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                user_id: currentUserId
            })
        });

        // Remove typing indicator
        if (typingRow && typingRow.parentNode) {
            typingRow.parentNode.removeChild(typingRow);
        }

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            const errMsg = errData.detail || 'MindMesh AI server encountered an issue.';
            appendMessageToUI('assistant', `⚠️ **Error:** ${errMsg}`);
            return;
        }

        const data = await response.json();
        const assistantAnswer = data.answer || "No response received.";
        appendMessageToUI('assistant', assistantAnswer);

    } catch (err) {
        if (typingRow && typingRow.parentNode) {
            typingRow.parentNode.removeChild(typingRow);
        }
        appendMessageToUI('assistant', `⚠️ **Connection error:** Could not reach backend (${err.message}).`);
    } finally {
        isGenerating = false;
        autoResizeTextarea(textarea);
        textarea.focus();
    }
}

// Append Message Row to UI
function appendMessageToUI(role, content) {
    const list = document.getElementById('messages-list');
    if (!list) return;

    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    if (role === 'assistant') {
        const avatar = document.createElement('div');
        avatar.className = 'assistant-avatar';
        avatar.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7L12 12L22 7L12 2Z"/>
                <path d="M2 17L12 22L22 17"/>
                <path d="M2 12L12 17L22 12"/>
            </svg>
        `;
        row.appendChild(avatar);
    }

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = formatMarkdown(content);

    row.appendChild(bubble);
    list.appendChild(row);

    // Scroll to bottom
    const container = document.getElementById('messages-container');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

// Typing Indicator
function appendTypingIndicator() {
    const list = document.getElementById('messages-list');
    if (!list) return null;

    const row = document.createElement('div');
    row.className = 'message-row assistant';

    const avatar = document.createElement('div');
    avatar.className = 'assistant-avatar';
    avatar.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7L12 12L22 7L12 2Z"/>
            <path d="M2 17L12 22L22 17"/>
            <path d="M2 12L12 17L22 12"/>
        </svg>
    `;
    row.appendChild(avatar);

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = `
        <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
    `;

    row.appendChild(bubble);
    list.appendChild(row);

    const container = document.getElementById('messages-container');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }

    return row;
}

// Simple Markdown Formatter
function formatMarkdown(text) {
    if (!text) return '';
    // Escape basic HTML
    let escaped = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");

    // Code blocks ```code```
    escaped = escaped.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');

    // Inline code `code`
    escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold **text**
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic *text*
    escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Newlines to <br> or paragraphs
    const paragraphs = escaped.split('\n\n');
    return paragraphs.map(p => {
        if (p.startsWith('<pre>')) return p;
        return `<p>${p.replace(/\n/g, '<br>')}</p>`;
    }).join('');
}

// Logout
async function handleLogout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {
        console.warn("Logout error:", e);
    }
    localStorage.removeItem('mindmesh_user');
    window.location.href = '/login';
}
