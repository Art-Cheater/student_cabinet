(function () {
    function formatRoom(raw) {
        var digits = (raw || '').replace(/\D/g, '');
        if (!digits) return '';
        if (digits.length <= 1) return digits;
        return digits.charAt(0) + '-' + digits.slice(1);
    }

    function applyMask(input) {
        input.addEventListener('input', function () {
            var pos = input.selectionStart;
            var old = input.value;
            input.value = formatRoom(old);
        });
        input.addEventListener('blur', function () {
            input.value = formatRoom(input.value);
        });
    }

    function init() {
        document.querySelectorAll('[data-room-mask]').forEach(applyMask);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    window.RoomMask = { formatRoom: formatRoom, applyMask: applyMask };
})();
