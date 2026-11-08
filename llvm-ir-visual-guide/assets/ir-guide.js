/* assets/ir-guide.js — mermaid init for LLVM IR visual guide */
(function () {
  var style = getComputedStyle(document.documentElement);
  var ink = style.getPropertyValue('--ink').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var accent = style.getPropertyValue('--accent').trim();

  if (window.mermaid) {
    mermaid.initialize({
      startOnLoad: true,
      theme: 'neutral',
      securityLevel: 'loose',
      fontFamily: "'Outfit','PingFang SC','Microsoft YaHei',sans-serif",
      themeVariables: {
        primaryColor: '#ffffff',
        primaryTextColor: ink,
        primaryBorderColor: accent,
        lineColor: muted,
        fontSize: '14px'
      },
      flowchart: { curve: 'basis', htmlLabels: true, padding: 10 }
    });
  }
})();
