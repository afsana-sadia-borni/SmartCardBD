(function () {
    'use strict';

    const appScript = document.getElementById('app-script');
    const config = appScript ? appScript.dataset : {};
    const BN = '০১২৩৪৫৬৭৮৯';
    const useBnDigits = () => document.cookie.includes('digits=bn');

    function getCookie(name) {
        const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
        return match ? decodeURIComponent(match[2]) : null;
    }

    function localizeDigits(text) {
        return useBnDigits() ? String(text).replace(/[0-9]/g, (d) => BN[d]) : String(text);
    }

    // ৳12,50,000 (lakh grouping, like the server's |taka filter).
    function formatTaka(value) {
        const n = Number(value);
        const opts = Number.isInteger(n) ? {} : { minimumFractionDigits: 2, maximumFractionDigits: 2 };
        return localizeDigits((n < 0 ? '-' : '') + '৳' + Math.abs(n).toLocaleString('en-IN', opts));
    }

    async function postData(url, data) {
        const body = data instanceof FormData ? data : new URLSearchParams(data);
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken'), 'X-Requested-With': 'XMLHttpRequest' },
            body: body,
        });
        if (response.status === 401) {
            window.location.href = '/accounts/login/?next=' + encodeURIComponent(window.location.pathname);
            throw new Error('login required');
        }
        if (!response.ok && response.status !== 400) throw new Error('Request failed: ' + response.status);
        return response.json();
    }

    function showToast(message, level) {
        if (!message) return;
        const colors = { success: 'success', error: 'danger', warning: 'warning', info: 'info' };
        const el = document.createElement('div');
        el.className = 'toast align-items-center border-0 text-bg-' + (colors[level] || 'secondary');
        el.setAttribute('role', 'alert');
        el.innerHTML = '<div class="d-flex"><div class="toast-body"></div>' +
            '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>';
        el.querySelector('.toast-body').textContent = message;
        document.getElementById('toast-container').appendChild(el);
        const toast = new bootstrap.Toast(el, { delay: 4000 });
        el.addEventListener('hidden.bs.toast', () => el.remove());
        toast.show();
    }

    function debounce(fn, wait) {
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn(...args), wait);
        };
    }

    // ---------- Theme (dark mode) ----------
    function applyThemeIcon() {
        const dark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
        document.querySelectorAll('.js-theme-icon').forEach((i) => { i.className = 'bi js-theme-icon ' + (dark ? 'bi-sun' : 'bi-moon-stars'); });
        document.querySelectorAll('.js-theme-toggle').forEach((b) => b.setAttribute('aria-pressed', dark));
    }
    applyThemeIcon();

    // ---------- Cart helpers ----------
    function updateCartCount(data) {
        const shown = data.cart_count_display !== undefined ? data.cart_count_display : localizeDigits(data.cart_count);
        document.querySelectorAll('.js-cart-count').forEach((el) => { el.textContent = shown; });
    }

    function updateMiniCart(html) {
        const body = document.querySelector('.js-mini-cart-body');
        if (body && html !== undefined) body.innerHTML = html;
    }

    function openMiniCart() {
        const el = document.getElementById('miniCart');
        if (el) bootstrap.Offcanvas.getOrCreateInstance(el).show();
    }

    function updateCartTotals(data) {
        const set = (sel, value) => document.querySelectorAll(sel).forEach((el) => { el.textContent = value; });
        set('.js-cart-subtotal', formatTaka(data.subtotal));
        set('.js-cart-discount', '-' + formatTaka(data.discount));
        set('.js-cart-bundle', '-' + formatTaka(data.bundle_discount));
        set('.js-cart-total', formatTaka(data.total));
        document.querySelectorAll('.js-discount-row').forEach((el) => el.classList.toggle('d-none', Number(data.discount) === 0));
        document.querySelectorAll('.js-bundle-row').forEach((el) => el.classList.toggle('d-none', Number(data.bundle_discount) === 0));
        updateCartCount(data);
        updateMiniCart(data.mini_cart_html);
        if (data.cart_count === 0 && document.querySelector('.js-cart-page')) window.location.reload();
    }

    // Show server-rendered Django messages.
    document.querySelectorAll('#toast-container .toast').forEach((el) => new bootstrap.Toast(el).show());

    // ---------- Image skeletons ----------
    function markLoaded(img) {
        const wrap = img.closest('.img-skeleton');
        if (wrap) wrap.classList.add('loaded');
    }
    function watchImages(root) {
        root.querySelectorAll('.img-skeleton img').forEach((img) => {
            if (img.complete) markLoaded(img);
            else {
                img.addEventListener('load', () => markLoaded(img), { once: true });
                img.addEventListener('error', () => markLoaded(img), { once: true });
            }
        });
    }
    watchImages(document);

    // ---------- Variant picker ----------
    function setupVariantForm(form) {
        if (!form || !form.dataset.variants || form.dataset.ready) return;
        form.dataset.ready = '1';
        const variants = JSON.parse(form.dataset.variants);
        const box = form.closest('.js-product-buy');
        const attrs = [...new Set([...form.querySelectorAll('.js-option')].map((o) => o.dataset.attr))];
        const scope = form.closest('.modal') || document;

        function selected() {
            const sel = {};
            attrs.forEach((a) => {
                const checked = form.querySelector('.js-option[data-attr="' + a + '"]:checked');
                if (checked) sel[a] = checked.value;
            });
            return sel;
        }

        function refresh() {
            const sel = selected();
            attrs.forEach((a) => {
                const label = form.querySelector('.js-opt-label[data-attr="' + a + '"]');
                if (label) label.textContent = sel[a] || 'Choose';
                // Grey out values that have no stock with the other current choices.
                form.querySelectorAll('.js-option[data-attr="' + a + '"]').forEach((opt) => {
                    const ok = variants.some((v) => v[a] === opt.value && v.stock > 0 &&
                        attrs.every((b) => b === a || !sel[b] || v[b] === sel[b]));
                    opt.nextElementSibling.classList.toggle('unavailable', !ok);
                });
            });
            const match = attrs.every((a) => sel[a]) ? variants.find((v) => attrs.every((a) => v[a] === sel[a])) : null;
            const button = form.querySelector('.js-add-btn');
            const label = form.querySelector('.js-add-label');
            const qty = form.querySelector('.js-qty');
            form.querySelector('.js-variant-id').value = match ? match.id : '';
            if (match) {
                box.querySelector('.js-price').textContent = match.price_display;
                const regular = box.querySelector('.js-regular');
                regular.textContent = match.regular_display;
                regular.classList.toggle('d-none', Number(match.price) >= Number(match.regular));
                const stockMsg = box.querySelector('.js-stock-msg .badge');
                if (match.stock <= 0) {
                    stockMsg.className = 'badge text-bg-secondary';
                    stockMsg.innerHTML = '<i class="bi bi-x-circle"></i> Out of stock';
                } else if (match.stock <= 5) {
                    stockMsg.className = 'badge text-bg-warning';
                    stockMsg.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Only ' + localizeDigits(match.stock) + ' left';
                } else {
                    stockMsg.className = 'badge text-bg-success';
                    stockMsg.innerHTML = '<i class="bi bi-check-circle"></i> In stock';
                }
                button.disabled = match.stock <= 0;
                label.textContent = match.stock > 0 ? 'Add to cart' : 'Out of stock';
                qty.max = match.stock;
                qty.disabled = match.stock <= 0;
            } else {
                button.disabled = true;
                label.textContent = 'Choose an option';
            }
            // Show the photo for the chosen colour, if there is one.
            if (sel.color) {
                const thumb = scope.querySelector('.js-gallery-thumb[data-color="' + CSS.escape(sel.color) + '"]');
                if (thumb) thumb.click();
            }
        }

        form.addEventListener('change', (e) => { if (e.target.closest('.js-option')) refresh(); });
        // Pre-select options that only have one value.
        attrs.forEach((a) => {
            const opts = form.querySelectorAll('.js-option[data-attr="' + a + '"]');
            if (opts.length === 1) opts[0].checked = true;
        });
        refresh();
    }
    document.querySelectorAll('.js-add-to-cart[data-variants]').forEach(setupVariantForm);

    // ---------- Gallery & zoom ----------
    document.addEventListener('click', (e) => {
        const thumb = e.target.closest('.js-gallery-thumb');
        if (!thumb) return;
        const gallery = thumb.closest('.js-gallery');
        const main = gallery.querySelector('.js-gallery-main');
        main.src = thumb.dataset.src;
        main.alt = thumb.dataset.alt || main.alt;
        gallery.querySelectorAll('.js-gallery-thumb').forEach((t) => t.classList.toggle('active', t === thumb));
    });

    document.querySelectorAll('.js-zoom').forEach((frame) => {
        const img = frame.querySelector('img');
        frame.addEventListener('mousemove', (e) => {
            const r = frame.getBoundingClientRect();
            frame.style.backgroundImage = 'url("' + img.currentSrc + '")';
            frame.style.backgroundPosition = ((e.clientX - r.left) / r.width * 100) + '% ' + ((e.clientY - r.top) / r.height * 100) + '%';
            frame.classList.add('zooming');
        });
        frame.addEventListener('mouseleave', () => frame.classList.remove('zooming'));
    });

    // ---------- Add to cart (AJAX + slide-out cart) ----------
    document.addEventListener('submit', async (e) => {
        const form = e.target.closest('.js-add-to-cart');
        if (!form) return;
        e.preventDefault();
        const button = form.querySelector('[type=submit]');
        button.disabled = true;
        try {
            const data = await postData(form.action, new FormData(form));
            if (data.needs_options && data.product_url) {
                window.location.href = data.product_url;
                return;
            }
            updateCartCount(data);
            updateMiniCart(data.mini_cart_html);
            const modal = form.closest('.modal');
            if (modal) bootstrap.Modal.getInstance(modal).hide();
            if (data.added) openMiniCart();
            showToast(data.message, data.level);
        } catch (err) {
            showToast('Something went wrong. Please try again.', 'error');
        } finally {
            button.disabled = false;
        }
    });

    // ---------- Cart page and mini cart: quantity / remove ----------
    async function setQuantity(row, quantity) {
        const data = await postData(row.dataset.updateUrl, {
            product_id: row.dataset.productId, variant_id: row.dataset.variantId || '', quantity: quantity,
        });
        if (data.quantity === 0) {
            row.remove();
        } else {
            row.querySelector('.js-qty-input').value = data.quantity;
            row.querySelector('.js-item-subtotal').textContent = formatTaka(data.item_subtotal);
            if (data.quantity < quantity) showToast('Only ' + localizeDigits(data.max_quantity) + ' in stock.', 'warning');
        }
        updateCartTotals(data);
    }

    document.addEventListener('click', async (e) => {
        const qtyBtn = e.target.closest('.js-qty-btn');
        if (qtyBtn) {
            const row = qtyBtn.closest('.js-cart-row');
            const input = row.querySelector('.js-qty-input');
            const next = Number(input.value) + Number(qtyBtn.dataset.step);
            if (next < 1) return;
            setQuantity(row, next).catch(() => showToast('Could not update cart.', 'error'));
            return;
        }

        const removeBtn = e.target.closest('.js-remove-item, .js-mini-remove');
        if (removeBtn) {
            const row = removeBtn.closest('.js-cart-row, .js-mini-row');
            const url = row.dataset.removeUrl || removeBtn.dataset.url;
            try {
                const data = await postData(url, { product_id: row.dataset.productId, variant_id: row.dataset.variantId || '' });
                document.querySelectorAll('.js-cart-row').forEach((r) => {
                    if (r.dataset.productId === row.dataset.productId && (r.dataset.variantId || '') === (row.dataset.variantId || '')) r.remove();
                });
                row.remove();
                updateCartTotals(data);
                showToast('Item removed from cart.', 'info');
            } catch (err) {
                showToast('Could not remove item.', 'error');
            }
            return;
        }

        const wishBtn = e.target.closest('.js-wishlist-toggle');
        if (wishBtn) {
            e.preventDefault();
            try {
                const data = await postData(wishBtn.dataset.url, {});
                wishBtn.querySelector('i').className = data.in_wishlist ? 'bi bi-heart-fill' : 'bi bi-heart';
                wishBtn.setAttribute('aria-pressed', data.in_wishlist);
                const label = wishBtn.querySelector('.js-wishlist-label');
                if (label) label.textContent = data.in_wishlist ? 'In wishlist' : 'Add to wishlist';
                showToast(data.in_wishlist ? 'Added to wishlist.' : 'Removed from wishlist.', 'success');
                if (!data.in_wishlist && wishBtn.dataset.removeCard) wishBtn.closest('.js-wishlist-item').remove();
            } catch (err) {
                if (err.message !== 'login required') showToast('Could not update wishlist.', 'error');
            }
            return;
        }

        const compareBtn = e.target.closest('.js-compare-toggle');
        if (compareBtn) {
            e.preventDefault();
            try {
                const data = await postData(compareBtn.dataset.url, {});
                compareBtn.classList.toggle('active', data.in_compare);
                compareBtn.setAttribute('aria-pressed', data.in_compare);
                const label = compareBtn.querySelector('.js-compare-label');
                if (label) label.textContent = data.in_compare ? 'In compare' : 'Compare';
                document.querySelectorAll('.js-compare-count').forEach((el) => {
                    el.textContent = localizeDigits(data.count);
                    el.classList.toggle('d-none', data.count === 0);
                });
                if (compareBtn.dataset.removeCol) { window.location.reload(); return; }
                showToast(data.message || (data.in_compare ? 'Added to compare.' : 'Removed from compare.'), data.message ? 'warning' : 'success');
            } catch (err) {
                showToast('Could not update compare list.', 'error');
            }
            return;
        }

        const alertBtn = e.target.closest('.js-price-alert');
        if (alertBtn) {
            try {
                const data = await postData(alertBtn.dataset.url, {});
                alertBtn.querySelector('i').className = data.active ? 'bi bi-bell-fill' : 'bi bi-bell';
                alertBtn.querySelector('.js-price-alert-label').textContent = data.active ? 'Price alert on' : 'Notify me if price drops';
                alertBtn.setAttribute('aria-pressed', data.active);
                showToast(data.message, 'success');
            } catch (err) {
                if (err.message !== 'login required') showToast('Could not update price alert.', 'error');
            }
            return;
        }

        const quickBtn = e.target.closest('.js-quick-view');
        if (quickBtn) {
            openQuickView(quickBtn.dataset.url);
            return;
        }

        const copyBtn = e.target.closest('.js-copy-link');
        if (copyBtn) {
            try {
                await navigator.clipboard.writeText(copyBtn.dataset.url);
                showToast('Link copied.', 'success');
            } catch (err) {
                window.prompt('Copy this link:', copyBtn.dataset.url);
            }
            return;
        }

        const themeBtn = e.target.closest('.js-theme-toggle');
        if (themeBtn) {
            const next = document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-bs-theme', next);
            try { localStorage.setItem('theme', next); } catch (err) { /* private mode */ }
            applyThemeIcon();
            return;
        }

        const digitsBtn = e.target.closest('.js-digits-toggle');
        if (digitsBtn) {
            const next = useBnDigits() ? 'en' : 'bn';
            document.cookie = 'digits=' + next + '; path=/; max-age=31536000; SameSite=Lax';
            window.location.reload();
        }
    });

    document.addEventListener('change', (e) => {
        const input = e.target.closest('.js-qty-input');
        if (!input) return;
        const qty = Math.max(1, parseInt(input.value, 10) || 1);
        setQuantity(input.closest('.js-cart-row'), qty).catch(() => showToast('Could not update cart.', 'error'));
    });

    // Refresh the mini cart when it opens (e.g. after using the back button).
    const miniCart = document.getElementById('miniCart');
    if (miniCart) {
        miniCart.addEventListener('show.bs.offcanvas', async () => {
            const body = miniCart.querySelector('.js-mini-cart-body');
            try {
                const response = await fetch(body.dataset.url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                if (response.ok) body.innerHTML = await response.text();
            } catch (err) { /* keep the server-rendered version */ }
        });
    }

    // ---------- Quick view ----------
    const QUICK_SKELETON = '<div class="row g-4 placeholder-glow" aria-busy="true"><div class="col-md-6"><div class="placeholder w-100 rounded-3" style="aspect-ratio:1"></div></div>' +
        '<div class="col-md-6"><span class="placeholder col-4"></span><span class="placeholder col-10 mt-2" style="height:1.6rem"></span>' +
        '<span class="placeholder col-12 mt-3"></span><span class="placeholder col-9"></span><span class="placeholder col-5 mt-3" style="height:2rem"></span>' +
        '<span class="placeholder col-12 mt-3" style="height:2.6rem"></span></div></div>';

    async function openQuickView(url) {
        const modalEl = document.getElementById('quickViewModal');
        const body = modalEl.querySelector('.js-quick-view-body');
        body.innerHTML = QUICK_SKELETON;
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
        try {
            const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            if (!response.ok) throw new Error(response.status);
            body.innerHTML = await response.text();
            body.querySelectorAll('.js-add-to-cart[data-variants]').forEach(setupVariantForm);
            body.querySelectorAll('.js-countdown').forEach(startCountdown);
            watchImages(body);
        } catch (err) {
            body.innerHTML = '<p class="text-center text-body-secondary py-5">Could not load this product. Please try again.</p>';
        }
    }

    // ---------- Countdown timers ----------
    function startCountdown(el) {
        if (el.dataset.started) return;
        el.dataset.started = '1';
        const end = new Date(el.dataset.end).getTime();
        const pad = (n) => localizeDigits(String(n).padStart(2, '0'));
        function tick() {
            let left = Math.max(0, Math.floor((end - Date.now()) / 1000));
            const h = Math.floor(left / 3600); left -= h * 3600;
            const m = Math.floor(left / 60);
            const s = left - m * 60;
            el.querySelector('.js-cd-h').textContent = pad(h);
            el.querySelector('.js-cd-m').textContent = pad(m);
            el.querySelector('.js-cd-s').textContent = pad(s);
            if (end - Date.now() <= 0) {
                clearInterval(timer);
                // The sale is over: reload once so normal prices show.
                if (!sessionStorage.getItem('flash-ended-' + el.dataset.end)) {
                    sessionStorage.setItem('flash-ended-' + el.dataset.end, '1');
                    setTimeout(() => window.location.reload(), 1500);
                }
            }
        }
        const timer = setInterval(tick, 1000);
        tick();
    }
    document.querySelectorAll('.js-countdown').forEach(startCountdown);

    // ---------- Live search suggestions ----------
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function highlight(text, query) {
        const safe = escapeHtml(text);
        const q = query.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return q ? safe.replace(new RegExp('(' + q + ')', 'ig'), '<mark>$1</mark>') : safe;
    }

    document.querySelectorAll('.js-search-form').forEach((form) => {
        const input = form.querySelector('.js-search-input');
        const box = form.querySelector('.js-search-suggest');
        let active = -1;
        let controller = null;

        const close = () => { box.hidden = true; active = -1; input.setAttribute('aria-expanded', 'false'); };

        const render = (data) => {
            if (input.value.trim() !== data.query) return;  // an older response
            if (!data.results.length) {
                box.innerHTML = '<div class="p-3 small text-body-secondary">No products match "' + escapeHtml(data.query) + '"</div>';
            } else {
                box.innerHTML = data.results.map((r, i) =>
                    '<a class="suggest-item" role="option" id="' + box.id + '-' + i + '" href="' + r.url + '">' +
                    '<img src="' + r.image + '" alt="" loading="lazy">' +
                    '<span class="flex-grow-1 small"><span class="d-block fw-semibold">' + highlight(r.title, data.query) + '</span>' +
                    '<span class="text-body-secondary">' + escapeHtml(r.subtitle) + '</span></span>' +
                    '<span class="text-end small"><span class="d-block fw-bold text-warning-emphasis">' + escapeHtml(r.price) + '</span>' +
                    (r.regular ? '<span class="price-old">' + escapeHtml(r.regular) + '</span>' : '') + '</span></a>'
                ).join('') + '<a class="suggest-item justify-content-center small fw-semibold border-top" href="' + form.action + '?q=' + encodeURIComponent(data.query) + '">See all results</a>';
            }
            box.hidden = false;
            input.setAttribute('aria-expanded', 'true');
        };

        const search = debounce(async () => {
            const q = input.value.trim();
            if (q.length < 2) { close(); return; }
            if (controller) controller.abort();
            controller = new AbortController();
            box.innerHTML = '<div class="p-3 placeholder-glow"><span class="placeholder col-8"></span><span class="placeholder col-6 mt-2"></span></div>';
            box.hidden = false;
            try {
                const response = await fetch(config.suggestUrl + '?q=' + encodeURIComponent(q), { signal: controller.signal });
                render(await response.json());
            } catch (err) {
                if (err.name !== 'AbortError') close();
            }
        }, 300);

        input.addEventListener('input', search);
        input.addEventListener('keydown', (e) => {
            const items = [...box.querySelectorAll('.suggest-item')];
            if (box.hidden || !items.length) return;
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                active = (active + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
                items.forEach((it, i) => it.classList.toggle('active', i === active));
                input.setAttribute('aria-activedescendant', items[active].id || '');
            } else if (e.key === 'Enter' && active >= 0) {
                e.preventDefault();
                window.location.href = items[active].href;
            } else if (e.key === 'Escape') {
                close();
            }
        });
        document.addEventListener('click', (e) => { if (!form.contains(e.target)) close(); });
    });

    // ---------- Infinite scroll ----------
    const grid = document.querySelector('.js-product-grid');
    const sentinel = document.querySelector('.js-infinite-sentinel');
    if (grid && sentinel && 'IntersectionObserver' in window) {
        const skeleton = document.querySelector('.js-grid-skeleton');
        const pagination = document.querySelector('.js-pagination');
        if (pagination) pagination.hidden = true;
        let loading = false;
        const observer = new IntersectionObserver(async (entries) => {
            if (!entries[0].isIntersecting || loading || !grid.dataset.nextUrl) return;
            loading = true;
            skeleton.hidden = false;
            try {
                const response = await fetch(grid.dataset.nextUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                const data = await response.json();
                const tmp = document.createElement('div');
                tmp.innerHTML = data.html;
                watchImages(tmp);
                grid.append(...tmp.children);
                if (data.next_url) grid.dataset.nextUrl = data.next_url;
                else { delete grid.dataset.nextUrl; observer.disconnect(); }
                if (window.AOS) AOS.refreshHard();
            } catch (err) {
                if (pagination) pagination.hidden = false;
                observer.disconnect();
            } finally {
                skeleton.hidden = true;
                loading = false;
            }
        }, { rootMargin: '400px' });
        observer.observe(sentinel);
    }

    // ---------- Checkout: division → district → upazila, live delivery cost ----------
    let geoPromise = null;
    const loadGeo = () => (geoPromise = geoPromise || fetch(config.geoUrl).then((r) => r.json()));

    function makeUpazilaSelect(input) {
        if (input.tagName === 'SELECT') return input;
        const select = document.createElement('select');
        select.name = input.name;
        select.id = input.id;
        select.className = 'form-select js-upazila';
        select.required = true;
        select.dataset.initial = input.value;
        input.replaceWith(select);
        return select;
    }

    async function setupAddressFields(container) {
        const district = container.querySelector('.js-district');
        const upazilaInput = container.querySelector('.js-upazila');
        if (!district || !upazilaInput) return;
        const geo = await loadGeo();
        const upazila = makeUpazilaSelect(upazilaInput);
        const division = container.querySelector('.js-division');
        const byDistrict = {};
        geo.divisions.forEach((dv) => dv.districts.forEach((d) => { byDistrict[d.name] = { division: dv.name, upazilas: d.upazilas }; }));

        function fillUpazilas() {
            const info = byDistrict[district.value];
            const keep = upazila.value || upazila.dataset.initial || '';
            upazila.innerHTML = '<option value="">' + (info ? 'Select upazila / thana' : 'Select district first') + '</option>';
            (info ? info.upazilas : []).forEach((u) => {
                const opt = new Option(u, u, false, u === keep);
                upazila.add(opt);
            });
            upazila.disabled = !info;
        }

        if (division) {
            geo.divisions.forEach((dv) => division.add(new Option(dv.name + ' (' + dv.bn + ')', dv.name)));
            const allDistricts = [...district.options].map((o) => [o.value, o.text]);
            if (byDistrict[district.value]) division.value = byDistrict[district.value].division;
            division.addEventListener('change', () => {
                const current = district.value;
                district.innerHTML = '';
                allDistricts.forEach(([value, text]) => {
                    if (!value || !division.value || (byDistrict[value] && byDistrict[value].division === division.value)) {
                        district.add(new Option(text, value, false, value === current));
                    }
                });
                if (district.value !== current) district.dispatchEvent(new Event('change'));
            });
            if (division.value) division.dispatchEvent(new Event('change'));
        }
        district.addEventListener('change', () => { upazila.dataset.initial = ''; upazila.value = ''; fillUpazilas(); });
        fillUpazilas();
    }
    document.querySelectorAll('form').forEach((f) => { if (f.querySelector('.js-district')) setupAddressFields(f); });

    const checkout = document.querySelector('.js-checkout');
    if (checkout) {
        const zones = JSON.parse(document.getElementById('delivery-zones').textContent);
        const district = document.getElementById('id_district');
        const gift = checkout.querySelector('.js-gift-wrap');
        const points = checkout.querySelector('.js-use-points');
        const cfg = checkout.dataset;
        const recalc = () => {
            let amount = Number(cfg.amount);
            const usePoints = points && points.checked;
            if (usePoints) amount -= Number(cfg.pointsDiscount);
            const zone = zones[district.value];
            let shipping = 0;
            if (zone && amount < Number(cfg.freeMin)) shipping = zone.charge;
            const giftCost = gift && gift.checked ? Number(cfg.giftWrap) : 0;
            document.querySelector('.js-shipping').textContent = zone ? (shipping === 0 ? 'Free' : formatTaka(shipping)) : 'Select district';
            document.querySelector('.js-grand-total').textContent = formatTaka(amount + shipping + giftCost);
            // These rows use d-flex, which beats the hidden attribute, so toggle d-none instead.
            checkout.querySelector('.js-gift-row').classList.toggle('d-none', !giftCost);
            checkout.querySelector('.js-points-row').classList.toggle('d-none', !usePoints);
            const estimate = checkout.querySelector('.js-delivery-estimate');
            estimate.hidden = !zone;
            if (zone) checkout.querySelector('.js-delivery-text').textContent = 'Delivery to ' + district.value + ' in ' + zone.time + (shipping === 0 ? ' · free delivery' : ' · ' + formatTaka(shipping));
        };
        [district, gift, points].forEach((el) => el && el.addEventListener('change', recalc));
        recalc();
    }

    // ---------- Notifications: mark all read without leaving the page ----------
    document.addEventListener('submit', async (e) => {
        const form = e.target.closest('.js-mark-read');
        if (!form) return;
        e.preventDefault();
        try {
            await postData(form.action, new FormData(form));
            document.querySelectorAll('.js-notif-badge').forEach((b) => b.remove());
            document.querySelectorAll('.notif-unread').forEach((n) => n.classList.remove('notif-unread'));
            form.remove();
        } catch (err) { form.submit(); }
    });

    // ---------- Newsletter ----------
    document.addEventListener('submit', async (e) => {
        const form = e.target.closest('.js-newsletter');
        if (!form) return;
        e.preventDefault();
        const msg = form.querySelector('.js-newsletter-msg');
        try {
            const data = await postData(form.action, new FormData(form));
            msg.textContent = data.message;
            msg.className = 'small mt-1 js-newsletter-msg ' + (data.ok ? 'text-success' : 'text-warning');
            if (data.ok) form.reset();
        } catch (err) {
            msg.textContent = 'Could not subscribe right now.';
        }
    });

    // ---------- Back to top ----------
    const topBtn = document.querySelector('.js-back-to-top');
    if (topBtn) {
        const toggle = () => { topBtn.hidden = window.scrollY < 600; };
        window.addEventListener('scroll', toggle, { passive: true });
        topBtn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
            document.getElementById('main-content').focus({ preventScroll: true });
        });
        toggle();
    }

    // ---------- Scroll animations ----------
    if (window.AOS) {
        AOS.init({ once: true, duration: 500, offset: 40, disable: () => window.matchMedia('(prefers-reduced-motion: reduce)').matches });
    }

    // ---------- PWA ----------
    if ('serviceWorker' in navigator && config.swUrl) {
        window.addEventListener('load', () => navigator.serviceWorker.register(config.swUrl, { scope: '/' }).catch(() => {}));
    }
})();
