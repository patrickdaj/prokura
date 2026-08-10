/*
 * site-nav.js — the docs site's single source of navigation truth.
 *
 * Every page loads this once. It injects both the rail markup and its styles,
 * so the three page families (landing, blog, walkthroughs) — which do not share
 * one stylesheet — get an identical global rail plus a section strip generated
 * from the lists below. Adding a milestone or flow is a one-line edit here; no
 * page markup changes. Static rail markup in each page is the no-JS fallback,
 * which this replaces on load.
 */
(function () {
  var path = location.pathname;
  var inBlog = /\/blog\//.test(path);
  var inWalk = /\/walkthroughs\//.test(path);
  var prefix = inBlog || inWalk ? "../" : "";
  var here = path.split("/").pop() || "index.html";

  var GITHUB = "https://github.com/patrickdaj/prokura";
  var ARCH = GITHUB + "/blob/main/docs/architecture.md";

  // Tier 1 — the global rail, identical on every page.
  var SECTIONS = [
    { label: "Walkthrough", href: prefix + "walkthroughs/index.html", cur: inWalk },
    { label: "Blog", href: prefix + "blog/index.html", cur: inBlog },
    { label: "Architecture", href: ARCH },
    { label: "GitHub", href: GITHUB },
  ];

  // Tier 2 (blog) — the complete milestone stepper. Append here for M10+.
  var MILESTONES = [
    { id: "M0", file: "index.html" },
    { id: "M1", file: "m1-token-exchange.html" },
    { id: "M2", file: "m2-token-broker.html" },
    { id: "M3", file: "m3-human-approval.html" },
    { id: "M4", file: "m4-mcp-authorization.html" },
    { id: "M5", file: "m5-rag-authorization.html" },
    { id: "M6", file: "m6-threat-model.html" },
    { id: "M7", file: "m7-correct-parties.html" },
    { id: "M8", file: "m8-authority-console.html" },
    { id: "M9", file: "m9-instant-revocation.html" },
  ];

  // Tier 2 (walkthroughs) — the flow strip; `blog` is the originating post.
  var FLOWS = [
    { label: "Flow A", file: "delegation.html", blog: "m1-token-exchange.html" },
    { label: "Flow B", file: "brokering.html", blog: "m2-token-broker.html" },
    { label: "Flow C", file: "approval.html", blog: "m3-human-approval.html" },
    { label: "Flow D", file: "rag.html", blog: "m5-rag-authorization.html" },
    { label: "MCP", file: "mcp.html", blog: "m4-mcp-authorization.html" },
    { label: "Authority", file: "authority.html", blog: "m8-authority-console.html" },
    { label: "Kill switch", file: "revocation.html", blog: "m9-instant-revocation.html" },
    { label: "Postmortem", file: "postmortem.html" },
    { label: "Claude Code", file: "claude-code.html" },
  ];

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function globalRail() {
    var links = SECTIONS.map(function (s) {
      return '<a href="' + s.href + '"' + (s.cur ? ' class="cur"' : "") + ">" + esc(s.label) + "</a>";
    }).join("");
    return (
      '<div class="wrap">' +
      '<a class="mark" href="' + prefix + 'index.html">PROKURA</a>' +
      '<div class="nav">' + links + "</div>" +
      "</div>"
    );
  }

  function milestoneStrip() {
    var items = MILESTONES.map(function (m) {
      if (m.file === here) return '<span class="cur">' + m.id + "</span>";
      return '<a class="done" href="' + prefix + "blog/" + m.file + '">' + m.id + "</a>";
    }).join("<i>·</i>");
    return '<div class="wrap sub"><div class="strip">' + items + "</div></div>";
  }

  function flowStrip() {
    var cross = "";
    var items = FLOWS.map(function (f) {
      var on = f.file === here;
      if (on && f.blog) {
        var n = f.blog.match(/^m(\d+)/);
        cross =
          '<a class="xlink" href="' + prefix + "blog/" + f.blog + '">' +
          (n ? "M" + n[1] + " blog" : "blog") + " →</a>";
      }
      if (on) return '<span class="cur">' + esc(f.label) + "</span>";
      return '<a href="' + prefix + "walkthroughs/" + f.file + '">' + esc(f.label) + "</a>";
    }).join("<i>·</i>");
    return '<div class="wrap sub"><div class="strip">' + items + "</div>" + cross + "</div>";
  }

  function styles() {
    return [
      ".rail .nav{display:flex;gap:14px;align-items:center;font-family:var(--mono);font-size:11.5px;letter-spacing:.06em;}",
      ".rail .nav a{color:var(--faint);text-decoration:none;}",
      ".rail .nav a.cur{color:var(--accent);}",
      ".rail .mark{text-decoration:none;}",
      ".rail .sub{height:auto;min-height:38px;border-top:1px solid var(--hair);justify-content:space-between;gap:12px;flex-wrap:wrap;}",
      ".rail .strip{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:8px 0;font-family:var(--mono);font-size:11.5px;letter-spacing:.08em;}",
      ".rail .strip a{color:var(--muted);text-decoration:none;} .rail .strip a:hover{color:var(--accent);}",
      ".rail .strip .cur{color:var(--accent);}",
      ".rail .strip i{color:var(--faint);font-style:normal;}",
      ".rail .xlink{font-family:var(--mono);font-size:11px;color:var(--faint);white-space:nowrap;text-decoration:none;} .rail .xlink:hover{color:var(--accent);}",
    ].join("");
  }

  function render() {
    var rail = document.querySelector(".rail");
    if (!rail) return;

    var st = document.createElement("style");
    st.id = "site-nav-css";
    st.textContent = styles();
    document.head.appendChild(st);

    var html = globalRail();
    if (inBlog) html += milestoneStrip();
    else if (inWalk) html += flowStrip();
    rail.innerHTML = html;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
})();
