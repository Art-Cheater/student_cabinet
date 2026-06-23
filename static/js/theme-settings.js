(function () {
    var STORAGE_KEY = 'campusThemeSettings';
    var defaults = {
        mode: 'light',
        lesson: '#0039A6',
        university: '#0050B3',
        slot: '#FFC107',
        personal: '#7c3aed'
    };

    function load() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return Object.assign({}, defaults);
            return Object.assign({}, defaults, JSON.parse(raw));
        } catch (e) {
            return Object.assign({}, defaults);
        }
    }

    function save(settings) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    }

    function hexToRgb(hex) {
        var h = (hex || '').replace('#', '');
        if (h.length !== 6) return null;
        return {
            r: parseInt(h.slice(0, 2), 16),
            g: parseInt(h.slice(2, 4), 16),
            b: parseInt(h.slice(4, 6), 16)
        };
    }

    function tint(hex, alpha) {
        var rgb = hexToRgb(hex);
        if (!rgb) return hex;
        return 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',' + alpha + ')';
    }

    function apply(settings) {
        var root = document.documentElement;
        var isDark = settings.mode === 'dark';
        root.setAttribute('data-theme', isDark ? 'dark' : 'light');
        root.style.setProperty('--cal-color-lesson-border', settings.lesson);
        root.style.setProperty('--cal-color-lesson', tint(settings.lesson, isDark ? 0.22 : 0.08));
        root.style.setProperty('--cal-color-university-border', settings.university);
        root.style.setProperty('--cal-color-university', tint(settings.university, isDark ? 0.22 : 0.08));
        root.style.setProperty('--cal-color-slot-border', settings.slot);
        root.style.setProperty('--cal-color-slot', tint(settings.slot, isDark ? 0.25 : 0.15));
        root.style.setProperty('--cal-color-personal-border', settings.personal);
        root.style.setProperty('--cal-color-personal', tint(settings.personal, isDark ? 0.22 : 0.12));
        var fab = document.getElementById('themeToggleFab');
        if (fab) fab.textContent = isDark ? '🌙' : '☀️';
    }

    function bindPanel(settings) {
        var panel = document.getElementById('themeSettingsPanel');
        if (!panel) return;
        var bindColor = function (id, key) {
            var el = document.getElementById(id);
            if (!el) return;
            el.value = settings[key];
            el.addEventListener('input', function () {
                settings[key] = el.value;
                save(settings);
                apply(settings);
            });
        };
        bindColor('themeColorLesson', 'lesson');
        bindColor('themeColorUniversity', 'university');
        bindColor('themeColorSlot', 'slot');
        bindColor('themeColorPersonal', 'personal');
    }

    function bindFab(settings) {
        var fab = document.getElementById('themeToggleFab');
        if (!fab) return;
        fab.addEventListener('click', function () {
            settings.mode = settings.mode === 'dark' ? 'light' : 'dark';
            save(settings);
            apply(settings);
        });
    }

    var settings = load();
    apply(settings);
    function init() {
        bindPanel(settings);
        bindFab(settings);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
