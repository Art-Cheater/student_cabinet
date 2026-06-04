(function () {
    var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
        document.documentElement.classList.add('no-motion');
        document.querySelectorAll('.bento-cell, .reveal-on-scroll').forEach(function (el) {
            el.classList.add('reveal-visible');
        });
        return;
    }

    var revealSelector = '.bento-cell, .reveal-on-scroll, .dash-card, .home-news-preview, .student-cabinet-card, .teacher-profile-card';
    var items = document.querySelectorAll(revealSelector);
    if (!items.length) return;

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            var el = entry.target;
            var delay = 0;
            if (el.classList.contains('bento-cell')) {
                var cells = Array.prototype.indexOf.call(
                    el.parentElement ? el.parentElement.querySelectorAll('.bento-cell') : [],
                    el
                );
                delay = Math.max(0, cells) * 60;
            }
            setTimeout(function () {
                el.classList.add('reveal-visible');
            }, delay);
            observer.unobserve(el);
        });
    }, { rootMargin: '0px 0px -40px 0px', threshold: 0.08 });

    items.forEach(function (el) { observer.observe(el); });

    document.querySelectorAll('.btn-accent, .btn-primary').forEach(function (btn) {
        btn.addEventListener('mousedown', function () {
            btn.style.transform = 'scale(0.98)';
        });
        btn.addEventListener('mouseup', function () {
            btn.style.transform = '';
        });
    });
})();
