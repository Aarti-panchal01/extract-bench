/* extract-bench site. Every number drawn here comes from data/site.json (geometry)
   and data/display.json (3-decimal strings rounded from the full-precision result files). */
(function () {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";
  var ORDER = ["readability-lxml", "trafilatura (best-config)", "trafilatura", "html2text",
    "bs4-naive", "markdownify", "justext"];
  var NAME = {
    "readability-lxml": "readability-lxml", "trafilatura (best-config)": "trafilatura (best-config)",
    "trafilatura": "trafilatura", "html2text": "html2text", "bs4-naive": "bs4-naive",
    "markdownify": "markdownify", "justext": "jusText"
  };
  var SHORT = {
    "readability-lxml": "readability", "trafilatura (best-config)": "trafilatura tuned",
    "trafilatura": "trafilatura", "html2text": "html2text", "bs4-naive": "bs4-naive",
    "markdownify": "markdownify", "justext": "jusText"
  };
  var TINY = {};
  Object.keys(SHORT).forEach(function (k) { TINY[k] = SHORT[k]; });
  TINY["trafilatura (best-config)"] = "traf. tuned";
  // color follows the entity, never its rank
  var STYLE = {
    "readability-lxml": { c: "var(--s-read)", strong: true },
    "trafilatura (best-config)": { c: "var(--s-traf)", strong: true },
    "trafilatura": { c: "var(--s-traf)", hollow: true },
    "html2text": { c: "var(--s-other)" },
    "bs4-naive": { c: "var(--s-other)" },
    "markdownify": { c: "var(--s-other)" },
    "justext": { c: "var(--s-jus)", strong: true }
  };
  var TAX_LABELS = ["crash", "empty_output", "low_recall", "over_extraction", "nav_or_footer_leak",
    "consent_or_modal_leak", "related_or_teaser_leak", "comment_or_signature_leak",
    "script_or_noscript_leak", "commerce_or_listing_leak", "table_lost", "code_lost",
    "code_flattened", "title_wrong"];

  var S, D; // site.json, display.json

  /* ---------------- helpers ---------------- */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function h(tag, attrs, parent, text) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "class") e.className = attrs[k];
      else if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]);
    }
    if (text !== undefined && text !== null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function s(tag, attrs, parent, text) {
    var e = document.createElementNS(NS, tag);
    if (attrs) for (var k in attrs) if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]);
    if (text !== undefined && text !== null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function svg(container, w, hgt, label) {
    var root = s("svg", { viewBox: "0 0 " + w + " " + hgt, width: w, height: hgt, role: "img", "aria-label": label });
    container.appendChild(root);
    return root;
  }
  // Python-style rounding: an exact tie (like 0.125) goes to the even digit, as "%.2f" does
  function pyRound(x, d) {
    var m = Math.pow(10, d), v = x * m, fl = Math.floor(v), diff = v - fl;
    var n = Math.abs(diff - 0.5) < 1e-9 ? (fl % 2 === 0 ? fl : fl + 1) : Math.round(v);
    return (n / m).toFixed(d);
  }
  function f3(x) { return pyRound(x, 3); }
  function f2(x) { return pyRound(x, 2); }
  function ciText(c) { return c.mean + " [" + c.lo + ", " + c.hi + "]"; }
  function pairText(p) { return p.diff + " [" + p.lo + ", " + p.hi + "]"; }
  function scale(d0, d1, r0, r1) { return function (v) { return r0 + (v - d0) / (d1 - d0) * (r1 - r0); }; }
  function textW(str, px) { return str.length * px * 0.56; }
  function lab(t) { return t.replace(/_/g, " "); }

  // one tooltip for the whole page; content set with textContent only
  var tip;
  function tipShow(lines, x, y) {
    tip.textContent = "";
    lines.forEach(function (ln, i) { h(i === 0 ? "b" : "span", null, tip, ln); if (i > 0 && i < lines.length - 1) tip.appendChild(document.createElement("br")); });
    tip.classList.add("on");
    var r = tip.getBoundingClientRect();
    var left = Math.min(window.innerWidth - r.width - 8, Math.max(8, x + 12));
    var top = y - r.height - 12;
    if (top < 8) top = y + 16;
    tip.style.left = left + "px"; tip.style.top = top + "px";
  }
  function tipHide() { tip.classList.remove("on"); }
  function bindTip(node, lines, focusable) {
    node.setAttribute("data-tip", "");
    node.addEventListener("pointermove", function (e) { tipShow(lines, e.clientX, e.clientY); });
    node.addEventListener("pointerleave", tipHide);
    if (focusable) {
      node.setAttribute("tabindex", "0");
      node.setAttribute("aria-label", lines.join(", "));
      node.addEventListener("focus", function () { var r = node.getBoundingClientRect(); tipShow(lines, r.left + r.width / 2, r.top); });
      node.addEventListener("blur", tipHide);
    }
  }

  // redraw a chart whenever its container width changes
  function mount(container, draw) {
    var last = -1;
    function run() {
      var w = Math.floor(container.clientWidth);
      if (!w || w === last) return;
      last = w;
      container.textContent = "";
      draw(container, w);
    }
    if ("ResizeObserver" in window) new ResizeObserver(run).observe(container);
    else window.addEventListener("resize", run);
    run();
    return function () { last = -1; run(); };
  }

  function dot(g, x, y, r, ex, extra) {
    var st = STYLE[ex];
    var c = s("circle", { cx: x, cy: y, r: r }, g);
    c.setAttribute("style", st.hollow
      ? "fill:var(--paper);stroke:" + st.c + ";stroke-width:2"
      : "fill:" + st.c + ";stroke:var(--paper);stroke-width:2");
    if (extra) for (var k in extra) c.setAttribute(k, extra[k]);
    return c;
  }

  /* ---------------- rank slope chart (Figures 1 and 5) ---------------- */

  function sliceOrders() {
    return [
      { key: "synthetic", label: "Synthetic", sub: "40 test pages", subShort: "40 pages", order: S.wikipedia.rank.synthetic_order, f1: rowMap("synthetic") },
      { key: "wikipedia", label: "Wikipedia", sub: S.wikipedia.n_pages + " articles", subShort: S.wikipedia.n_pages + " pages", order: S.wikipedia.rank.real_order, f1: rowMap("wikipedia") },
      { key: "zyte", label: "Zyte", sub: S.zyte.n_pages + " pages, " + S.zyte.n_sites + " sites", subShort: S.zyte.n_pages + " pages", order: S.zyte.rank.zyte_order, f1: rowMap("zyte") }
    ];
  }
  function rowMap(slice) {
    var m = {};
    S[slice].rows.forEach(function (r) { m[r.extractor] = r; });
    return m;
  }

  function drawSlope(container, w, big) {
    var cols = sliceOrders();
    var compact = w < 560;
    var names = w < 360 ? TINY : compact ? SHORT : NAME;
    var fs = compact ? 11 : 12;
    var showVals = big && !compact;
    var labelW = 0;
    ORDER.forEach(function (ex) { labelW = Math.max(labelW, textW(names[ex], fs)); });
    labelW = Math.ceil(labelW) + (showVals ? 44 : 0) + 16;
    var rowH = big ? (compact ? 30 : 38) : 25;
    var top = big ? 54 : 46, n = ORDER.length;
    var H = top + rowH * (n - 1) + 22;
    var x0 = labelW, x2 = w - labelW, x1 = (x0 + x2) / 2;
    var xs = [x0, x1, x2];
    var root = svg(container, w, H, "Rank of each extractor by mean F1 in three slices: synthetic, Wikipedia and Zyte. jusText is last on synthetic, first on Wikipedia and fourth on Zyte.");
    var g = s("g", null, root);

    cols.forEach(function (c, i) {
      var anchor = i === 0 ? "middle" : i === 2 ? "middle" : "middle";
      s("text", { x: xs[i], y: 14, "text-anchor": anchor, class: "t-strong", "font-size": compact ? 11 : 12 }, g, c.label);
      s("text", { x: xs[i], y: 29, "text-anchor": anchor, class: "t-muted", "font-size": 10.5 }, g, big && w >= 620 ? c.sub : c.subShort);
      s("line", { x1: xs[i], x2: xs[i], y1: top - 8, y2: H - 12, class: "grid" }, g);
    });

    function yOf(ci, ex) { return top + cols[ci].order.indexOf(ex) * rowH; }

    var drawOrder = ORDER.slice().sort(function (a, b) { return (STYLE[a].strong ? 1 : 0) - (STYLE[b].strong ? 1 : 0); });
    drawOrder.forEach(function (ex) {
      var st = STYLE[ex];
      var pts = cols.map(function (c, i) { return [xs[i], yOf(i, ex)]; });
      var d = "M" + pts.map(function (p) { return p[0] + "," + p[1]; }).join("L");
      var focus = ex === "justext";
      var p = s("path", { d: d, fill: "none", "stroke-linejoin": "round", "stroke-linecap": "round" }, g);
      p.setAttribute("style", "stroke:" + st.c + ";stroke-width:" + (focus ? (big ? 3 : 2.5) : st.strong ? 2 : 1.5) +
        ";opacity:" + (st.strong ? 1 : st.hollow ? 0.7 : 0.55));
      if (big) {
        var len = Math.ceil(p.getTotalLength ? p.getTotalLength() : 600);
        p.setAttribute("class", "draw");
        p.style.setProperty("--len", len);
      }
      cols.forEach(function (c, i) {
        var r = c.f1[ex];
        var disp = D[c.key].rows[ex].f1;
        var grp = s("g", null, g);
        s("circle", { cx: xs[i], cy: pts[i][1], r: 12, fill: "transparent" }, grp);
        dot(grp, xs[i], pts[i][1], focus ? 5 : 4, ex);
        bindTip(grp, [disp.mean, NAME[ex] + ", " + c.label + ", rank " + (c.order.indexOf(ex) + 1) + " of 7", "95% CI " + disp.lo + " to " + disp.hi], big);
        if (big && focus && i === 1 && !compact) {
          s("text", { x: xs[i] - 11, y: pts[i][1] + 4, "text-anchor": "end", class: "t-strong halo", "font-size": 12 }, g, "first, " + disp.mean);
        }
      });
      // end labels
      var yl = pts[0][1], yr = pts[2][1];
      var tl = s("text", { x: x0 - 10, y: yl + 4, "text-anchor": "end", "font-size": fs, class: focus || st.strong ? "t-ink" : "" }, g,
        names[ex] + (showVals ? "  " + D.synthetic.rows[ex].f1.mean : ""));
      var tr = s("text", { x: x2 + 10, y: yr + 4, "text-anchor": "start", "font-size": fs, class: focus || st.strong ? "t-ink" : "" }, g,
        (showVals ? D.zyte.rows[ex].f1.mean + "  " : "") + names[ex]);
      if (focus) { tl.setAttribute("font-weight", "600"); tr.setAttribute("font-weight", "600"); }
    });
  }

  /* ---------------- forest plot (Figure 2) ---------------- */

  function drawForest(container, w, mode) {
    var compact = w < 560;
    var rows = ORDER.map(function (ex) {
      var r = S.synthetic.rows.filter(function (x) { return x.extractor === ex; })[0];
      var c = mode === "nolist" ? S.synthetic.no_listing[ex] : r.f1;
      var dsp = mode === "nolist" ? D.synthetic.no_listing[ex] : D.synthetic.rows[ex].f1;
      return { ex: ex, c: c, d: dsp };
    }).sort(function (a, b) { return b.c.mean - a.c.mean; });

    var names = compact ? SHORT : NAME;
    var labelW = compact ? 112 : 196;
    var valW = compact ? 0 : 150;
    var rowH = compact ? 44 : 36;
    var top = 10, H = top + rowH * rows.length + 30;
    var xl = labelW, xr = w - valW - (compact ? 14 : 8);
    var x = scale(0.4, 1.0, xl, xr);
    var root = svg(container, w, H, "Mean F1 with 95% intervals for seven extractors on " + (mode === "nolist" ? "36 synthetic test pages without listing pages" : "40 synthetic test pages"));
    var g = s("g", null, root);
    var step = compact ? 0.2 : 0.1;
    for (var t = 0.4; t <= 1.0001; t += step) {
      s("line", { x1: x(t), x2: x(t), y1: top - 4, y2: H - 26, class: "grid" }, g);
      s("text", { x: x(t), y: H - 10, "text-anchor": "middle", class: "t-muted", "font-size": 11 }, g, t.toFixed(1));
    }
    s("text", { x: xr, y: H - 10, "text-anchor": "end", class: "t-muted", "font-size": 11, dx: valW ? 0 : 0, dy: 0 }, g, "");

    // overlap of the top two intervals
    var a = rows[0], b = rows[1];
    var oLo = Math.max(a.c.lo, b.c.lo), oHi = Math.min(a.c.hi, b.c.hi);
    var yA = top + rowH * 0.5, yB = top + rowH * 1.5;
    if (oHi > oLo) {
      var band = s("rect", { x: x(oLo), y: yA - 12, width: Math.max(2, x(oHi) - x(oLo)), height: yB - yA + 24 }, g);
      band.setAttribute("style", "fill:var(--accent);opacity:0.13");
    }
    // bracket + annotation in the empty left part of the plot
    var bx = x(Math.min(a.c.lo, b.c.lo)) - 10;
    if (!compact) s("path", { d: "M" + (bx + 5) + "," + yA + "H" + bx + "V" + yB + "H" + (bx + 5), fill: "none", style: "stroke:var(--accent);stroke-width:1.25" }, g);
    var note = mode === "nolist" ? ["Top two: +0.020, not significant", "either way of resampling"] : ["Top two: significant over pages,", "not over page types (Figure 3)"];
    if (!compact) {
      s("text", { x: bx - 8, y: yA + 8, "text-anchor": "end", "font-size": 11.5, style: "fill:var(--accent)" }, g, note[0]);
      s("text", { x: bx - 8, y: yA + 23, "text-anchor": "end", "font-size": 11.5, style: "fill:var(--accent)" }, g, note[1]);
    }

    rows.forEach(function (r, i) {
      var y = top + rowH * (i + 0.5);
      var st = STYLE[r.ex];
      var grp = s("g", null, g);
      s("rect", { x: 0, y: y - rowH / 2, width: w, height: rowH, fill: "transparent" }, grp);
      var ln = s("line", { x1: x(r.c.lo), x2: x(r.c.hi), y1: y, y2: y, "stroke-linecap": "round" }, grp);
      ln.setAttribute("style", "stroke:" + st.c + ";stroke-width:2");
      dot(grp, x(r.c.mean), y, 5.5, r.ex);
      var t1 = s("text", { x: 0, y: compact ? y - 3 : y + 4, "font-size": compact ? 11.5 : 13, class: "t-ink" }, grp, names[r.ex]);
      if (r.ex === "justext") t1.setAttribute("font-weight", "600");
      if (compact) s("text", { x: 0, y: y + 12, "font-size": 11, class: "t-muted" }, grp, r.d.mean + " [" + r.d.lo + ", " + r.d.hi + "]");
      else {
        s("text", { x: w, y: y + 4, "text-anchor": "end", "font-size": 12, class: "t-ink" }, grp, r.d.mean);
        s("text", { x: w - 40, y: y + 4, "text-anchor": "end", "font-size": 11, class: "t-muted" }, grp, "[" + r.d.lo + ", " + r.d.hi + "]");
      }
      bindTip(grp, [r.d.mean, NAME[r.ex] + ", mean F1", "95% CI " + r.d.lo + " to " + r.d.hi], true);
    });
    if (compact) {
      // annotation below in compact mode
      s("text", { x: xl, y: H + 0, "font-size": 10.5, style: "fill:var(--accent)" }, g, "");
    }
  }

  /* ---------------- paired interval plot (Figures 3, 7, 9) ---------------- */

  function drawIntervals(container, w, rows, opt) {
    var rowH = 66, top = 4;
    var H = top + rows.length * rowH + 28;
    var pad = 4;
    var x = scale(opt.d0, opt.d1, pad + 6, w - pad - 6);
    var root = svg(container, w, H, opt.label);
    var g = s("g", null, root);
    var ticks = opt.ticks(w);
    rows.forEach(function (r, i) {
      var yb = top + i * rowH + 38, ye = top + (i + 1) * rowH + (i === rows.length - 1 ? 0 : 0);
      ticks.forEach(function (t) { s("line", { x1: x(t), x2: x(t), y1: yb, y2: ye, class: "grid" }, g); });
      if (opt.zero !== undefined) s("line", { x1: x(opt.zero), x2: x(opt.zero), y1: yb, y2: ye, class: "zero" }, g);
    });
    s("line", { x1: x(opt.d0), x2: x(opt.d1), y1: H - 24, y2: H - 24, class: "axis" }, g);
    ticks.forEach(function (t) {
      s("text", { x: x(t), y: H - 8, "text-anchor": "middle", class: "t-muted", "font-size": 11 }, g, opt.fmtTick(t));
    });
    rows.forEach(function (r, i) {
      var y0 = top + i * rowH;
      var grp = s("g", null, g);
      s("rect", { x: 0, y: y0, width: w, height: rowH, fill: "transparent" }, grp);
      s("text", { x: 0, y: y0 + 16, "font-size": 13, class: "t-strong halo" }, grp, r.label);
      var v = s("text", { x: 0, y: y0 + 32, "font-size": 12, class: "t-ink halo" }, grp, r.value);
      var vd = s("tspan", { class: r.sig ? "t-ink" : "t-muted", dx: 8 }, v, r.verdict);
      if (r.sig && !r.plain) vd.setAttribute("font-weight", "600");
      // paper plate behind the two label lines so grid and zero lines never run through text
      try {
        var t1 = grp.childNodes[1], b1 = t1.getBBox(), b2 = v.getBBox();
        var plate = s("rect", { x: -2, y: Math.min(b1.y, b2.y) - 2, width: Math.max(b1.width, b2.width) + 8, height: (b2.y + b2.height) - Math.min(b1.y, b2.y) + 4 });
        plate.setAttribute("style", "fill:var(--paper)");
        grp.insertBefore(plate, t1);
      } catch (e) { /* getBBox unavailable: the text halo still separates text from lines */ }
      var y = y0 + 50;
      var col = r.sig ? "var(--ink)" : "var(--muted)";
      var ln = s("line", { x1: x(r.lo), x2: x(r.hi), y1: y, y2: y }, grp);
      ln.setAttribute("style", "stroke:" + col + ";stroke-width:2.5");
      [r.lo, r.hi].forEach(function (e) {
        var tk = s("line", { x1: x(e), x2: x(e), y1: y - 6, y2: y + 6 }, grp);
        tk.setAttribute("style", "stroke:" + col + ";stroke-width:2");
      });
      var c = s("circle", { cx: x(r.mid), cy: y, r: 5 }, grp);
      c.setAttribute("style", "fill:" + (r.sig ? "var(--accent)" : "var(--paper)") + ";stroke:" + (r.sig ? "var(--paper)" : "var(--ink-2)") + ";stroke-width:2");
      bindTip(grp, [r.value, r.label, r.verdict], true);
    });
  }

  function diffTicks(d0, d1) {
    return function (w) {
      var step = w < 420 ? 0.1 : 0.05, out = [];
      for (var t = Math.ceil(d0 / step) * step; t <= d1 + 1e-9; t += step) out.push(Math.round(t * 1000) / 1000);
      return out;
    };
  }
  function signed(t) { return (t > 0 ? "+" : t < 0 ? "−" : "") + Math.abs(t).toFixed(2); }

  /* ---------------- strip plots (Figure 6) ---------------- */

  function rng(seed) { var x = seed >>> 0; return function () { x = (x * 1664525 + 1013904223) >>> 0; return x / 4294967296; }; }

  function drawStrips(container, w) {
    var slices = [
      { key: "synthetic", label: "Synthetic", sub: "40 test pages", strip: S.synthetic.strip, empt: function (ex) { return (S.synthetic.taxonomy[ex] || {}).empty_output || 0; }, op: 0.5 },
      { key: "wikipedia", label: "Wikipedia", sub: "40 articles", strip: S.wikipedia.strip, empt: function (ex) { return S.wikipedia.empties[ex]; }, op: 0.5 },
      { key: "zyte", label: "Zyte", sub: "181 pages, 126 sites", strip: S.zyte.strip, empt: function (ex) { return S.zyte.empties[ex]; }, op: 0.3 }
    ];
    var wide = w >= 720;
    var names = wide ? NAME : TINY;
    var rowH = 34, head = 40, axisH = 22, gap = wide ? 40 : 0;
    var labelW = wide ? 168 : 92;
    var panelH = head + rowH * ORDER.length + axisH;
    var H = wide ? panelH : panelH * 3 + 28 * 2;
    var root = svg(container, w, H, "Per-page F1 for each extractor in each of the three slices, one dot per page, with mean and 95% interval.");
    var panelW = wide ? (w - labelW - gap * 2) / 3 : w - labelW - 8;
    slices.forEach(function (sl, si) {
      var ox = wide ? labelW + si * (panelW + gap) : labelW;
      var oy = wide ? 0 : si * (panelH + 28);
      var g = s("g", { transform: "translate(0," + oy + ")" }, root);
      var x = scale(0, 1, ox + 4, ox + panelW - 4);
      s("text", { x: ox + 4, y: 14, class: "t-strong", "font-size": 12.5 }, g, sl.label);
      s("text", { x: ox + 4, y: 29, class: "t-muted", "font-size": 10.5 }, g, sl.sub);
      [0, 0.25, 0.5, 0.75, 1].forEach(function (t) {
        s("line", { x1: x(t), x2: x(t), y1: head - 2, y2: head + rowH * ORDER.length, class: "grid" }, g);
        if (wide && si > 0 && t === 0) return;
        if (t === 0 || t === 0.5 || t === 1 || panelW > 260)
          s("text", { x: x(t), y: head + rowH * ORDER.length + 15, "text-anchor": "middle", class: "t-muted", "font-size": 10.5 }, g, t === 0 || t === 1 ? String(t) : t.toFixed(2).replace(/0$/, ""));
      });
      var rows = S[sl.key].rows;
      ORDER.forEach(function (ex, i) {
        var yc = head + rowH * (i + 0.5) - 3;
        if (si === 0 || !wide) {
          var tl = s("text", { x: 0, y: yc + 4, "font-size": wide ? 12.5 : 11.5, class: "t-ink" }, g, names[ex]);
          if (ex === "justext") tl.setAttribute("font-weight", "600");
        }
        var st = STYLE[ex];
        var r = rng(17 + i * 31 + si * 7);
        var vals = sl.strip[ex] || [];
        var dg = s("g", null, g);
        vals.forEach(function (v) {
          var c = s("circle", { cx: x(v), cy: yc + (r() - 0.5) * 16, r: 2.4 }, dg);
          c.setAttribute("style", "fill:" + st.c + ";opacity:" + sl.op);
        });
        var row = rows.filter(function (q) { return q.extractor === ex; })[0];
        var disp = D[sl.key].rows[ex].f1;
        var ci = s("line", { x1: x(row.f1.lo), x2: x(row.f1.hi), y1: yc + 12, y2: yc + 12 }, g);
        ci.setAttribute("style", "stroke:var(--ink);stroke-width:2");
        var m = s("line", { x1: x(row.f1.mean), x2: x(row.f1.mean), y1: yc - 9, y2: yc + 14 }, g);
        m.setAttribute("style", "stroke:var(--ink);stroke-width:2");
        var nE = sl.empt(ex);
        if (nE > 0) {
          s("text", { x: x(0) + 7, y: yc - 7, "font-size": 10.5, style: "fill:var(--accent)", "font-weight": 600 }, g, nE + " empty");
        }
        var hit = s("rect", { x: ox, y: yc - rowH / 2 + 3, width: panelW, height: rowH, fill: "transparent" }, g);
        bindTip(hit, [disp.mean, NAME[ex] + ", " + sl.label + ", " + vals.length + " pages", "95% CI " + disp.lo + " to " + disp.hi + (nE ? ", " + nE + " empty outputs" : "")], wide && si === 0 ? false : false);
      });
    });
  }

  /* ---------------- tables ---------------- */

  function leaderboard() {
    var tb = $("#t-leader tbody");
    var rows = S.synthetic.rows.map(function (r) {
      return {
        ex: r.extractor, f1: r.f1.mean, precision: r.precision, recall: r.recall, leak: r.leak,
        latency: r.latency_ms, title: r.title_match, config: r.config
      };
    });
    function render() {
      tb.textContent = "";
      rows.forEach(function (r) {
        var d = D.synthetic.rows[r.ex];
        var tr = h("tr", null, tb);
        var td = h("td", { class: "name" }, tr);
        var sw = h("span", { class: "sw", "aria-hidden": "true" }, td);
        sw.setAttribute("style", STYLE[r.ex].hollow ? "border:2px solid " + STYLE[r.ex].c + ";width:9px;height:9px" : "background:" + STYLE[r.ex].c);
        td.appendChild(document.createTextNode(NAME[r.ex]));
        h("span", { class: "cfg" }, td, r.config);
        var f = h("td", null, tr, d.f1.mean + " ");
        h("span", { class: "ci" }, f, "[" + d.f1.lo + ", " + d.f1.hi + "]");
        h("td", null, tr, d.precision);
        h("td", null, tr, d.recall);
        h("td", null, tr, d.leak);
        h("td", null, tr, d.latency_ms);
        h("td", null, tr, r.ex === "html2text" || r.ex === "markdownify" || r.ex === "justext" ? "n/a" : f2(r.title));
      });
    }
    var keys = ["ex", "f1", "precision", "recall", "leak", "latency", "title"];
    var ths = document.querySelectorAll("#t-leader th.sortable");
    ths.forEach(function (th, i) {
      var btn = th.querySelector("button");
      btn.addEventListener("click", function () {
        var k = keys[i];
        var cur = th.getAttribute("aria-sort");
        var dir = cur === "descending" ? "ascending" : cur === "ascending" ? "descending" : (k === "ex" || k === "latency" || k === "leak" ? "ascending" : "descending");
        ths.forEach(function (o) { o.removeAttribute("aria-sort"); o.querySelector(".arrow").textContent = ""; });
        th.setAttribute("aria-sort", dir);
        th.querySelector(".arrow").textContent = dir === "ascending" ? "▲" : "▼";
        var sign = dir === "ascending" ? 1 : -1;
        rows.sort(function (a, b) {
          var va = a[k], vb = b[k];
          if (k === "title") { va = (a.ex === "html2text" || a.ex === "markdownify" || a.ex === "justext") ? -1 : va; vb = (b.ex === "html2text" || b.ex === "markdownify" || b.ex === "justext") ? -1 : vb; }
          if (typeof va === "string") return sign * va.localeCompare(vb);
          return sign * (va - vb);
        });
        render();
        var live = $("#sort-status");
        if (live) live.textContent = "Sorted by " + btn.textContent.trim() + ", " + dir;
      });
    });
    render();
  }

  function heatmap() {
    var t = $("#t-heat");
    var thead = h("thead", null, t), tr = h("tr", null, thead);
    h("th", { scope: "col" }, tr, "Extractor");
    S.synthetic.page_types.forEach(function (pt) { h("th", { scope: "col" }, tr, lab(pt)); });
    var tb = h("tbody", null, t);
    ORDER.forEach(function (ex) {
      var r = h("tr", null, tb);
      h("th", { scope: "row", class: "name", style: "text-align:left;font-weight:500;color:var(--ink)" }, r, NAME[ex]);
      S.synthetic.page_types.forEach(function (pt) {
        var v = S.synthetic.by_type[ex][pt];
        var td = h("td", { class: "cell", title: NAME[ex] + ", " + lab(pt) + ": " + f2(v) }, r, f2(v));
        // most cells sit between 0.6 and 1.0, so that range gets most of the ramp
        var cv = Math.max(0, Math.min(1, v));
        var pct = Math.round(cv < 0.6 ? cv / 0.6 * 20 : 20 + (cv - 0.6) / 0.4 * 80);
        td.style.background = "color-mix(in oklab, var(--seq-hi) " + pct + "%, var(--seq-lo))";
        td.dataset.pct = pct;
      });
    });
  }
  function isDark() { return document.documentElement.getAttribute("data-theme-resolved") === "dark"; }
  function recolorHeat() { /* heat cells use ink text on a light ramp in both themes: nothing to swap */ }

  function spearman() {
    var t = $("#t-spear tbody");
    var w = S.wikipedia.rank, z = S.zyte.rank;
    [["Wikipedia vs synthetic", w.spearman_base_6, w.spearman_all_7],
     ["Zyte vs synthetic", z.spearman_vs_synthetic_6, z.spearman_vs_synthetic_7],
     ["Zyte vs Wikipedia", z.spearman_vs_wikipedia_6, null]].forEach(function (row) {
      var tr = h("tr", null, t);
      h("td", null, tr, row[0]);
      h("td", null, tr, f2(row[1]));
      h("td", null, tr, row[2] === null ? "not computed" : f2(row[2]));
    });
  }

  function taxonomy() {
    var t = $("#t-tax");
    var thead = h("thead", null, t), tr = h("tr", null, thead);
    h("th", { scope: "col" }, tr, "Extractor");
    TAX_LABELS.forEach(function (l) { h("th", { scope: "col" }, tr, lab(l)); });
    var tb = h("tbody", null, t);
    ORDER.forEach(function (ex) {
      var r = h("tr", null, tb);
      h("th", { scope: "row", style: "text-align:left;font-weight:500;color:var(--ink)" }, r, NAME[ex]);
      var counts = S.synthetic.taxonomy[ex] || {};
      TAX_LABELS.forEach(function (l) {
        var c = counts[l] || 0;
        var td = h("td", { class: "dot", title: NAME[ex] + ", " + lab(l) + ": " + c + " of 40" }, r);
        var wrap = h("span", { class: "dotcell" }, td);
        var i = h("i", { "aria-hidden": "true" }, wrap);
        if (c === 0) { i.className = "z"; h("span", { class: "sr" , style: "position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)" }, wrap, "0"); }
        else {
          var d = Math.round(5 + Math.sqrt(c / 40) * 23);
          i.style.width = d + "px"; i.style.height = d + "px";
          if (l === "empty_output") i.className = "hot";
          h("small", null, wrap, String(c));
        }
      });
    });
  }

  function tuningTable() {
    var tb = $("#t-tune tbody");
    var ch = S.tuning.chosen;
    S.tuning.grid.forEach(function (g) {
      var o = g.options;
      var chosen = o.include_comments === ch.include_comments && o.favor_precision === ch.favor_precision && o.favor_recall === ch.favor_recall;
      var tr = h("tr", null, tb);
      h("td", null, tr, String(o.include_comments));
      h("td", null, tr, String(o.favor_precision));
      h("td", null, tr, String(o.favor_recall));
      var f = h("td", null, tr, f3(g.dev_f1));
      h("td", null, tr, f3(g.dev_leak_rate));
      var c = h("td", null, tr, chosen ? "chosen" : "");
      if (chosen) { f.style.fontWeight = "600"; c.style.color = "var(--accent)"; c.style.fontWeight = "600"; }
    });
  }

  function stoplistTable() {
    var tb = $("#t-stop tbody");
    var LANG = { es: "Spanish", de: "German", fr: "French", pt: "Portuguese", it: "Italian", hi: "Hindi" };
    S.side_checks.justext_language_check.forEach(function (r) {
      var tr = h("tr", null, tb);
      h("td", null, tr, LANG[r.lang] || r.lang);
      h("td", null, tr, r.doc_id);
      h("td", null, tr, r.split);
      h("td", null, tr, f3(r.english_stoplist_f1));
      var m = h("td", null, tr, f3(r.matching_stoplist_f1));
      if (r.matching_stoplist_f1 === 0) m.style.color = "var(--accent)";
    });
  }

  function judgeTables() {
    var wrap = $("#confusions");
    S.judge.judges.forEach(function (j) {
      var t = h("table", { class: "confusion" }, null);
      h("caption", null, t, j.model + " (n = " + j.n + ")");
      var th = h("thead", null, t), r0 = h("tr", null, th);
      h("th", { scope: "col" }, r0, "");
      h("th", { scope: "col" }, r0, "judge GOOD");
      h("th", { scope: "col" }, r0, "judge BAD");
      var tb = h("tbody", null, t);
      var c = j.confusion;
      [["metric GOOD", c.metric_GOOD_judge_GOOD, c.metric_GOOD_judge_BAD, "agree", "dis"],
       ["metric BAD", c.metric_BAD_judge_GOOD, c.metric_BAD_judge_BAD, "dis", "agree"]].forEach(function (row) {
        var tr = h("tr", null, tb);
        h("th", { scope: "row" }, tr, row[0]);
        h("td", { class: row[3] }, tr, String(row[1]));
        h("td", { class: row[4] }, tr, String(row[2]));
      });
      var box = h("div", { class: "table-wrap" }, wrap);
      box.appendChild(t);
    });
  }

  function disagreementTable() {
    var tb = $("#t-disagree tbody");
    var have = {};
    S.viewer_index.forEach(function (p) { have[p.doc_id] = true; });
    S.judge.unanimous.disagreements.forEach(function (d) {
      var tr = h("tr", null, tb);
      h("td", { class: "name" }, tr, NAME[d.extractor]);
      var td = h("td", null, tr);
      if (have[d.doc_id]) {
        var a = h("a", { href: "#viewer" }, td, d.doc_id);
        a.addEventListener("click", function (e) {
          e.preventDefault();
          Viewer.open(d.doc_id, d.extractor);
        });
      } else td.textContent = d.doc_id;
      h("td", null, tr, f2(d.f1));
      h("td", null, tr, f2(d.leak_rate));
      h("td", null, tr, d.metric);
      h("td", null, tr, d.judges);
    });
  }

  function facts() {
    var hd = S.synthetic.header;
    var dl = $("#facts");
    function row(k, v) { h("dt", null, dl, k); h("dd", null, dl, v); }
    row("Corpus seed", String(hd.corpus_seed));
    row("Bootstrap seed", String(hd.bootstrap_seed));
    row("Resamples", hd.bootstrap_iters.toLocaleString("en-US"));
    row("Split", hd.n_dev + " dev, " + hd.n_test + " test (only test is reported)");
    row("Timing", "median of " + hd.timing_repeats + " runs per page");
    row("Python", hd.python + " on " + hd.platform);
    var v = hd.versions;
    row("Libraries", Object.keys(v).map(function (k) { return k + " " + v[k]; }).join(", "));
  }

  /* ---------------- side-by-side viewer ---------------- */

  var Viewer = (function () {
    var state = { doc: "blog_comments-2", a: "trafilatura", b: "readability-lxml", show: "a" };
    var cache = {};
    var root, selPage, selA, selB, matrix, frame, goldBox, outA, outB, tabs, pageMeta;

    function init() {
      root = $("#viewer-app");
      selPage = $("#v-page"); selA = $("#v-a"); selB = $("#v-b");
      matrix = $("#v-matrix"); frame = $("#v-frame"); goldBox = $("#v-gold");
      outA = $("#v-out-a"); outB = $("#v-out-b"); tabs = $("#v-tabs"); pageMeta = $("#v-page-meta");
      var groups = {};
      S.synthetic.page_types.forEach(function (pt) { groups[pt] = h("optgroup", { label: lab(pt) }, selPage); });
      S.viewer_index.forEach(function (p) {
        var o = h("option", { value: p.doc_id }, groups[p.page_type] || selPage, p.doc_id + ": " + p.title);
        if (p.doc_id === state.doc) o.selected = true;
      });
      [selA, selB].forEach(function (sel) {
        ORDER.forEach(function (ex) { h("option", { value: ex }, sel, NAME[ex]); });
      });
      selA.value = state.a; selB.value = state.b;
      selPage.addEventListener("change", function () { state.doc = selPage.value; load(); });
      selA.addEventListener("change", function () { state.a = selA.value; render(); });
      selB.addEventListener("change", function () { state.b = selB.value; render(); });
      tabs.querySelectorAll("button").forEach(function (b) {
        b.addEventListener("click", function () { state.show = b.dataset.side; renderTabs(); });
      });
      var det = $("#v-frame-pane");
      if (window.matchMedia("(min-width: 900px)").matches) det.open = true;
      load();
    }

    function renderTabs() {
      tabs.querySelectorAll("button").forEach(function (b) {
        b.setAttribute("aria-pressed", b.dataset.side === state.show ? "true" : "false");
        b.textContent = (b.dataset.side === "a" ? "A: " + NAME[state.a] : "B: " + NAME[state.b]);
      });
      outA.parentElement.setAttribute("data-hidden", state.show === "a" ? "false" : "true");
      outB.parentElement.setAttribute("data-hidden", state.show === "b" ? "false" : "true");
    }

    function load() {
      var id = state.doc;
      root.classList.add("v-loading");
      frame.src = "pages/" + encodeURIComponent(id) + ".html";
      var p = cache[id] ? Promise.resolve(cache[id]) : fetch("data/pages/" + encodeURIComponent(id) + ".json")
        .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then(function (j) { cache[id] = j; return j; });
      p.then(function () { if (state.doc === id) { root.classList.remove("v-loading"); render(); } })
        .catch(function (e) {
          root.classList.remove("v-loading");
          goldBox.textContent = "";
          h("p", { class: "v-error" }, goldBox, "Could not load data/pages/" + id + ".json (" + e.message + "). The page data is served next to this file; open the site through a web server, not from the file system.");
        });
    }

    function marker(cls, letter, title) {
      return h("span", { class: "mk " + cls, title: title, "aria-label": title }, null, letter);
    }

    function render() {
      var P = cache[state.doc];
      if (!P) return;
      pageMeta.textContent = lab(P.page_type) + ", lang " + P.lang;
      // F1 matrix for this page
      matrix.textContent = "";
      ORDER.forEach(function (ex) {
        var e = P.extractors[ex];
        var b = h("button", { type: "button", "aria-label": NAME[ex] + " F1 " + f3(e.f1) + (e.empty ? ", empty output" : "") + ". Show as output A." }, matrix);
        if (ex === state.a) b.classList.add("is-a");
        if (ex === state.b) b.classList.add("is-b");
        if (e.empty) b.classList.add("is-empty");
        h("span", { class: "nm" }, b, SHORT[ex]);
        h("span", { class: "vl" }, b, e.empty ? "empty" : f3(e.f1));
        var bar = h("span", { class: "bar" }, b);
        var fill = h("span", null, bar);
        fill.style.width = Math.round(e.f1 * 100) + "%";
        fill.style.background = STYLE[ex].c;
        b.addEventListener("click", function () { state.a = ex; selA.value = ex; state.show = "a"; render(); });
      });
      renderGold(P);
      renderOut(outA, P, state.a, "A");
      renderOut(outB, P, state.b, "B");
      renderTabs();
    }

    function renderGold(P) {
      goldBox.textContent = "";
      var ea = P.extractors[state.a], eb = P.extractors[state.b];
      h("div", { class: "gold-sub" }, goldBox, "Title");
      h("div", { class: "gold-p" }, goldBox).appendChild(document.createTextNode(P.title));
      h("div", { class: "gold-sub" }, goldBox, "Main text, " + P.main.length + " paragraphs. Markers: A, then B");
      P.main.forEach(function (para, i) {
        var ka = ea.gold_kept[i], kb = eb.gold_kept[i];
        var row = h("div", { class: "gold-p" + (ka ? "" : " dropped-a") }, goldBox);
        var m = h("span", { class: "marks" }, row);
        m.appendChild(marker(ka ? "k" : "d", ka ? "K" : "D", "A, " + NAME[state.a] + ": " + (ka ? "kept" : "dropped")));
        m.appendChild(marker(kb ? "k" : "d", kb ? "K" : "D", "B, " + NAME[state.b] + ": " + (kb ? "kept" : "dropped")));
        var tx = h("span", { class: "txt" }, row, para);
        if (para.length > 260) {
          var more = h("button", { class: "more", type: "button", "aria-expanded": "false" }, row, "Show all");
          more.addEventListener("click", function () {
            var open = row.classList.toggle("open");
            more.textContent = open ? "Show less" : "Show all";
            more.setAttribute("aria-expanded", open ? "true" : "false");
          });
        }
        void tx;
      });
      h("div", { class: "gold-sub" }, goldBox, "Planted boilerplate, " + P.boilerplate.length + " snippets. Leaked into A, B?");
      P.boilerplate.forEach(function (bp, i) {
        var la = ea.leaked.indexOf(i) >= 0, lb = eb.leaked.indexOf(i) >= 0;
        var row = h("div", { class: "bp" }, goldBox);
        var m = h("span", { class: "marks" }, row);
        m.appendChild(marker(la ? "l" : "off", la ? "L" : "·", "A, " + NAME[state.a] + ": " + (la ? "leaked" : "not leaked")));
        m.appendChild(marker(lb ? "l" : "off", lb ? "L" : "·", "B, " + NAME[state.b] + ": " + (lb ? "leaked" : "not leaked")));
        h("span", { class: "kind" }, row, lab(bp.kind));
        h("span", null, row, bp.text);
      });
    }

    function renderOut(box, P, ex, side) {
      var e = P.extractors[ex];
      var pane = box.parentElement;
      var hd = pane.querySelector(".pane-h");
      hd.textContent = "";
      var t = h("h4", null, hd);
      h("span", { class: "tag", style: "display:inline-block;width:1.1rem;text-align:center;background:var(--ink);color:var(--paper);border-radius:2px;margin-right:0.4rem" }, t, side);
      t.appendChild(document.createTextNode(NAME[ex]));
      var nk = 0, nl = 0, nx = 0;
      e.lines.forEach(function (l) { if (l.c === "k") nk++; else if (l.c.indexOf("l:") === 0) nl++; else nx++; });
      h("span", { class: "meta" }, hd, e.lines.length + " lines: " + nk + " K, " + nl + " L, " + nx + " X");

      box.textContent = "";
      var stats = h("div", { class: "out-stats" }, box);
      [["F1", f3(e.f1)], ["Precision", f3(e.precision)], ["Recall", f3(e.recall)], ["Leak", e.n_leaked + " of " + e.n_boilerplate]].forEach(function (p) {
        var d = h("div", null, stats); h("small", null, d, p[0]); h("b", null, d, p[1]);
      });
      var labs = h("div", { class: "out-labels" }, box);
      if (e.labels.length) e.labels.forEach(function (l) { h("span", null, labs, lab(l)); });
      else h("span", { class: "none" }, labs, "No failure labels");
      var ti = h("div", { class: "out-title" }, box, "Title returned: ");
      if (e.title === null || e.title === undefined) ti.appendChild(document.createTextNode("none (this tool has no title call)"));
      else h("q", null, ti, e.title);

      if (e.empty) {
        var es = h("div", { class: "empty-state", role: "note" }, box);
        h("b", null, es, "Empty string, no error.");
        es.appendChild(document.createTextNode(NAME[ex] + " returned "));
        h("code", null, es, "\"\"");
        es.appendChild(document.createTextNode(" for this page and raised nothing. It scores F1 0. A pipeline that does not check for empty output would pass this on as if it were the page."));
        return;
      }
      var lines = h("div", { class: "out-lines", tabindex: "0", role: "region", "aria-label": "Output of " + NAME[ex] }, box);
      e.lines.forEach(function (l) {
        var cls = l.c === "k" ? "k" : l.c.indexOf("l:") === 0 ? "l" : "x";
        var kind = cls === "l" ? l.c.slice(2) : "";
        var title = cls === "k" ? "kept: gold main text" : cls === "l" ? "leaked boilerplate: " + lab(kind) : "extra: not gold, not a tracked snippet";
        var row = h("div", { class: "ln " + cls, title: title }, lines);
        row.appendChild(marker(cls, cls === "k" ? "K" : cls === "l" ? "L" : "X", title));
        var tx = h("span", { class: "tx" }, row);
        if (kind) h("span", { class: "kind" }, tx, lab(kind));
        tx.appendChild(document.createTextNode(l.t));
      });
    }

    function open(doc, ex) {
      state.doc = doc; state.a = ex; state.show = "a";
      selPage.value = doc; selA.value = ex;
      if (state.b === ex) { state.b = ex === "readability-lxml" ? "trafilatura" : "readability-lxml"; selB.value = state.b; }
      load();
      var sec = document.getElementById("viewer");
      sec.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    }

    return { init: init, open: open };
  })();

  /* ---------------- theme ---------------- */

  function theme() {
    var btn = $("#theme-btn");
    var label = $("#theme-label");
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var choice = null;
    try { choice = localStorage.getItem("xb-theme"); } catch (e) { choice = null; }
    function apply() {
      var de = document.documentElement;
      if (choice === "light" || choice === "dark") de.setAttribute("data-theme", choice); else de.removeAttribute("data-theme");
      var resolved = choice === "light" || choice === "dark" ? choice : (mq.matches ? "dark" : "light");
      de.setAttribute("data-theme-resolved", resolved);
      label.textContent = resolved === "dark" ? "Light" : "Dark";
      btn.setAttribute("aria-label", "Switch to " + (resolved === "dark" ? "light" : "dark") + " theme");
      recolorHeat();
    }
    btn.addEventListener("click", function () {
      choice = document.documentElement.getAttribute("data-theme-resolved") === "dark" ? "light" : "dark";
      try { localStorage.setItem("xb-theme", choice); } catch (e) { /* storage blocked: the theme still flips for this visit */ }
      apply();
    });
    if (mq.addEventListener) mq.addEventListener("change", apply);
    apply();
  }

  /* ---------------- table of contents ---------------- */

  function toc() {
    var links = document.querySelectorAll(".toc-side a");
    if (!("IntersectionObserver" in window) || !links.length) return;
    var map = {};
    links.forEach(function (a) { map[a.getAttribute("href").slice(1)] = a; });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          links.forEach(function (a) { a.removeAttribute("aria-current"); });
          var a = map[en.target.id]; if (a) a.setAttribute("aria-current", "true");
        }
      });
    }, { rootMargin: "-30% 0px -60% 0px" });
    Object.keys(map).forEach(function (id) { var e = document.getElementById(id); if (e) io.observe(e); });
    document.querySelectorAll(".toc-mobile a").forEach(function (a) {
      a.addEventListener("click", function () { a.closest("details").open = false; });
    });
  }

  /* ---------------- boot ---------------- */

  function boot() {
    tip = h("div", { class: "tip", role: "tooltip", "aria-hidden": "true" }, document.body);
    theme();
    toc();
    Promise.all([
      fetch("data/site.json").then(function (r) { if (!r.ok) throw new Error("site.json HTTP " + r.status); return r.json(); }),
      fetch("data/display.json").then(function (r) { if (!r.ok) throw new Error("display.json HTTP " + r.status); return r.json(); })
    ]).then(function (res) {
      S = res[0]; D = res[1];
      mount($("#fig-glance"), function (c, w) { drawSlope(c, w, false); });
      var forestMode = "all";
      var redrawForest = mount($("#fig-forest"), function (c, w) { drawForest(c, w, forestMode); });
      document.querySelectorAll("#forest-toggle button").forEach(function (b) {
        b.addEventListener("click", function () {
          forestMode = b.dataset.mode;
          document.querySelectorAll("#forest-toggle button").forEach(function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
          redrawForest();
        });
      });
      var tp = S.synthetic.top_pair, dp = D.synthetic;
      var nl = S.synthetic.paired_other.sensitivity_without_listing;
      mount($("#fig-paired"), function (c, w) {
        drawIntervals(c, w, [
          { label: "All 40 pages, resampling pages", value: pairText(dp.top_pair.page), verdict: tp.page.significant ? "significant" : "crosses zero, not significant", lo: tp.page.lo, hi: tp.page.hi, mid: tp.page.diff, sig: tp.page.significant },
          { label: "All 40 pages, resampling page types (10)", value: pairText(dp.top_pair.type), verdict: tp.type.significant ? "significant" : "crosses zero, not significant", lo: tp.type.lo, hi: tp.type.hi, mid: tp.type.diff, sig: tp.type.significant },
          { label: "Without listing pages (36), resampling pages", value: pairText(dp.no_listing_pair.page), verdict: nl.paired_top_two.significant ? "significant" : "crosses zero, not significant", lo: nl.paired_top_two.lo, hi: nl.paired_top_two.hi, mid: nl.paired_top_two.mean_diff, sig: nl.paired_top_two.significant }
        ], { d0: -0.05, d1: 0.25, zero: 0, zeroLabel: "no difference", ticks: diffTicks(-0.05, 0.25), fmtTick: signed,
          label: "Paired bootstrap difference in F1, readability-lxml minus trafilatura (best-config), three ways." });
      });
      leaderboard();
      heatmap();
      mount($("#fig-bump"), function (c, w) { drawSlope(c, w, true); });
      spearman();
      mount($("#fig-strips"), drawStrips);
      var zp = S.zyte.paired_vs_top["trafilatura (best-config)"], zd = D.zyte.vs_top["trafilatura (best-config)"];
      mount($("#fig-zyte"), function (c, w) {
        drawIntervals(c, w, [
          { label: "181 pages, resampling pages", value: pairText(zd.page), verdict: zp.page.significant ? "significant" : "crosses zero, a tie", lo: zp.page.lo, hi: zp.page.hi, mid: zp.page.diff, sig: zp.page.significant },
          { label: "126 sites, resampling whole sites", value: pairText(zd.site), verdict: zp.site.significant ? "significant" : "crosses zero, a tie", lo: zp.site.lo, hi: zp.site.hi, mid: zp.site.diff, sig: zp.site.significant }
        ], { d0: -0.05, d1: 0.05, zero: 0, zeroLabel: "no difference", ticks: function (w) { return w < 420 ? [-0.04, 0, 0.04] : [-0.04, -0.02, 0, 0.02, 0.04]; }, fmtTick: signed,
          label: "Zyte slice: readability-lxml minus trafilatura (best-config), over pages and over sites. Both intervals cross zero." });
      });
      taxonomy();
      tuningTable();
      stoplistTable();
      var J = S.judge;
      mount($("#fig-kappa"), function (c, w) {
        var rows = J.judges.map(function (j) {
          return { label: j.model + " vs metric rule", value: "kappa " + f2(j.kappa) + " [" + f2(j.kappa_ci[0]) + ", " + f2(j.kappa_ci[1]) + "]", verdict: "agreement " + f2(j.agreement), lo: j.kappa_ci[0], hi: j.kappa_ci[1], mid: j.kappa, sig: true, plain: true };
        });
        var jj = J.judge_vs_judge;
        rows.push({ label: "the two judges with each other", value: "kappa " + f2(jj.kappa) + " [" + f2(jj.kappa_ci[0]) + ", " + f2(jj.kappa_ci[1]) + "]", verdict: "agreement " + f2(jj.agreement), lo: jj.kappa_ci[0], hi: jj.kappa_ci[1], mid: jj.kappa, sig: true, plain: true });
        drawIntervals(c, w, rows, { d0: 0, d1: 1, ticks: function (w) { return w < 420 ? [0, 0.5, 1] : [0, 0.2, 0.4, 0.6, 0.8, 1]; }, fmtTick: function (t) { return t === 0 || t === 1 ? String(t) : t.toFixed(1); },
          label: "Cohen's kappa with 95% intervals: each judge against the metric rule, and the two judges against each other." });
      });
      judgeTables();
      disagreementTable();
      facts();
      Viewer.init();
    }).catch(function (e) {
      document.querySelectorAll(".chart").forEach(function (c) {
        c.textContent = "Could not load the data (" + e.message + "). Serve the site folder over HTTP, for example with python -m http.server.";
      });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
