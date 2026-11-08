(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var palette = [accent, accent2, muted, accent + '99', accent2 + '99'];
  var langs = ['仓颉 std+stdx', 'Go std', 'Rust std', 'Swift stdlib+corelibs', 'Kotlin stdlib'];

  function base(el) {
    return echarts.init(el, null, { renderer: 'svg' });
  }
  function axisCommon() {
    return {
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisTick: { show: false }
    };
  }

  // --- 图1 源码规模（万行） ---
  var c1 = base(document.getElementById('chart-loc'));
  c1.setOption({
    animation: false,
    grid: { left: 8, right: 16, top: 46, bottom: 8, containLabel: true },
    legend: { top: 0, textStyle: { color: muted, fontSize: 12 } },
    tooltip: { trigger: 'axis', appendToBody: true, valueFormatter: function(v){ return v + ' 万行'; } },
    xAxis: { type: 'category', data: langs, ...axisCommon(), splitLine: { show: false }, axisLabel: { color: ink, fontSize: 11, interval: 0 } },
    yAxis: { type: 'value', name: '万行', ...axisCommon() },
    series: [
      { name: '原始口径', type: 'bar', data: [24.2, 79.9, 95.8, 28.3, 14.0], itemStyle: { color: muted, opacity: .55 }, barMaxWidth: 34 },
      { name: '剔除生成代码', type: 'bar', data: [24.2, 63.9, 43.4, 28.3, 14.0], itemStyle: { color: accent }, barMaxWidth: 34,
        label: { show: true, position: 'top', color: ink, fontSize: 11, formatter: '{c}' } }
    ]
  });

  // --- 图2 顶层公开声明 ---
  var c2 = base(document.getElementById('chart-api'));
  c2.setOption({
    animation: false,
    grid: { left: 8, right: 16, top: 46, bottom: 8, containLabel: true },
    legend: { top: 0, textStyle: { color: muted, fontSize: 12 } },
    tooltip: { trigger: 'axis', appendToBody: true },
    xAxis: { type: 'category', data: langs, ...axisCommon(), splitLine: { show: false }, axisLabel: { color: ink, fontSize: 11, interval: 0 } },
    yAxis: { type: 'value', ...axisCommon() },
    series: [
      { name: '顶层公开声明（剔生成码）', type: 'bar', data: [1677, 6556, 6509, 1895, 8501], itemStyle: { color: accent2 }, barMaxWidth: 34,
        label: { show: true, position: 'top', color: ink, fontSize: 11, formatter: function(p){ return p.value > 10000 ? (p.value/1000).toFixed(1)+'k' : p.value; } } },
      { name: '其中：公开成员', type: 'bar', data: [7916, 18961, 8719, 7846, 20635], itemStyle: { color: accent2, opacity: .45 }, barMaxWidth: 34 }
    ]
  });

  // --- 图3 功能域覆盖数（堆叠） ---
  var c3 = base(document.getElementById('chart-cover'));
  c3.setOption({
    animation: false,
    grid: { left: 8, right: 20, top: 46, bottom: 8, containLabel: true },
    legend: { top: 0, textStyle: { color: muted, fontSize: 12 } },
    tooltip: { trigger: 'axis', appendToBody: true, valueFormatter: function(v){ return v + ' 个域'; } },
    xAxis: { type: 'category', data: langs, ...axisCommon(), splitLine: { show: false }, axisLabel: { color: ink, fontSize: 11, interval: 0 } },
    yAxis: { type: 'value', max: 31, ...axisCommon() },
    series: [
      { name: '完整', type: 'bar', stack: 'c', data: [24, 30, 14, 16, 15], itemStyle: { color: accent }, barMaxWidth: 40 },
      { name: '部分', type: 'bar', stack: 'c', data: [3, 1, 3, 9, 5], itemStyle: { color: '#D9A441' }, barMaxWidth: 40 },
      { name: '无', type: 'bar', stack: 'c', data: [4, 0, 14, 6, 11], itemStyle: { color: rule }, barMaxWidth: 40,
        label: { show: true, position: 'top', color: muted, fontSize: 11,
          formatter: function(p) { var d = [84, 98, 50, 66, 56]; return d[p.dataIndex] + '%'; } } }
    ]
  });

  // --- 图4 八维雷达 ---
  var dims = ['网络与通信', '安全与加密', '数据编码/序列化', '并发编程', '测试设施', '数学与数值', '文本与国际化', '系统接口'];
  var c4 = base(document.getElementById('chart-radar'));
  c4.setOption({
    animation: false,
    legend: { top: 0, textStyle: { color: muted, fontSize: 11.5 }, itemWidth: 14 },
    tooltip: { appendToBody: true },
    radar: {
      indicator: dims.map(function(d){ return { name: d, max: 10 }; }),
      center: ['50%', '56%'],
      radius: '62%',
      axisName: { color: ink, fontSize: 11.5 },
      splitLine: { lineStyle: { color: rule } },
      splitArea: { areaStyle: { color: [bg2, '#F2F4F7'] } },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'radar',
      data: [
        { name: '仓颉 std+stdx', value: [9, 8, 7, 9, 10, 9, 6, 8], lineStyle: { width: 2.5, color: accent }, itemStyle: { color: accent }, areaStyle: { color: accent, opacity: .18 } },
        { name: 'Go std', value: [10, 10, 10, 10, 9, 8, 7, 10], lineStyle: { width: 2, color: accent2 }, itemStyle: { color: accent2 }, areaStyle: { color: accent2, opacity: .08 } },
        { name: 'Rust std', value: [3, 1, 1, 8, 7, 8, 5, 8], lineStyle: { width: 1.5, color: muted }, itemStyle: { color: muted } },
        { name: 'Swift', value: [6, 2, 7, 9, 7, 6, 9, 7], lineStyle: { width: 1.5, color: accent2 + '88' }, itemStyle: { color: accent2 + '88' } },
        { name: 'Kotlin', value: [4, 2, 5, 7, 5, 6, 8, 6], lineStyle: { width: 1.5, color: accent + '88' }, itemStyle: { color: accent + '88' } }
      ]
    }]
  });

  [c1, c2, c3, c4].forEach(function(c) {
    window.addEventListener('resize', function() { c.resize(); });
  });
})();
