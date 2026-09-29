/* Presentation layer for the redesigned workspace. The market/data engine lives in app.js. */
(function () {
  var key = 'qd-studio-filter';
  var allowed = ['all', 'buy', 'fav', 'idx', 'act'];
  var activeFilter = localStorage.getItem(key) || 'all';
  if (allowed.indexOf(activeFilter) < 0) activeFilter = 'all';

  function applyFilter() {
    flt = { buy: false, fav: false, idx: false, act: false };
    if (activeFilter === 'all') flt = { buy: true, fav: true, idx: true, act: true };
    else flt[activeFilter] = true;
  }

  applyFilter();
  var focusCode = null;
  var focusRange = 'y1';
  var focusJobs = {};
  var focusFailed = {};
  var benchmarkAttempted = false;
  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }
  function requestFocusData(code) {
    if (!fundHist[code] && !focusJobs[code] && !focusFailed[code]) {
      focusJobs[code] = true;
      ensureHist(code).then(function () { delete focusJobs[code]; renderFocus(); })
        .catch(function () { delete focusJobs[code]; focusFailed[code] = true; renderFocus(); });
    }
    if (!benchmarkRows && !benchmarkAttempted) {
      benchmarkAttempted = true;
      loadBenchmark().then(renderFocus).catch(renderFocus);
    }
  }
  function renderFocus() {
    var f = funds.filter(function (item) { return item.code === focusCode; })[0] || funds[0];
    if (!f) return;
    focusCode = f.code;
    var h = fundHist[f.code];
    function ytdOf(item) {
      if (typeof item.ytd === 'number' && isFinite(item.ytd)) return item.ytd;
      var series = fundHist[item.code] || fundSeriesCache[item.code];
      return series && series.period && typeof series.period.JN === 'number' ? series.period.JN : null;
    }
    document.getElementById('metricFunds').textContent = funds.length;
    document.getElementById('metricBuyable').textContent = funds.filter(buyable).length;
    var leaders = funds.filter(function (item) { return ytdOf(item) !== null; })
      .sort(function (a, b) { return ytdOf(b) - ytdOf(a); });
    var complete = leaders.length === funds.length;
    document.getElementById('metricLeaderLabel').textContent = complete ? '年内表现领先' : '已统计基金最高';
    document.getElementById('metricLeader').textContent = leaders.length ? fmtPct(ytdOf(leaders[0])) : '--';
    document.getElementById('metricLeaderName').textContent = (leaders.length ? leaders[0].name : '等待净值数据')
      + (complete ? '' : ' · 已统计 ' + leaders.length + '/' + funds.length);
    document.getElementById('metricNavDate').textContent = f.navDate ? f.navDate.slice(5).replace('-', '.') : '--';
    document.getElementById('focusName').textContent = f.name;
    document.getElementById('focusMeta').textContent = f.code + ' · 最新净值 ' + (f.nav || '--') + ' · ' + (f.navDate || '待更新');
    document.getElementById('focusYtd').textContent = fmtPct(ytdOf(f));
    document.getElementById('focusYtd').className = cls(ytdOf(f));
    document.getElementById('focusRanges').innerHTML = RANGES.map(function (item) {
      return '<button type="button" class="focus-range' + (item[0] === focusRange ? ' on' : '') + '" aria-pressed="' + (item[0] === focusRange) + '" onclick="selectFocusRange(\'' + item[0] + '\')">' + item[1] + '</button>';
    }).join('');
    var watch = funds.slice(0, 4);
    document.getElementById('watchCount').textContent = '/ ' + watch.length;
    document.getElementById('watchList').innerHTML = watch.map(function (item) {
      return '<button type="button" class="watch-row' + (item.code === focusCode ? ' selected' : '') + '" onclick="selectFocus(\'' + item.code + '\')">'
        + '<span><strong>' + escapeHtml(item.name) + '</strong><small>' + escapeHtml(item.code) + ' · 净值 ' + escapeHtml(item.nav || '--') + '</small></span>'
        + '<b class="' + cls(ytdOf(item)) + '">' + fmtPct(ytdOf(item)) + '</b></button>';
    }).join('');
    var chart = document.getElementById('focusChart');
    if (h && h.nav && h.nav.length > 1 && benchmarkRows) {
      var count = (RANGES.filter(function (item) { return item[0] === focusRange; })[0] || RANGES[4])[2];
      chart.innerHTML = comparisonChartSvg(h.nav.slice(-count), benchmarkRows);
    } else if (focusFailed[f.code]) {
      chart.innerHTML = '<div class="hm-empty">基金历史净值暂不可用。<button type="button" class="retry-btn" onclick="retryFocus()">重试</button></div>';
    } else if (benchmarkError) {
      chart.innerHTML = '<div class="hm-empty">沪深300历史行情暂不可用。<button type="button" class="retry-btn" onclick="retryFocus()">重试</button></div>';
    } else {
      chart.innerHTML = '<div class="hm-empty">正在加载基金与沪深300的同期走势…</div>';
    }
    requestFocusData(f.code);
  }
  window.selectFocus = function (code) { focusCode = code; renderFocus(); };
  window.selectFocusRange = function (range) { focusRange = range; renderFocus(); };
  window.retryFocus = function () { delete focusFailed[focusCode]; benchmarkAttempted = false; renderFocus(); };
  syncFilterUi = function () {
    var ids = { all: 'ckAll', buy: 'ckBuy', fav: 'ckFav', idx: 'ckIdx', act: 'ckAct' };
    Object.keys(ids).forEach(function (name) {
      var el = document.getElementById(ids[name]);
      if (!el) return;
      var selected = name === activeFilter;
      el.classList.toggle('on', selected);
      el.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
  };
  toggleFilter = function (name) {
    if (allowed.indexOf(name) < 0) return;
    activeFilter = name;
    localStorage.setItem(key, name);
    applyFilter();
    syncFilterUi();
    renderHome();
  };

  var baseRenderHome = renderHome;
  renderHome = function () {
    baseRenderHome();
    var count = document.querySelectorAll('#list > .card').length;
    var target = document.getElementById('fundCount');
    if (target) target.textContent = count + ' 只';
    renderFocus();
  };

  var labels = {
    home: ['基金总览', '每一个数字，都有来处。', '净值、估值与累计表现，放在一张清晰的画布上。'],
    etf: ['场内 ETF', '观察交易价格与溢价。', '比较跨境 ETF 的场内价格、涨跌幅与最新净值。'],
    mkt: ['全球行情', '市场变化，一目了然。', '关注 A 股、港股、美股及全球主要市场指数。'],
    mine: ['关于与设置', '让每一次观察都有依据。', '了解估值口径、数据来源与使用注意事项。']
  };
  var baseSetView = setView;
  setView = function (view) {
    var search = document.getElementById('kw');
    if (search) { search.blur(); search.value = ''; }
    document.getElementById('results').style.display = 'none';
    baseSetView(view);
    var copy = labels[view] || labels.home;
    document.getElementById('sectionCrumb').textContent = copy[0];
    document.getElementById('pageTitle').textContent = copy[1];
    document.getElementById('pageDescription').textContent = copy[2];
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  renderMine = function () {
    document.getElementById('mineCard').innerHTML =
      '<b>QD 观察台</b><br>' +
      '估值根据公开披露持仓与个股行情加权计算，并应用仓位系数。实际净值以基金公司披露为准。<br>' +
      '行情来源：腾讯行情、CNBC；基金净值、持仓与申购状态来源：天天基金公开数据。<br>' +
      '公开持仓存在披露时差；申购限额可能临时变更，交易前请核对基金公司最新公告。<br>' +
      '当前预置基金：' + FUNDS_DEFAULT.length + ' 只。自选与排序保存在本机浏览器。<br>' +
      '<span class="btn" onclick="resetAll()">恢复默认基金列表</span><br>' +
      '本工具仅供信息参考，不构成投资建议。';
  };

  var date = new Date();
  document.getElementById('dateLabel').textContent = date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' });
  syncFilterUi();
  renderHome();
})();
