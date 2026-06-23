(function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (!meta) return;
    var token = meta.getAttribute('content') || '';
    if (!token) return;

    var origFetch = window.fetch;
    window.fetch = function (url, opts) {
        opts = opts || {};
        var method = (opts.method || 'GET').toUpperCase();
        if (method === 'POST' || method === 'PUT' || method === 'PATCH' || method === 'DELETE') {
            if (opts.headers instanceof Headers) {
                if (!opts.headers.has('X-CSRF-Token')) {
                    opts.headers.set('X-CSRF-Token', token);
                }
            } else {
                opts.headers = Object.assign({}, opts.headers || {}, { 'X-CSRF-Token': token });
            }
        }
        return origFetch.call(this, url, opts);
    };
})();
