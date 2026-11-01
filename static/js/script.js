(function () {
    'use strict';

    function getCookie(name) {
        const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
        return match ? decodeURIComponent(match[2]) : null;
    }

    function formatTaka(value) {
        const n = Number(value);
        const opts = Number.isInteger(n) ? {} : { minimumFractionDigits: 2, maximumFractionDigits: 2 };
        return '৳' + n.toLocaleString('en-US', opts);
    }

    async function postData(url, data) {
        const body = data instanceof FormData ? data : new URLSearchParams(data);
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: body,
        });
        if (response.status === 401) {
            window.location.href = '/accounts/login/?next=' + encodeURIComponent(window.location.pathname);
            throw new Error('login required');
        }
        if (!response.ok) throw new Error('Request failed: ' + response.status);
        return response.json();
    }

    function showToast(message, level) {
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

    function updateCartCount(count) {
        document.querySelectorAll('.js-cart-count').forEach((el) => { el.textContent = count; });
    }

    function updateCartTotals(data) {
        const set = (sel, value) => document.querySelectorAll(sel).forEach((el) => { el.textContent = value; });
        set('.js-cart-subtotal', formatTaka(data.subtotal));
        set('.js-cart-discount', '-' + formatTaka(data.discount));
        set('.js-cart-total', formatTaka(data.total));
        document.querySelectorAll('.js-discount-row').forEach((el) => {
            el.classList.toggle('d-none', Number(data.discount) === 0);
        });
        updateCartCount(data.cart_count);
        if (data.cart_count === 0 && document.querySelector('.js-cart-page')) {
            window.location.reload();
        }
    }

    // Show server-rendered Django messages.
    document.querySelectorAll('#toast-container .toast').forEach((el) => new bootstrap.Toast(el).show());

    // Add to cart without leaving the page.
    document.addEventListener('submit', async (e) => {
        const form = e.target.closest('.js-add-to-cart');
        if (!form) return;
        e.preventDefault();
        const button = form.querySelector('[type=submit]');
        button.disabled = true;
        try {
            const data = await postData(form.action, new FormData(form));
            updateCartCount(data.cart_count);
            showToast(data.message, data.level);
        } catch (err) {
            showToast('Something went wrong. Please try again.', 'error');
        } finally {
            button.disabled = false;
        }
    });

    // Cart page: change quantity / remove item.
    async function setQuantity(row, quantity) {
        const data = await postData(row.dataset.updateUrl, { product_id: row.dataset.productId, quantity: quantity });
        if (data.quantity === 0) {
            row.remove();
        } else {
            row.querySelector('.js-qty-input').value = data.quantity;
            row.querySelector('.js-item-subtotal').textContent = formatTaka(data.item_subtotal);
            if (data.quantity < quantity) {
                showToast('Only ' + data.max_quantity + ' in stock.', 'warning');
            }
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

        const removeBtn = e.target.closest('.js-remove-item');
        if (removeBtn) {
            const row = removeBtn.closest('.js-cart-row');
            try {
                const data = await postData(row.dataset.removeUrl, { product_id: row.dataset.productId });
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
                const icon = wishBtn.querySelector('i');
                icon.className = data.in_wishlist ? 'bi bi-heart-fill' : 'bi bi-heart';
                wishBtn.setAttribute('aria-pressed', data.in_wishlist);
                const label = wishBtn.querySelector('.js-wishlist-label');
                if (label) label.textContent = data.in_wishlist ? 'In wishlist' : 'Add to wishlist';
                showToast(data.in_wishlist ? 'Added to wishlist.' : 'Removed from wishlist.', 'success');
                if (!data.in_wishlist && wishBtn.dataset.removeCard) {
                    wishBtn.closest('.js-wishlist-item').remove();
                }
            } catch (err) {
                if (err.message !== 'login required') showToast('Could not update wishlist.', 'error');
            }
        }
    });

    document.addEventListener('change', (e) => {
        const input = e.target.closest('.js-qty-input');
        if (!input) return;
        const qty = Math.max(1, parseInt(input.value, 10) || 1);
        setQuantity(input.closest('.js-cart-row'), qty).catch(() => showToast('Could not update cart.', 'error'));
    });

    // Checkout: live shipping cost by district.
    const checkout = document.querySelector('.js-checkout');
    if (checkout) {
        const district = document.getElementById('id_district');
        const cfg = checkout.dataset;
        const recalc = () => {
            const amount = Number(cfg.amount);
            let shipping = 0;
            if (district.value && amount < Number(cfg.freeMin)) {
                shipping = district.value === 'Dhaka' ? Number(cfg.inside) : Number(cfg.outside);
            }
            document.querySelector('.js-shipping').textContent =
                district.value ? (shipping === 0 ? 'Free' : formatTaka(shipping)) : 'Select district';
            document.querySelector('.js-grand-total').textContent = formatTaka(amount + shipping);
        };
        district.addEventListener('change', recalc);
        recalc();
    }
})();
