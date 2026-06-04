(function () {
    const frame = document.getElementById('yandexMapFrame');
    const mapStatus = document.getElementById('mapStatus');
    const mapExternalLink = document.getElementById('mapExternalLink');
    const detailPanel = document.getElementById('mapDetailPanel');
    const detailTitle = document.getElementById('mapDetailTitle');
    const detailAddress = document.getElementById('mapDetailAddress');
    const detailPhone = document.getElementById('mapDetailPhone');
    const detailContact = document.getElementById('mapDetailContact');
    const detailExtra = document.getElementById('mapDetailExtra');
    const detailImg = document.getElementById('mapDetailImg');
    const detailRouteBtn = document.getElementById('mapDetailRoute');
    const defaultCenter = window.MAP_DEFAULT_CENTER || { lat: 58.6036, lon: 49.668 };

    let userCoords = null;
    const allLocations = (window.MAP_LOCATIONS || []).map(function (item) {
        return {
            ...item,
            lat: item.lat != null ? Number(item.lat) : null,
            lon: item.lon != null ? Number(item.lon) : null,
            type: item.kind || 'building',
            id: (item.kind || 'building') + '-' + item.number,
        };
    });

    function formatDistance(km) {
        if (km < 1) return Math.round(km * 1000) + ' м';
        return km.toFixed(1) + ' км';
    }

    function haversine(lat1, lon1, lat2, lon2) {
        const R = 6371;
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
        return R * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
    }

    function updateDistances() {
        document.querySelectorAll('.map-list-row').forEach(function (row) {
            const line = row.querySelector('[data-distance-for]');
            const lat = Number(row.dataset.lat);
            const lon = Number(row.dataset.lon);
            if (!line || !userCoords || !Number.isFinite(lat)) {
                if (line && !userCoords) line.textContent = '—';
                return;
            }
            line.textContent = formatDistance(haversine(userCoords.lat, userCoords.lon, lat, lon));
        });
    }

    function widgetUrlForPlace(place, zoom) {
        zoom = zoom || 16;
        if (!place || !Number.isFinite(place.lat) || !Number.isFinite(place.lon)) {
            return widgetUrlOverview();
        }
        const lon = place.lon;
        const lat = place.lat;
        return 'https://yandex.ru/map-widget/v1/?ll=' + lon + ',' + lat +
            '&z=' + zoom + '&pt=' + lon + ',' + lat + ',pm2rdm&lang=ru_RU';
    }

    function widgetUrlOverview() {
        const withCoords = allLocations.filter(function (p) {
            return Number.isFinite(p.lat) && Number.isFinite(p.lon);
        });
        if (!withCoords.length) {
            return 'https://yandex.ru/map-widget/v1/?ll=' + defaultCenter.lon + ',' + defaultCenter.lat +
                '&z=12&lang=ru_RU';
        }
        const pt = withCoords.map(function (p) { return p.lon + ',' + p.lat + ',pm2rdm'; }).join('~');
        const c = withCoords[0];
        return 'https://yandex.ru/map-widget/v1/?ll=' + c.lon + ',' + c.lat + '&z=12&pt=' + pt + '&lang=ru_RU';
    }

    function setMapFrame(url) {
        if (frame) frame.src = url;
    }

    function showYandexRouteLink(fromLat, fromLon, toLat, toLon, label) {
        var fromPart = Number.isFinite(fromLat) ? fromLat + ',' + fromLon + '~' : '~';
        var url = 'https://yandex.ru/maps/?rtext=' + fromPart + toLat + ',' + toLon + '&rtt=auto';
        mapExternalLink.innerHTML = '<a class="btn btn-outline map-open-external" href="' + url +
            '" target="_blank" rel="noopener">Маршрут в Яндекс.Картах: ' + label + '</a>';
        mapExternalLink.hidden = false;
    }

    function showDetail(place) {
        detailTitle.textContent = place.name || '';
        detailAddress.textContent = place.address ? 'Адрес: ' + place.address : '';
        detailPhone.textContent = place.phone ? 'Телефон: ' + place.phone : '';
        var contactBits = [];
        if (place.contact_role) contactBits.push(place.contact_role);
        if (place.contact_person) contactBits.push(place.contact_person);
        detailContact.textContent = contactBits.length ? contactBits.join(': ') : '';
        detailExtra.textContent = place.extra_info ? place.extra_info : '';
        detailExtra.hidden = !place.extra_info;

        if (place.image_url) {
            detailImg.src = place.image_url;
            detailImg.alt = place.name;
            detailImg.hidden = false;
        } else {
            detailImg.hidden = true;
        }
        detailPanel.classList.add('visible');
        detailRouteBtn.dataset.lat = place.lat;
        detailRouteBtn.dataset.lon = place.lon;
        detailRouteBtn.dataset.routeName = place.name;
        detailRouteBtn.dataset.address = place.address || '';

        document.querySelectorAll('.map-list-row').forEach(function (r) { r.classList.remove('active'); });
        var row = document.querySelector('.map-list-row[data-id="' + place.id + '"]');
        if (row) row.classList.add('active');

        if (Number.isFinite(place.lat) && Number.isFinite(place.lon)) {
            setMapFrame(widgetUrlForPlace(place, 16));
            mapStatus.textContent = 'Карта: ' + (place.name || '');
        } else {
            mapStatus.textContent = 'Нет координат — откройте маршрут по адресу в Яндекс.Картах.';
        }
        mapExternalLink.hidden = true;
    }

    function applyFilter(selected) {
        document.querySelectorAll('.location-item').forEach(function (row) {
            row.style.display = (selected === 'all' || row.dataset.type === selected) ? '' : 'none';
        });
    }

    function ensureUserCoords(callback) {
        if (userCoords) { callback(); return; }
        if (!navigator.geolocation) {
            mapStatus.textContent = 'Геолокация недоступна в браузере.';
            callback();
            return;
        }
        mapStatus.textContent = 'Определяем местоположение...';
        navigator.geolocation.getCurrentPosition(
            function (pos) {
                userCoords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
                updateDistances();
                mapStatus.textContent = 'Геопозиция определена.';
                callback();
            },
            function () {
                mapStatus.textContent = 'Геопозиция недоступна.';
                callback();
            },
            { enableHighAccuracy: true, timeout: 10000 }
        );
    }

    function buildRouteTo(targetLat, targetLon, targetName, targetAddress) {
        mapExternalLink.hidden = true;
        if (!Number.isFinite(targetLat) || !Number.isFinite(targetLon)) {
            if (targetAddress) {
                window.open('https://yandex.ru/maps/?text=' + encodeURIComponent('Киров, ' + targetAddress),
                    '_blank', 'noopener');
                mapStatus.textContent = 'Открыли поиск по адресу в Яндекс.Картах.';
            } else {
                mapStatus.textContent = 'Нет координат и адреса для маршрута.';
            }
            return;
        }
        ensureUserCoords(function () {
            showYandexRouteLink(
                userCoords ? userCoords.lat : null,
                userCoords ? userCoords.lon : null,
                targetLat,
                targetLon,
                targetName
            );
            mapStatus.textContent = userCoords
                ? 'Маршрут откроется в Яндекс.Картах (без API-ключа).'
                : 'Маршрут в Яндекс.Картах (разрешите геолокацию для старта от вас).';
            window.open(
                'https://yandex.ru/maps/?rtext=' +
                (userCoords ? userCoords.lat + ',' + userCoords.lon + '~' : '~') +
                targetLat + ',' + targetLon + '&rtt=auto',
                '_blank',
                'noopener'
            );
        });
    }

    var withCoords = allLocations.filter(function (p) {
        return Number.isFinite(p.lat) && Number.isFinite(p.lon);
    });
    setMapFrame(widgetUrlOverview());
    mapStatus.textContent = withCoords.length
        ? 'На карте ' + withCoords.length + ' объектов (виджет Яндекс.Карт, без API-ключа).'
        : 'Нет координат. Запустите: python parsers/vyatsu_campus.py';

    var highlighted = window.MAP_HIGHLIGHTED_BUILDING;
    if (highlighted) {
        var place = allLocations.find(function (p) {
            return String(p.number) === String(highlighted) && p.type === 'building';
        });
        if (place) showDetail(place);
    }

    document.getElementById('locateMeBtn').addEventListener('click', function () {
        ensureUserCoords(function () {
            if (userCoords) setMapFrame(widgetUrlForPlace(userCoords, 14));
        });
    });

    document.querySelectorAll('.map-filter').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.map-filter').forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');
            applyFilter(btn.dataset.type);
        });
    });

    document.querySelectorAll('.map-list-row').forEach(function (row) {
        row.addEventListener('click', function () {
            var place = allLocations.find(function (p) { return p.id === row.dataset.id; });
            if (place) showDetail(place);
        });
    });

    detailRouteBtn.addEventListener('click', function () {
        buildRouteTo(
            Number(detailRouteBtn.dataset.lat),
            Number(detailRouteBtn.dataset.lon),
            detailRouteBtn.dataset.routeName || 'объект',
            detailRouteBtn.dataset.address || ''
        );
    });
})();
