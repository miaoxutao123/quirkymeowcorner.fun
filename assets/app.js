/* 怪猫角落 · 交互层
   原则：JS 只做增强，不做承载。关掉 JS，内容和导航必须照常可用。 */
(function () {
  'use strict';

  var root = document.documentElement;

  /* ---- 1. 明暗主题 ---- */
  // 首屏之前已经由内联脚本定过一次，这里只负责切换和记忆
  var btn = document.getElementById('themeBtn');
  function current() {
    var set = root.getAttribute('data-theme');
    if (set) return set;
    return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function apply(mode) {
    root.setAttribute('data-theme', mode);
    try { localStorage.setItem('theme', mode); } catch (e) {}
    if (btn) btn.setAttribute('aria-pressed', mode === 'dark' ? 'true' : 'false');
  }
  if (btn) {
    btn.setAttribute('aria-pressed', current() === 'dark' ? 'true' : 'false');
    btn.addEventListener('click', function () {
      apply(current() === 'dark' ? 'light' : 'dark');
    });
  }

  /* ---- 2. 滚动进场 ---- */
  // 关键：先把 html 标记为 js，CSS 才敢把内容初始设成透明。
  // 之前直接在 CSS 里写 [data-reveal]{opacity:0}，结果 JS 一旦没跑成
  // （禁用、报错、无头浏览器回调不触发），内容就永久不可见。
  // 现在的顺序是：默认可见 → JS 可用才加动画 → 进入视野才真正显示。
  root.classList.add('js');

  var reveals = document.querySelectorAll('[data-reveal]');
  if (reveals.length && 'IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add('in');
          io.unobserve(en.target);
        }
      });
    }, { rootMargin: '120px 0px', threshold: 0 });
    reveals.forEach(function (el) { io.observe(el); });

    // 兜底：1.2 秒内还没进场的，直接显示。
    // 无头浏览器、极短视口、观察器行为异常时都会走到这里。
    setTimeout(function () {
      reveals.forEach(function (el) { el.classList.add('in'); });
    }, 1200);
  } else {
    reveals.forEach(function (el) { el.classList.add('in'); });
  }

  /* ---- 3. 代码块复制 ---- */
  document.querySelectorAll('.prose pre').forEach(function (pre) {
    var wrap = document.createElement('div');
    wrap.className = 'pre-wrap';
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);

    var b = document.createElement('button');
    b.className = 'copy-btn';
    b.type = 'button';
    b.textContent = '复制';
    b.addEventListener('click', function () {
      var code = pre.querySelector('code');
      var text = code ? code.innerText : pre.innerText;
      navigator.clipboard.writeText(text).then(function () {
        b.textContent = '已复制';
        b.classList.add('done');
        setTimeout(function () {
          b.textContent = '复制';
          b.classList.remove('done');
        }, 1600);
      }).catch(function () { b.textContent = '复制失败'; });
    });
    wrap.appendChild(b);
  });

  /* ---- 4. 日历格悬停气泡 ---- */
  var tip = document.createElement('div');
  tip.className = 'cal-tip';
  tip.setAttribute('aria-hidden', 'true');
  document.body.appendChild(tip);

  var calCells = document.querySelectorAll('.cal .cell[data-info]');
  calCells.forEach(function (c) {
    c.addEventListener('mouseenter', function () {
      var info = c.getAttribute('data-info');
      if (!info) return;
      tip.innerHTML = info;
      tip.classList.add('show');
    });
    c.addEventListener('mousemove', function (e) {
      var pad = 12;
      var r = tip.getBoundingClientRect();
      var x = e.clientX + pad;
      var y = e.clientY - r.height - pad;
      if (x + r.width > innerWidth - 8) x = e.clientX - r.width - pad;
      if (y < 8) y = e.clientY + pad;
      tip.style.transform = 'translate(' + x + 'px,' + y + 'px)';
    });
    c.addEventListener('mouseleave', function () {
      tip.classList.remove('show');
    });
  });

  /* ---- 5. 栏目页筛选 ---- */
  var filterBar = document.getElementById('filterBar');
  if (filterBar) {
    var cards = [].slice.call(document.querySelectorAll('[data-tags]'));
    filterBar.addEventListener('click', function (e) {
      var chip = e.target.closest('.chip');
      if (!chip) return;
      var tag = chip.getAttribute('data-tag');
      filterBar.querySelectorAll('.chip').forEach(function (c) {
        c.classList.toggle('on', c === chip);
      });
      cards.forEach(function (card) {
        var tags = (card.getAttribute('data-tags') || '').split('|');
        var show = !tag || tag === '*' || tags.indexOf(tag) !== -1;
        card.classList.toggle('hide', !show);
      });
      // 没有可见卡片时给一句提示
      var visible = cards.filter(function (c) { return !c.classList.contains('hide'); }).length;
      var empty = document.getElementById('filterEmpty');
      if (empty) empty.classList.toggle('show', visible === 0);
    });
  }

  /* ---- 6. 当前页高亮导航 ---- */
  var path = location.pathname.replace(/\/index\.html$/, '/');
  document.querySelectorAll('.nav a').forEach(function (a) {
    var href = a.getAttribute('href');
    if (href && href !== '/' && path.indexOf(href) === 0) a.classList.add('on');
  });
})();
