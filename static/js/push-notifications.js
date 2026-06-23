(function () {
    if (!('serviceWorker' in navigator) || !window.fetch) return;

    function urlBase64ToUint8Array(base64String) {
        var padding = '='.repeat((4 - base64String.length % 4) % 4);
        var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        var raw = window.atob(base64);
        var arr = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
        return arr;
    }

    window.subscribePushNotifications = async function () {
        if (!('PushManager' in window) || !('Notification' in window)) {
            return { ok: false, error: 'Браузер не поддерживает push' };
        }
        var perm = await Notification.requestPermission();
        if (perm !== 'granted') {
            return { ok: false, error: 'Разрешение не дано' };
        }
        var reg = await navigator.serviceWorker.ready;
        var keyResp = await fetch('/api/push/vapid-key');
        var keyData = await keyResp.json();
        if (!keyData.enabled || !keyData.publicKey) {
            return { ok: false, error: 'Push не настроен на сервере' };
        }
        var sub = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(keyData.publicKey),
        });
        var json = sub.toJSON();
        await fetch('/api/push/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                endpoint: json.endpoint,
                keys: json.keys,
            }),
        });
        return { ok: true };
    };
})();
