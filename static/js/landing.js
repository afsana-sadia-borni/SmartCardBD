// Landing page (/) effects: sticky nav shadow, rotating category names, count-up numbers,
// step timeline, product rail arrows and a gentle mouse parallax in the hero.
(function () {
    'use strict';

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const BN = '০১২৩৪৫৬৭৮৯';

    // Nav gets a blurred background once the page scrolls.
    const nav = document.querySelector('.js-lx-nav');
    if (nav) {
        const onScroll = () => nav.classList.toggle('is-scrolled', window.scrollY > 10);
        window.addEventListener('scroll', onScroll, { passive: true });
        onScroll();
    }

    // "Trending now: <category>" cycles through the categories.
    const words = document.querySelector('.js-lx-words');
    if (words && !reduceMotion) {
        const items = Array.from(words.children);
        let current = 0;
        if (items.length > 1) {
            words.style.minWidth = Math.max(...items.map((el) => el.offsetWidth)) + 'px';
            setInterval(() => {
                const prev = items[current];
                current = (current + 1) % items.length;
                prev.classList.remove('is-active');
                prev.classList.add('is-leaving');
                items[current].classList.remove('is-leaving');
                items[current].classList.add('is-active');
                setTimeout(() => prev.classList.remove('is-leaving'), 500);
            }, 2400);
        }
    }

    // Numbers count up when they scroll into view (keeping Bangla digits if the page uses them).
    function countUp(el) {
        const target = parseInt(el.dataset.to, 10);
        if (!target || reduceMotion) return;
        const bangla = /[০-৯]/.test(el.textContent);
        const format = (n) => {
            const text = String(n);
            return bangla ? text.replace(/[0-9]/g, (d) => BN[d]) : text;
        };
        const duration = 1400;
        const start = performance.now();
        const step = (now) => {
            const t = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - t, 3);
            el.textContent = format(Math.round(target * eased));
            if (t < 1) requestAnimationFrame(step);
        };
        el.textContent = format(0);
        requestAnimationFrame(step);
    }

    if ('IntersectionObserver' in window) {
        const counter = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                countUp(entry.target);
                counter.unobserve(entry.target);
            });
        }, { threshold: 0.6 });
        document.querySelectorAll('.js-count').forEach((el) => counter.observe(el));

        const steps = document.querySelector('.js-lx-steps');
        if (steps) {
            const stepObserver = new IntersectionObserver((entries) => {
                if (entries[0].isIntersecting) {
                    steps.classList.add('is-visible');
                    stepObserver.disconnect();
                }
            }, { threshold: 0.3 });
            stepObserver.observe(steps);
        }
    } else {
        document.querySelectorAll('.js-lx-steps').forEach((el) => el.classList.add('is-visible'));
    }

    // Product rail arrows.
    const rail = document.querySelector('.js-lx-rail');
    if (rail) {
        const by = (dir) => {
            const card = rail.firstElementChild;
            const width = card ? card.getBoundingClientRect().width + 20 : 300;
            rail.scrollBy({ left: dir * width * 2, behavior: reduceMotion ? 'auto' : 'smooth' });
        };
        document.querySelector('.js-lx-prev')?.addEventListener('click', () => by(-1));
        document.querySelector('.js-lx-next')?.addEventListener('click', () => by(1));
    }

    // Hero parallax: the devices, bags and notes drift with the mouse (mouse users only).
    const hero = document.querySelector('.js-lx-hero');
    if (hero && !reduceMotion && window.matchMedia('(pointer: fine)').matches) {
        const layers = hero.querySelectorAll('.js-depth');
        let frame = null;
        hero.addEventListener('pointermove', (e) => {
            if (frame) return;
            frame = requestAnimationFrame(() => {
                frame = null;
                const rect = hero.getBoundingClientRect();
                const x = (e.clientX - rect.left) / rect.width - 0.5;
                const y = (e.clientY - rect.top) / rect.height - 0.5;
                layers.forEach((el) => {
                    const depth = parseFloat(el.dataset.depth) || 10;
                    el.style.setProperty('--px', (-x * depth).toFixed(1) + 'px');
                    el.style.setProperty('--py', (-y * depth).toFixed(1) + 'px');
                });
            });
        });
        hero.addEventListener('pointerleave', () => {
            layers.forEach((el) => { el.style.setProperty('--px', '0px'); el.style.setProperty('--py', '0px'); });
        });
    }
})();
