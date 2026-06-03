/* Retro Price Watch — main app */
const { STORE_BY_ID, fmt, fmtPct, genHistory, changeOf, Sparkline } = window.RPW;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "green",
  "scanlines": 15,
  "density": "comfy"
}/*EDITMODE-END*/;

const PLATFORMS = [...new Set(window.RETRO_DATA.map(d => d.platform))];
const SORTS = [
  { id: "drop",     label: "Biggest drop" },
  { id: "name",     label: "Name A–Z" },
  { id: "priceAsc", label: "Price low→high" },
  { id: "priceDesc",label: "Price high→low" },
];

function clock(d) {
  return d.toLocaleString("en-US", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

/* ---------- stat card ---------- */
function Stat({ label, value, sub, tone }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className={"val " + (tone || "")}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

/* ---------- change cell ---------- */
function ChangeCell({ item }) {
  const c = changeOf(item);
  if (c.kind === "new") return <span className="badge-new">NEW</span>;
  if (c.kind === "flat") return <span className="chg flat">—</span>;
  const arrow = c.kind === "down" ? "▼" : "▲";
  return (
    <span className={"chg " + c.kind}>
      {arrow} {fmt(Math.abs(c.diff))}
      <span className="pct">{fmtPct(c.pct)}</span>
    </span>
  );
}

/* ---------- expandable detail ---------- */
function DetailRow({ item, span }) {
  const hist = useMemo(() => genHistory(item), [item.id, item.price, item.prev]);
  const lo = Math.min(...hist), hi = Math.max(...hist);
  return (
    <tr className="exp-row">
      <td colSpan={span}>
        <div className="exp-inner">
          <div className="spark-box">
            <div className="cap">Price history · last 8 syncs</div>
            <Sparkline data={hist} />
          </div>
          <div className="hist-stats">
            <div><div className="h">Current</div><div className="v">{fmt(item.price)}</div></div>
            <div><div className="h">Low</div><div className="v lo">{fmt(lo)}</div></div>
            <div><div className="h">High</div><div className="v hi">{fmt(hi)}</div></div>
            <div><div className="h">Store</div><div className="v">{STORE_BY_ID[item.store].name}</div></div>
          </div>
        </div>
      </td>
    </tr>
  );
}

/* ---------- main ---------- */
function App() {
  const [items, setItems]   = useState(() => window.RETRO_DATA.map(d => ({ ...d })));
  const [q, setQ]           = useState("");
  const [store, setStore]   = useState("all");
  const [plat, setPlat]     = useState("all");
  const [sort, setSort]     = useState("drop");
  const [dealsOnly, setDeals] = useState(false);
  const [expanded, setExp]  = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [lastSync, setLast] = useState(() => window.RETRO_LAST_SYNC ? new Date(window.RETRO_LAST_SYNC) : new Date(Date.now() - 6 * 3600 * 1000));
  const searchRef = useRef(null);
  const [tw, setTweak] = useTweaks(TWEAK_DEFAULTS);

  // apply tweaks to the document
  useEffect(() => {
    const r = document.documentElement;
    r.setAttribute("data-accent", tw.accent);
    r.style.setProperty("--scanline-alpha", (tw.scanlines / 100).toFixed(3));
    const pad = tw.density === "compact" ? "8px" : tw.density === "comfy" ? "18px" : "13px";
    r.style.setProperty("--row-pad", pad);
  }, [tw.accent, tw.scanlines, tw.density]);

  // keyboard: "/" focuses search
  useEffect(() => {
    const h = e => {
      if (e.key === "/" && document.activeElement !== searchRef.current) {
        e.preventDefault(); searchRef.current && searchRef.current.focus();
      }
      if (e.key === "Escape") { setQ(""); searchRef.current && searchRef.current.blur(); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let rows = items.filter(it => {
      if (store !== "all" && it.store !== store) return false;
      if (plat !== "all" && it.platform !== plat) return false;
      if (dealsOnly) { const c = changeOf(it); if (c.kind !== "down") return false; }
      if (needle) {
        const hay = (it.name + " " + it.platform + " " + STORE_BY_ID[it.store].name).toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
    rows.sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name);
      if (sort === "priceAsc") return a.price - b.price;
      if (sort === "priceDesc") return b.price - a.price;
      // biggest drop: most-negative diff first; NEW & flat sink to bottom
      const da = changeOf(a), db = changeOf(b);
      const va = da.kind === "down" ? da.diff : 1e9;
      const vb = db.kind === "down" ? db.diff : 1e9;
      return va - vb;
    });
    return rows;
  }, [items, q, store, plat, sort, dealsOnly]);

  const stats = useMemo(() => {
    const drops = items.filter(it => changeOf(it).kind === "down").length;
    const avg = items.reduce((s, it) => s + it.price, 0) / items.length;
    return { total: items.length, drops, avg };
  }, [items]);

  function runSync() {
    if (syncing) return;
    setSyncing(true); setExp(null);
    setTimeout(() => {
      setItems(prev => prev.map(it => {
        const r = Math.random();
        if (r < 0.45) {                       // re-roll ~45% of prices
          const dir = Math.random() < 0.62 ? -1 : 1;  // bias toward drops
          const pctMove = (0.03 + Math.random() * 0.16) * dir;
          let np = Math.max(8, it.price * (1 + pctMove));
          np = Math.round(np * 100) / 100;
          return { ...it, prev: it.price, price: np };
        }
        return { ...it, prev: it.prev == null ? it.price : it.prev };
      }));
      setLast(new Date());
      setSyncing(false);
    }, 1150);
  }

  function exportCSV() {
    const head = ["Product", "Store", "Platform", "Price", "Previous", "Change", "Change %"];
    const lines = [head.join(",")];
    filtered.forEach(it => {
      const c = changeOf(it);
      const chg = c.kind === "new" ? "NEW" : c.kind === "flat" ? "0" : c.diff.toFixed(2);
      const pct = c.kind === "down" || c.kind === "up" ? c.pct.toFixed(1) : "";
      const row = [it.name, STORE_BY_ID[it.store].name, it.platform, it.price.toFixed(2),
                   it.prev == null ? "" : it.prev.toFixed(2), chg, pct]
        .map(v => /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : v);
      lines.push(row.join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "retro-price-watch.csv"; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const COLS = 6;
  function header(id, label, extraClass) {
    const active = sort === id || (id === "price" && (sort === "priceAsc" || sort === "priceDesc"));
    const onClick = () => {
      if (id === "name") setSort("name");
      else if (id === "price") setSort(sort === "priceAsc" ? "priceDesc" : "priceAsc");
      else if (id === "drop") setSort("drop");
    };
    let arr = null;
    if (id === "price") arr = sort === "priceAsc" ? "▲" : sort === "priceDesc" ? "▼" : null;
    else if (active) arr = "•";
    return (
      <th className={(extraClass || "") + (id ? " sortable" : "")} onClick={id ? onClick : undefined}>
        {label}{arr && <span className="arr">{arr}</span>}
      </th>
    );
  }

  return (
    <div className="wrap boot">
      {/* header */}
      <div className="hdr">
        <div className="brand-block">
          <h1 className="brand">RETRO PRICE<span className="tld"> WATCH</span></h1>
          <div className="tagline">tracking retro game prices across 4 stores<span className="cursor" /></div>
        </div>
        <div className="status">
          <div className="row"><span className="live-dot" /> <span>FEED LIVE</span></div>
          <div className="row">Last sync: <b>{clock(lastSync)}</b></div>
          <div className="row">Next run: <b>daily 06:00</b></div>
        </div>
      </div>

      <div className="demo-banner">
        <span className="demo-tag">DEMO</span>
        <span>Sample data shaped like the live store feeds — prices are illustrative. Hit SYNC to simulate a fresh pull.</span>
      </div>

      {/* stats */}
      <div className="stats">
        <Stat label="Products tracked" value={stats.total} sub="across all stores" tone="accent" />
        <Stat label="Stores tracked" value="4" sub="RetroFam · vGames · Lukie · DKOldies" />
        <Stat label="Price drops · last sync" value={stats.drops} sub="items cheaper than before" tone="green" />
        <Stat label="Average price" value={fmt(stats.avg)} sub="used condition" />
      </div>

      {/* controls */}
      <div className="controls">
        <div className="search">
          <span className="prompt">›</span>
          <input ref={searchRef} value={q} onChange={e => setQ(e.target.value)}
                 placeholder="search game, console, or store…" />
          <span className="kbd">/</span>
        </div>
        <div className="ctl"><span>Store</span>
          <div className="select">
            <select value={store} onChange={e => setStore(e.target.value)}>
              <option value="all">All stores</option>
              {window.RETRO_STORES.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
        </div>
        <div className="ctl"><span>Platform</span>
          <div className="select">
            <select value={plat} onChange={e => setPlat(e.target.value)}>
              <option value="all">All platforms</option>
              {PLATFORMS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
        </div>
        <div className="ctl"><span>Sort</span>
          <div className="select">
            <select value={sort} onChange={e => setSort(e.target.value)}>
              {SORTS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </div>
        </div>
        <div className={"toggle" + (dealsOnly ? " on" : "")} onClick={() => setDeals(d => !d)}>
          <span className="sw"><span className="knob" /></span> Deals only
        </div>
        <button className="btn primary" onClick={runSync} title="Re-pull store feeds">
          {syncing ? <><span className="spin">↻</span> SYNCING…</> : <>↻ SYNC</>}
        </button>
        <button className="btn" onClick={exportCSV} title="Export current view as CSV">⤓ EXPORT</button>
      </div>

      {/* table meta */}
      <div className="table-meta">
        <div className="count">Showing <b>{filtered.length}</b> of {items.length} products</div>
        <div className="hint">click a row for price history · click headers to sort</div>
      </div>

      {/* table */}
      <div className="tbl-wrap">
        <table>
          <thead>
            <tr>
              {header("name", "Product")}
              <th>Store</th>
              <th>Platform</th>
              {header("price", "Price", "num")}
              {header("drop", "Change", "num")}
              <th className="num">Link</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr><td colSpan={COLS}>
                <div className="empty">
                  <div className="big">NO SIGNAL <span className="blink">_</span></div>
                  <div>No products match your filters. Try clearing the search or turning off “Deals only”.</div>
                </div>
              </td></tr>
            )}
            {filtered.map(it => {
              const s = STORE_BY_ID[it.store];
              const open = expanded === it.id;
              return (
                <React.Fragment key={it.id}>
                  <tr onClick={() => setExp(open ? null : it.id)}>
                    <td>
                      <div className="gname">{it.name}</div>
                    </td>
                    <td><span className="pill" style={{ "--h": s.hue }}>{s.name}</span></td>
                    <td className="gplat">{it.platform}</td>
                    <td className="price">{fmt(it.price)}</td>
                    <td><ChangeCell item={it} /></td>
                    <td className="num">
                      <a className="view-link" href="#" onClick={e => e.stopPropagation()}>View ↗</a>
                    </td>
                  </tr>
                  {open && <DetailRow item={it} span={COLS} />}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* footer */}
      <div className="foot">
        <div className="ft-title">// Roadmap — coming soon</div>
        <div className="roadmap">
          <div className="feat"><span className="ic">✉</span><div><div className="t">Price-drop email alerts</div><div className="d">Ping me when a watched title falls</div></div><span className="soon">SOON</span></div>
          <div className="feat"><span className="ic">📈</span><div><div className="t">Price-history charts</div><div className="d">Full trend lines per product</div></div><span className="soon">SOON</span></div>
          <div className="feat"><span className="ic">⤓</span><div><div className="t">One-click export</div><div className="d">CSV live now · JSON &amp; Sheets next</div></div><span className="soon">BETA</span></div>
        </div>
        <div className="copy">
          <span>RETRO PRICE WATCH · sample build</span>
          <span>4 feeds · {items.length} products · last sync {clock(lastSync)}</span>
        </div>
      </div>

      <Tweaks tw={tw} setTweak={setTweak} />
    </div>
  );
}

function Tweaks({ tw, setTweak }) {
  return (
    <TweaksPanel title="Tweaks">
      <TweakSection label="Display" />
      <TweakRadio label="Accent" value={tw.accent}
                  options={[{ value: "green", label: "Green" }, { value: "amber", label: "Amber" }, { value: "cyan", label: "Cyan" }]}
                  onChange={v => setTweak("accent", v)} />
      <TweakSlider label="Scanlines" value={tw.scanlines} min={0} max={100} step={5} unit="%"
                   onChange={v => setTweak("scanlines", v)} />
      <TweakRadio label="Density" value={tw.density}
                  options={["compact", "regular", "comfy"]}
                  onChange={v => setTweak("density", v)} />
    </TweaksPanel>
  );
}
