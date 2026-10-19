// Tab Switcher
function switchTab(tab) {
    const loginTab = document.getElementById('tab-login');
    const signupTab = document.getElementById('tab-signup');
    const loginForm = document.getElementById('login-form');
    const signupForm = document.getElementById('signup-form');
    hideAlert();

    if (tab === 'signup') {
        loginTab.classList.remove('active');
        signupTab.classList.add('active');
        loginForm.classList.remove('active');
        signupForm.classList.add('active');
    } else {
        signupTab.classList.remove('active');
        loginTab.classList.add('active');
        signupForm.classList.remove('active');
        loginForm.classList.add('active');
    }
}

function showAlert(message, type = 'error') {
    const alertBox = document.getElementById('auth-alert');
    if (!alertBox) return;
    alertBox.className = `alert-box ${type}`;
    alertBox.textContent = message;
    alertBox.style.display = 'block';
}

function hideAlert() {
    const alertBox = document.getElementById('auth-alert');
    if (alertBox) {
        alertBox.style.display = 'none';
    }
}

// Handle Login
async function handleLogin(e) {
    e.preventDefault();
    hideAlert();

    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const submitBtn = document.getElementById('login-submit-btn');

    if (!username || !password) {
        showAlert('Please enter both username and password.');
        return;
    }

    submitBtn.disabled = true;
    submitBtn.querySelector('span').textContent = 'Signing in...';

    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, user: username, password })
        });

        const data = await res.json();

        if (res.ok && data.success) {
            showAlert('Login successful! Redirecting to dashboard...', 'success');
            const user = data.user || {};
            const uid = user.user_id || user.id || user.username;
            localStorage.setItem('mindmesh_user', JSON.stringify(user));
            localStorage.setItem('mindmesh_user_id', uid);
            localStorage.setItem('mindmesh_username', user.username || user.user || uid);
            setTimeout(() => {
                window.location.href = '/dashboard';
            }, 600);
        } else {
            showAlert(data.detail || data.message || 'Invalid username or password.');
            submitBtn.disabled = false;
            submitBtn.querySelector('span').textContent = 'Sign In';
        }
    } catch (err) {
        showAlert('Network or server error: ' + err.message);
        submitBtn.disabled = false;
        submitBtn.querySelector('span').textContent = 'Sign In';
    }
}

// Handle Sign Up
async function handleSignUp(e) {
    e.preventDefault();
    hideAlert();

    const username = document.getElementById('signup-username').value.trim();
    const password = document.getElementById('signup-password').value;
    const confirmPassword = document.getElementById('signup-confirm-password').value;
    const submitBtn = document.getElementById('signup-submit-btn');

    if (!username) {
        showAlert('Please provide a username.');
        return;
    }

    if (password.length < 4) {
        showAlert('Password must be at least 4 characters long.');
        return;
    }

    if (password !== confirmPassword) {
        showAlert('Passwords do not match. Please re-enter.');
        return;
    }

    submitBtn.disabled = true;
    submitBtn.querySelector('span').textContent = 'Creating account...';

    try {
        const res = await fetch('/api/auth/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, user: username, password })
        });

        const data = await res.json();

        if (res.ok && data.success) {
            showAlert('Account created successfully! Redirecting...', 'success');
            const user = data.user || {};
            const uid = user.user_id || user.id || user.username;
            localStorage.setItem('mindmesh_user', JSON.stringify(user));
            localStorage.setItem('mindmesh_user_id', uid);
            localStorage.setItem('mindmesh_username', user.username || user.user || uid);
            setTimeout(() => {
                window.location.href = '/dashboard';
            }, 700);
        } else {
            showAlert(data.detail || data.message || 'Failed to create account.');
            submitBtn.disabled = false;
            submitBtn.querySelector('span').textContent = 'Create Account';
        }
    } catch (err) {
        showAlert('Network error: ' + err.message);
        submitBtn.disabled = false;
        submitBtn.querySelector('span').textContent = 'Create Account';
    }
}

// Auto-check if URL has #signup
window.addEventListener('DOMContentLoaded', () => {
    if (window.location.hash === '#signup' || window.location.pathname.includes('/signup')) {
        switchTab('signup');
    }
});
