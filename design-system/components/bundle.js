/* @ds-bundle: {"format":4,"namespace":"Thermal","components":[{"name":"Paper"},{"name":"HeaderBar"},{"name":"Masthead"},{"name":"SectionLabel"},{"name":"Rule"},{"name":"HazardTape"},{"name":"TearLine"},{"name":"Fill"},{"name":"Leaders"},{"name":"TaskRow"},{"name":"Checkbox"},{"name":"Step"},{"name":"LogList"},{"name":"Tag"},{"name":"Transition"},{"name":"Severity"},{"name":"Callout"},{"name":"Quote"},{"name":"StatTiles"},{"name":"BarList"},{"name":"Columns"},{"name":"CellGrid"},{"name":"DiffGlyph"},{"name":"NoteLines"},{"name":"BoxRow"},{"name":"QRSlot"},{"name":"TextMode"},{"name":"Image"}]} */
(function () {
  var R = window.React, h = R.createElement;
  function cx() { return Array.prototype.filter.call(arguments, Boolean).join(' '); }
  function rest(p, omit) { var o = {}; for (var k in p) if (omit.indexOf(k) < 0 && k !== 'children') o[k] = p[k]; return o; }

  /* Split a whole number of pixels into n whole-pixel parts (remainder goes to the first parts). */
  function split(total, n) { var b = Math.floor(total / n), r = total - b * n, o = []; for (var i = 0; i < n; i++) o.push(b + (i < r ? 1 : 0)); return o; }
  var PAPER = 384;

  /* ---------- Paper ---------- */
  function Paper(p) {
    var cls = cx('rp-paper', p.feed !== false && 'rp-feed', p.print && 'rp-print', p.className);
    var props = Object.assign(rest(p, ['feed', 'print', 'className']), { className: cls });
    if (p.print) return h('div', Object.assign({ id: 'receipt' }, props), p.children);
    return h('div', { className: 'rp-stage' }, h('div', props, p.children));
  }

  /* ---------- Structure ---------- */
  function HeaderBar(p) {
    return h('div', { className: cx('rp-bar', p.outline && 'rp-outline'), style: p.style },
      h('span', null, p.left), p.right != null ? h('span', null, p.right) : null);
  }
  var MAST = { xl: 'display-xl', lg: 'display-lg', md: 'display-md' };
  function Masthead(p) {
    var aside = p.aside;
    if (Array.isArray(aside)) aside = aside.map(function (l, i) { return h('div', { key: i }, l); });
    return h(R.Fragment, null,
      h('div', { className: 'rp-mast' },
        h('div', { className: MAST[p.size || 'lg'], style: { textWrap: 'balance' } }, p.title),
        aside ? h('div', { className: 'rp-mast-aside' }, aside) : null),
      p.sub ? h('div', { className: 'rp-mast-sub' }, p.sub) : null,
      p.rule === false ? null : h('div', { className: 'rp-rule rp-rule-bar', style: { marginBottom: 4 } }));
  }
  function SectionLabel(p) { return h('div', { className: 'rp-label', style: p.style }, p.children); }
  function Rule(p) {
    return h('div', { className: cx('rp-rule', 'rp-rule-' + (p.weight || 'rule')), style: p.style, role: 'separator' });
  }
  function HazardTape(p) { return h('div', { className: 'rp-hazard rp-fill-hazard', style: Object.assign({ height: p.height || 40 }, p.style) }); }
  function TearLine(p) { return h('div', { className: 'rp-tear' }, h('span', null, p.label == null ? 'TEAR' : p.label)); }
  function Fill(p) {
    return h('div', { className: 'rp-fill-' + (p.pattern || 'tone-50'), style: Object.assign({ width: p.width || '100%', height: p.height || 40, boxSizing: 'border-box', border: p.frame ? '3px solid #000' : 0 }, p.style) }, p.children);
  }

  /* ---------- Rows ---------- */
  function Leaders(p) {
    return h('div', { className: 'rp-leaders' }, (p.rows || []).map(function (r, i) {
      return h('div', { className: 'rp-leader', key: i },
        h('span', null, r[0]), h('span', { className: 'rp-leader-dots' }), h('span', { className: 'rp-leader-v' }, r[1]));
    }));
  }
  function Checkbox(p) { return p.checked ? h('div', { className: 'rp-box rp-checked' }, '✓') : h('div', { className: 'rp-box' }); }
  function TaskRow(p) {
    return h('div', { className: cx('rp-task', p.done && 'rp-done') },
      h(Checkbox, { checked: p.done }),
      h('div', { className: 'rp-task-body' },
        h('div', { className: 'rp-task-t' }, p.title),
        p.meta ? h('div', { className: 'rp-task-m' }, p.meta) : null),
      p.tag ? h(Tag, null, p.tag) : null);
  }
  function Step(p) {
    return h('div', { className: 'rp-step' },
      h('div', { className: 'rp-step-n rp-d' }, p.n),
      h('div', { className: 'rp-step-body' },
        h('div', null, p.children),
        p.timer ? h('div', { className: 'rp-step-timer' }, h('i'), p.timer) : null));
  }
  function LogList(p) {
    return h('div', { className: 'rp-log' }, (p.rows || []).map(function (r, i) {
      return h('div', { className: 'rp-log-row', key: i },
        h('span', { className: 'rp-log-t', style: p.timeWidth ? { width: p.timeWidth } : null }, r[0]), h('span', { className: 'rp-log-x' }, r[1]));
    }));
  }

  /* ---------- Signals ---------- */
  function Tag(p) { return h('span', { className: cx('rp-tag', p.variant === 'outline' && 'rp-outline') }, p.children); }
  function Transition(p) {
    return h('div', { className: 'rp-trans' },
      h('div', { className: 'rp-trans-a' }, p.from), h('div', { className: 'rp-trans-arrow' }, '→'), h('div', { className: 'rp-trans-b' }, p.to));
  }
  function Severity(p) {
    return h('div', { className: 'rp-sev' },
      h('div', { style: { display: 'flex', flexDirection: 'column' } },
        h('span', { className: 'rp-sev-k' }, p.kicker || 'SEV'), h('span', { className: 'display-mega' }, p.level)),
      h('div', { className: 'rp-sev-side' }, (p.lines || []).map(function (l, i) { return h('span', { key: i, style: i === 0 ? { fontSize: 23 } : null }, l); })));
  }
  function Callout(p) {
    if (p.value != null) {
      return h('div', { className: 'rp-callout rp-split' },
        h('span', { className: 'rp-callout-l' }, p.label), h('span', { className: 'display-md' }, p.value));
    }
    return h('div', { className: 'rp-callout' }, h('div', { className: 'rp-callout-l' }, p.label), h('div', { className: 'rp-callout-x' }, p.children));
  }
  function Quote(p) {
    return h('div', null, h('div', { className: 'rp-quote-mark' }, '“'),
      h('div', { style: { lineHeight: '26px', textWrap: 'pretty' } }, p.children),
      p.by ? h('div', { className: 'rp-quote-by' }, '— ' + p.by) : null);
  }

  /* ---------- Data ---------- */
  function StatTiles(p) {
    var items = p.items || [], cols = p.columns || Math.min(items.length, 3) || 1, rows = Math.ceil(items.length / cols);
    var tracks = split((p.width || PAPER) - 8, cols).map(function (w) { return w + 'px'; }).join(' ');
    return h('div', { className: 'rp-tiles', style: { gridTemplateColumns: tracks } }, items.map(function (t, i) {
      var c = i % cols, r = Math.floor(i / cols);
      var st = { borderRightWidth: c < cols - 1 ? 4 : 0, borderBottomWidth: r < rows - 1 ? 4 : 0 };
      var lab = t.label ? h('div', { className: 'rp-tile-l', key: 'l' }, t.label) : null;
      var val = h('div', { className: cx('rp-tile-v', 'rp-d'), key: 'v', style: p.small ? { fontSize: 42, lineHeight: '42px' } : null }, t.value);
      var note = t.note ? h('div', { className: 'rp-tile-n', key: 'n' }, t.note) : null;
      return h('div', { className: cx('rp-tile', t.inverted && 'rp-inv'), key: i, style: st },
        p.valueFirst ? [val, lab, note] : [lab, val, note]);
    }));
  }
  function clamp01(v) { return Math.max(0, Math.min(1, v || 0)); }
  function BarList(p) {
    var tone = p.tone || 'tone-50', lw = p.labelWidth || 76, vw = 52;
    var track = (p.width || PAPER) - lw - vw - 24;
    function px(v) { return Math.round(clamp01(v) * track); }
    return h('div', null,
      h('div', { className: 'rp-bars' }, (p.rows || []).map(function (r, i) {
        var solidA = r.solid !== false;
        return h('div', { className: 'rp-barrow', key: i, style: { gridTemplateColumns: lw + 'px ' + track + 'px ' + vw + 'px' } },
          h('span', { className: 'rp-barrow-l' }, r.label),
          h('div', { className: 'rp-barpair' },
            h('div', { className: cx('rp-bar-a', !solidA && 'rp-fill-' + tone), style: { width: px(r.a), border: solidA ? 0 : '2px solid #000' } }),
            r.b != null ? h('div', { className: 'rp-bar-b rp-fill-' + tone, style: { width: px(r.b) } }) : null,
            p.marker != null ? h('div', { className: 'rp-mark', style: { left: px(p.marker) } }) : null),
          h('span', { className: 'rp-barrow-v' }, r.value));
      })),
      p.legend ? h('div', { className: 'rp-legend' },
        h('span', null, h('i', { className: 'rp-sw rp-fill-solid', style: { border: 0, width: 24, height: 16 } }), p.legend[0]),
        p.legend[1] ? h('span', null, h('i', { className: 'rp-sw rp-fill-' + tone, style: { width: 24, height: 16 } }), p.legend[1]) : null) : null);
  }
  function Columns(p) {
    var data = p.data || [], H = p.height || 180, max = Math.max.apply(null, data.map(function (d) { return d.value; }).concat([1]));
    var ws = split((p.width || PAPER) - 10 * Math.max(0, data.length - 1), Math.max(1, data.length));
    return h('div', null,
      h('div', { className: 'rp-cols', style: { height: H + 40 } }, data.map(function (d, i) {
        var t = d.tone || (d.dither ? 'tone-50' : null);
        return h('div', { className: 'rp-col', key: i, style: { width: ws[i] } }, h('span', null, d.label2 != null ? d.label2 : d.value),
          h('div', { className: cx('rp-col-bar', t && 'rp-fill-' + t), style: { height: Math.round(d.value / max * H), border: t ? '2px solid #000' : 0 } }));
      })),
      h('div', { className: 'rp-cols-x' }, data.map(function (d, i) { return h('span', { key: i, style: { width: ws[i] } }, d.label); })));
  }
  var CELL = { empty: '', light: 'rp-fill-tone-35', tone: 'rp-fill-tone-65', solid: 'rp-solid', dither: 'rp-fill-tone-65', dot: 'rp-fill-tone-35' };
  function CellGrid(p) {
    var w = p.cellWidth || 11, hh = p.cellHeight || 22;
    var gap = p.gap == null ? 3 : p.gap;
    function cells(list) {
      var gaps = null;
      if (p.spread && list.length > 1) gaps = split((p.width || PAPER) - (p.labelWidth === 0 ? 0 : (p.labelWidth || 44)) - list.length * w, list.length - 1);
      return list.map(function (s, i) {
        return h('div', { key: i, className: cx('rp-cell', CELL[s] || ''), style: { width: w, height: hh, marginRight: i < list.length - 1 ? (gaps ? gaps[i] : gap) : 0 } });
      });
    }
    return h('div', null,
      p.ticks ? h('div', { style: { display: 'flex', justifyContent: 'space-between', paddingLeft: p.labelWidth === 0 ? 0 : (p.labelWidth || 44), fontSize: 14, fontWeight: 700, marginBottom: 6 } },
        p.ticks.map(function (t, i) { return h('span', { key: i }, t); })) : null,
      h('div', { className: 'rp-grid', style: p.rowGap != null ? { gap: p.rowGap } : null }, (p.rows || []).map(function (r, i) {
        var list = typeof r.cells === 'string' ? r.cells.split('').map(function (c) { return { '1': 'solid', '0': 'empty', '-': 'light', '~': 'tone' }[c] || 'empty'; }) : r.cells;
        return h('div', { key: i, className: 'rp-grid-row', style: p.labelWidth === 0 ? { flexDirection: 'column', alignItems: 'stretch', gap: 6 } : null },
          r.label != null ? h('span', { className: 'rp-grid-l', style: p.labelWidth === 0 ? { width: 'auto', display: 'flex', justifyContent: 'space-between', fontSize: 17 } : (p.labelWidth ? { width: p.labelWidth } : null) },
            r.label, p.labelWidth === 0 && r.right != null ? h('span', null, r.right) : null) : null,
          h('div', { className: 'rp-grid-cells', style: { gap: 0 } }, cells(list)));
      })),
      p.legend ? h('div', { className: 'rp-legend' }, p.legend.map(function (l, i) {
        return h('span', { key: i }, h('i', { className: cx('rp-sw', CELL[l[0]] || '', l[0] === 'solid' && 'rp-fill-solid'), style: l[0] === 'solid' ? { border: 0 } : null }), l[1]);
      })) : null);
  }
  function DiffGlyph(p) {
    var a = p.added || 0, d = p.removed || 0, n = Math.max(1, Math.min(4, Math.round(5 * a / ((a + d) || 1))));
    var sq = []; for (var i = 0; i < 5; i++) sq.push(h('i', { key: i, className: i < n ? 'rp-add' : 'rp-del rp-fill-tone-65' }));
    return h('div', { className: 'rp-diff', title: '+' + a + ' −' + d }, sq);
  }

  /* ---------- Pen & paper ---------- */
  function NoteLines(p) { var l = []; for (var i = 0; i < (p.count || 4); i++) l.push(h('div', { key: i })); return h('div', { className: 'rp-lines' }, l); }
  function BoxRow(p) {
    var n = p.count || 6, cols = p.columns || n, gap = 12, size = Math.floor(((p.width || PAPER) - gap * (cols - 1)) / cols), l = [];
    for (var i = 0; i < n; i++) l.push(h('div', { key: i, className: i < (p.filled || 0) ? 'rp-fill-solid' : null, style: { width: size, height: size } }));
    return h('div', { className: 'rp-boxes', style: { flexWrap: 'wrap' } }, l);
  }
  /* QR from a module matrix (array of '1'/'0' strings), drawn on whole dots. */
  function QRCode(p) {
    var ref = R.useRef(null), m = p.matrix || [], mod = p.module || 3, q = p.quiet == null ? 4 : p.quiet, n = m.length, size = (n + 2 * q) * mod;
    R.useEffect(function () {
      var c = ref.current; if (!c) return; var g = c.getContext('2d');
      g.fillStyle = '#fff'; g.fillRect(0, 0, size, size); g.fillStyle = '#000';
      for (var y = 0; y < n; y++) for (var x = 0; x < n; x++) if (m[y][x] === '1') g.fillRect((x + q) * mod, (y + q) * mod, mod, mod);
    }, [p.matrix, mod, q]);
    return h('canvas', { ref: ref, width: size, height: size, className: 'rp-qr-code', style: { width: size, height: size }, role: 'img', 'aria-label': p.alt || 'QR code' });
  }
  function QRSlot(p) {
    var s = p.size || 120, slot;
    if (p.matrix) slot = h(QRCode, { matrix: p.matrix, module: p.module, quiet: p.quiet });
    else if (p.src) slot = h('img', { src: p.src, width: s, height: s, className: 'rp-image', style: { width: s, height: s, flex: 'none' }, alt: 'QR' });
    else slot = h('div', { className: 'rp-qr-slot rp-fill-tone-15', style: { width: s, height: s } }, h('span', null, 'QR'));
    return h('div', { className: 'rp-qr' }, slot,
      p.lines ? h('div', { className: 'rp-qr-x' }, p.lines.map(function (l, i) { return h('div', { key: i }, l); })) : null);
  }
  function TextMode(p) {
    return h('div', { className: 'rp-textmode' }, (p.lines || []).map(function (l, i) {
      if (l && typeof l === 'object') {
        var txt = l.text != null ? l.text : l.inverse, dbl = l.double || l.inverse != null, inv = l.inverse != null || l.reverse;
        return h('div', { key: i, className: cx(dbl && 'rp-tm-double', inv && 'rp-tm-inv') }, String(txt).slice(0, dbl ? 16 : 32));
      }
      return h('div', { key: i }, String(l).slice(0, 32));
    }));
  }

  /* Image — a plain picture on whole pixels; the print pipeline dithers it. */
  function Image(p) {
    var width = Math.round(p.width || PAPER), st = R.useState(p.height ? Math.round(p.height) : null), hgt = st[0], setH = st[1];
    function onLoad(e) { if (!p.height) { var im = e.target; setH(Math.round(im.naturalHeight * width / im.naturalWidth)); } }
    return h('figure', { style: { margin: 0 } },
      h('img', { src: p.src, alt: p.alt || '', width: width, height: hgt || undefined, onLoad: onLoad, className: 'rp-image', style: { width: width, height: hgt || 'auto' } }),
      p.caption ? h('figcaption', { className: 'rp-image-cap' }, p.caption) : null);
  }

  window.Thermal = Object.assign(window.Thermal || {}, {
    Paper: Paper, HeaderBar: HeaderBar, Masthead: Masthead, SectionLabel: SectionLabel, Rule: Rule, HazardTape: HazardTape, TearLine: TearLine, Fill: Fill,
    Leaders: Leaders, TaskRow: TaskRow, Checkbox: Checkbox, Step: Step, LogList: LogList,
    Tag: Tag, Transition: Transition, Severity: Severity, Callout: Callout, Quote: Quote,
    StatTiles: StatTiles, BarList: BarList, Columns: Columns, CellGrid: CellGrid, DiffGlyph: DiffGlyph,
    NoteLines: NoteLines, BoxRow: BoxRow, QRSlot: QRSlot, TextMode: TextMode, Image: Image
  });
})();
