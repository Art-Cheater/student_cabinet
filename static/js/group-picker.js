(function () {
    var datalistEl = null;
    var tagsWrap = null;
    var hiddenInput = null;
    var multiInput = null;
    var selected = [];

    function fetchGroups(q, cb) {
        fetch('/api/groups/search?q=' + encodeURIComponent(q || ''))
            .then(function (r) { return r.json(); })
            .then(cb)
            .catch(function () { cb([]); });
    }

    function refreshDatalist(groups) {
        if (!datalistEl) return;
        datalistEl.innerHTML = '';
        groups.forEach(function (g) {
            var opt = document.createElement('option');
            opt.value = g.name;
            opt.dataset.id = g.id;
            datalistEl.appendChild(opt);
        });
    }

    function renderTags() {
        if (!tagsWrap) return;
        tagsWrap.innerHTML = '';
        selected.forEach(function (g, idx) {
            var tag = document.createElement('span');
            tag.className = 'group-picker-tag';
            tag.textContent = g.name;
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = '×';
            btn.onclick = function () {
                selected.splice(idx, 1);
                renderTags();
                syncHidden();
            };
            tag.appendChild(btn);
            tagsWrap.appendChild(tag);
        });
    }

    function syncHidden() {
        if (hiddenInput) {
            hiddenInput.value = selected.map(function (g) { return g.id; }).join(',');
        }
    }

    function addByName(name) {
        name = (name || '').trim();
        if (!name) return;
        fetchGroups(name, function (groups) {
            var match = groups.find(function (g) { return g.name === name; }) || { id: 0, name: name };
            if (selected.some(function (s) { return s.name === match.name; })) return;
            selected.push({ id: match.id, name: match.name });
            renderTags();
            syncHidden();
            if (multiInput) multiInput.value = '';
        });
    }

    function initPicker(root) {
        var audience = document.getElementById('audience_type');
        var oneWrap = document.getElementById('group-one-wrap');
        var multiWrap = document.getElementById('group-multi-wrap');
        datalistEl = document.getElementById('groups-datalist');
        tagsWrap = document.getElementById('group-tags');
        hiddenInput = document.getElementById('group_ids_hidden');
        multiInput = document.getElementById('group_multi_input');
        var oneInput = document.getElementById('group_one_input');

        function updateVisibility() {
            var v = audience ? audience.value : 'anyone';
            if (oneWrap) oneWrap.style.display = v === 'one_group' ? 'block' : 'none';
            if (multiWrap) multiWrap.style.display = v === 'multi_group' ? 'block' : 'none';
            selected = [];
            renderTags();
            syncHidden();
        }

        if (audience) {
            audience.addEventListener('change', updateVisibility);
            updateVisibility();
        }

        fetchGroups('', refreshDatalist);

        if (oneInput) {
            oneInput.addEventListener('change', function () {
                selected = [];
                addByName(oneInput.value);
                if (selected.length) selected = [selected[selected.length - 1]];
                renderTags();
                syncHidden();
            });
        }

        if (multiInput) {
            multiInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    addByName(multiInput.value);
                }
            });
            multiInput.addEventListener('blur', function () {
                if (multiInput.value.trim()) addByName(multiInput.value);
            });
        }

        var form = root.closest('form');
        if (form) {
            form.addEventListener('submit', function () {
                syncHidden();
            });
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var root = document.getElementById('slot-form');
        if (root) initPicker(root);
    });

    window.GroupPicker = {
        getSelectedIds: function () {
            return selected.map(function (g) { return g.id; }).filter(Boolean);
        },
        getSelectedNames: function () {
            return selected.map(function (g) { return g.name; });
        },
    };
})();
