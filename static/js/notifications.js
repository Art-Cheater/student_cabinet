(function () {
    if (!document.body.dataset.userRole) return;

    var bell = document.getElementById('navNotifyToggle');
    var dropdown = document.getElementById('navNotifyDropdown');
    var badge = document.getElementById('navNotifyBadge');
    var listEl = document.getElementById('navNotifyList');
    var pushBtn = document.getElementById('navNotifyPushBtn');
    if (!bell || !dropdown) return;

    async function loadNotifications() {
        try {
            var r = await fetch('/api/notifications');
            var data = await r.json();
            if (!r.ok) return;
            if (badge) {
                if (data.unread > 0) {
                    badge.textContent = data.unread > 99 ? '99+' : String(data.unread);
                    badge.hidden = false;
                } else {
                    badge.hidden = true;
                }
            }
            if (!listEl) return;
            listEl.innerHTML = '';
            var items = data.items || [];
            if (!items.length) {
                listEl.innerHTML = '<p class="hint nav-notify-empty">Нет уведомлений</p>';
                return;
            }
            items.forEach(function (item) {
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'nav-notify-item' + (item.is_read ? '' : ' nav-notify-item--unread');
                btn.innerHTML = '<strong>' + escapeHtml(item.title) + '</strong><span>' +
                    escapeHtml(item.body) + '</span>';
                btn.onclick = async function () {
                    await fetch('/api/notifications/' + item.id + '/read', { method: 'POST' });
                    if (item.url) window.location.href = item.url;
                    loadNotifications();
                };
                listEl.appendChild(btn);
            });
        } catch (e) { /* ignore */ }
    }

    function escapeHtml(s) {
        var d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    bell.addEventListener('click', function (e) {
        e.stopPropagation();
        var open = dropdown.hidden;
        dropdown.hidden = !open;
        bell.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) loadNotifications();
    });

    document.addEventListener('click', function () {
        dropdown.hidden = true;
        bell.setAttribute('aria-expanded', 'false');
    });
    dropdown.addEventListener('click', function (e) { e.stopPropagation(); });

    var readAll = document.getElementById('navNotifyReadAll');
    if (readAll) {
        readAll.addEventListener('click', async function () {
            await fetch('/api/notifications/read-all', { method: 'POST' });
            loadNotifications();
        });
    }

    if (pushBtn && window.subscribePushNotifications) {
        pushBtn.addEventListener('click', async function () {
            var res = await window.subscribePushNotifications();
            if (window.showToast) {
                window.showToast(
                    res.ok ? 'Push-уведомления включены' : (res.error || 'Не удалось'),
                    res.ok ? 'success' : 'error',
                );
            }
        });
    }

    loadNotifications();
    setInterval(loadNotifications, 60000);
})();
