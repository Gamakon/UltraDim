// Global state variables for visualization
let svg, width, height, radius, innerRadius, middleRadius, outerRadius, color;
// Bloom centre (the bloom occupies the left square; an optional legend strip
// sits to its right, so the bloom centre is NOT necessarily width/2).
let bloomCx, bloomCy, legendActive = false, legendW = 0;

// Deterministic PRNG (seedrandom, vendored). A fixed seed makes the Voronoi
// treemap layout reproducible so an exported poster is byte-identical across
// re-renders. Override via window.BLOOMMAP_SEED before load. A per-cluster
// salt keeps each petal's tessellation independent yet still deterministic.
const BLOOMMAP_BASE_SEED =
  (typeof window !== "undefined" && window.BLOOMMAP_SEED) || "bloommap-v1";
function seededPrng(salt) {
  // Math.seedrandom returns a function; new instance per cluster (no global state mutation).
  return new Math.seedrandom(`${BLOOMMAP_BASE_SEED}:${salt}`);
}

// Add error styling for user feedback
const style = document.createElement('style');
style.textContent = `.visualization-error {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  background: #fee; color: #c00; padding: 1em; border-radius: 4px; border: 1px solid #fcc; font-family: sans-serif;
}`;
document.head.appendChild(style);

// Global configuration object
const VIZ_CONFIG = {
  // Dimensions
  width: 1400,
  height: 1400,
  
  // Font sizes
  fonts: {
    globalMin: 8,
    globalMax: 14,
    clusterMin: 8, 
    clusterMax: 20,
    clusterLabelSize: 12,
    volumeLabelSize: 11
  },
  
  // Word counts
  wordCounts: {
    global: 100,  // Words in center
    clusters: 50  // Words per outer cluster
  },
  
  // Visualization settings
  visualization: {
    padding: 240,
    volumeScale: 1.2,
    innerRadiusStart: 33,
    innerRadiusEnd: 40,
    outerRadiusStart: 100,
    rotationAngle: 28  // Default rotation angle
  },

  // Treemap settings
  treemap: {
    // rotationOffset: 0,      // Deprecated
    // radialOffset: 0,        // Deprecated
    textRotationOffset: 0,  // Deprecated
    radialPosition: 0.7  // Controls flower openness (0 = closed, 1 = fully open)
  },

  // Colors
  colorScheme: d3.schemeCategory10,

  // Right-edge legend (print-canonical ID -> dimension-name table). Active only
  // when meta.id_to_text is present (a corpus with a dimension dictionary); a
  // corpus with no dictionary renders square with no legend.
  legend: {
    enabled: true,        // gated further by presence of metaData.id_to_text
    width: 520,           // px strip reserved on the right of the bloom square
    pad: 28,              // inner padding of the strip
    rowH: 13,             // row height
    fontSize: 9.5,        // legend entry font (px)
    headerSize: 15,       // legend title font
    colGap: 14,           // gap between legend sub-columns
    title: "Feature ID -> label",
  },
};

// ---------------------------------------------------------------------------
// Lineage colours (artist's spec). ONE shared 30-colour palette, not a separate
// palette per branch. The dendrogram's first binary split gets the SAME colours
// with a global temperature tint: branch 1 cooled (toward blue), branch 2 warmed
// (toward yellow). Related-but-distinct, harmonious because nothing is swapped,
// only warmed/cooled.
//
// Two rules keep it from being ugly:
//  (1) 30 colours = six families of five (teal, blue, purple, ochre, red, green),
//      each a light-to-dark run. Assigning in raw order would rainbow; instead
//      step through by 11 (coprime with 30) so all 30 are used once and each
//      neighbour lands ~two families away. Even spread, no sweep, no clashes.
//  (2) The cool/warm difference is a single tint over the whole set (~22% toward
//      blue / toward yellow), NOT a different palette -- both branches stay the
//      same colour system.
//
// Falls back to schemeCategory10 when no tree is present (e.g. Bible baseline).
// ---------------------------------------------------------------------------
let leafColorMap = null; // { "L01": "#rrggbb", ... }

// TWO surface palettes, drawn from the painting (two surfaces, two palettes).
// Each is six families x five (light -> dark); the step-by-STEP walk depends on
// this layout. Left branch = the LIT GARDEN/WALL surface (jade, teal, olive-gold,
// rust, red accent -- vibrant). Right branch = the SHADOW/BRICK surface
// (slate-blue, mauve, lilac, dusty rose, muted green -- cooler, dustier).
const PALETTE_LEFT = [
  "#0f5f52", "#1c8c7c", "#2fae9c", "#57c4b2", "#86d8c8", // jade/teal
  "#2c7a55", "#3f9e6e", "#5cbb88", "#86d2a6", "#b3e6c8", // green
  "#6b8f1f", "#8aad33", "#a7c452", "#c3da7e", "#dcebac", // olive-gold
  "#a85a16", "#c4762a", "#d89450", "#e6b27e", "#f0cda8", // rust/ochre
  "#9e2b1c", "#bf3f2a", "#d6634c", "#e68d78", "#f0b2a3", // red
  "#1c6f7a", "#2f93a0", "#54b1bd", "#84cdd6", "#b6e4ea", // peacock
];
const PALETTE_RIGHT = [
  "#3a5a7d", "#52789c", "#7396ba", "#9bb6d2", "#c2d4e6", // slate-blue
  "#5a4a78", "#74619b", "#9484bb", "#b6aad2", "#d4cce6", // mauve/violet
  "#8a5a7a", "#a8769a", "#c294b6", "#d8b4cd", "#ead2e0", // dusty rose
  "#6f6a52", "#8d886e", "#a9a48c", "#c5c1ae", "#ddd9cc", // taupe/stone
  "#4a7a6a", "#629a86", "#84b5a3", "#a9cdbf", "#cee0d7", // muted sage
  "#7a6a4a", "#988866", "#b4a484", "#cdc0a4", "#e0d6c0", // sand/shadow-ochre
];
const PALETTE_STEP = 11; // coprime with 30 -> all used once, neighbours 2 families apart
// Back-compat alias used by the ordinal fallback path.
const BLOOM_PALETTE = PALETTE_LEFT;

// TWO palette VARIANTS of the same 30 (every family on BOTH branches, red
// included). The left branch walks a WINTER variant (muted + slightly blued --
// fire-truck red becomes a dusty blued red); the right walks a SPRING variant
// (brighter + warmer fire-truck red). Derived deterministically from the base
// palette so the family structure is identical on both sides, only the mood
// differs. Each is still walked by step-11.
function deriveVariant(hex, mode) {
  let c = hexToRgb(hex);
  const mix = (p, a) => { c = c.map((ch, i) => ch + (p[i] - ch) * a); };
  // push AWAY from the colour's grey (mean) to make it pop, by `sat`
  const saturate = (a) => { const m = (c[0] + c[1] + c[2]) / 3; c = c.map((ch) => ch + (ch - m) * a); };
  if (mode === "winter") {
    // VERY vibrant cool jewel tones that really pop -- strong saturation lift.
    saturate(0.95);                // much more vibrant
    mix([0, 40, 120], 0.08);       // cool: gentle nudge toward deep blue
  } else {                          // spring
    // Slightly subdued warm tones: pull a touch toward grey, gentle warm lean.
    saturate(-0.10);               // desaturate a little (more subdued)
    mix([255, 255, 255], 0.05);    // a little brighter/fresher
    mix([255, 210, 60], 0.07);     // warm: nudge toward spring yellow
  }
  return rgbToHex(c);
}
let WINTER_PALETTE = null, SPRING_PALETTE = null; // built lazily (need hex helpers)

// Temperature tint = MIXING PAINT into the base palette at the first binary
// split. Think of it literally as adding pigment:
//   LEFT branch  (root child 1): + LEFT_WHITE white  + LEFT_BLUE true-blue
//   RIGHT branch (root child 2): - RIGHT_WHITE white (i.e. darken)  + RIGHT_YELLOW yellow
// Each amount is a small fraction (default 2%). White lightens, "minus white"
// darkens (mix toward black), and the colour pigments nudge hue. Tunable via
// window.BLOOMMAP_TINT (scales all four amounts) for stepping.
const TINT_SCALE =
  (typeof window !== "undefined" && typeof window.BLOOMMAP_TINT === "number")
    ? window.BLOOMMAP_TINT
    : 1.0; // 1.0 = the 2% recipe as written; >1 stronger, <1 weaker
const LEFT_WHITE = 0.02 * TINT_SCALE;  // left: +2% white
const LEFT_BLUE = 0.02 * TINT_SCALE;   // left: +2% true blue
const RIGHT_WHITE = 0.02 * TINT_SCALE; // right: -2% white (darken toward black)
const RIGHT_YELLOW = 0.02 * TINT_SCALE; // right: +2% yellow
const PIGMENT_WHITE = [255, 255, 255];
const PIGMENT_BLACK = [0, 0, 0];
const PIGMENT_BLUE = [0, 0, 255];   // true blue
const PIGMENT_YELLOW = [255, 255, 0]; // yellow

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function rgbToHex(rgb) {
  return "#" + rgb.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");
}
// mix `amount` of pigment into rgb (linear blend toward the pigment colour)
function mixPigment(rgb, pigment, amount) {
  return rgb.map((ch, i) => ch + (pigment[i] - ch) * amount);
}
// Apply the per-branch paint recipe. branchIndex 0 = left, 1 = right.
function paintByBranch(hex, branchIndex) {
  let c = hexToRgb(hex);
  if (branchIndex === 0) {
    c = mixPigment(c, PIGMENT_WHITE, LEFT_WHITE);  // +white
    c = mixPigment(c, PIGMENT_BLUE, LEFT_BLUE);    // +true blue
  } else {
    c = mixPigment(c, PIGMENT_BLACK, RIGHT_WHITE); // -white (toward black)
    c = mixPigment(c, PIGMENT_YELLOW, RIGHT_YELLOW); // +yellow
  }
  return rgbToHex(c);
}

function buildLineageColors(tree) {
  const map = {};
  if (!tree) return map;

  // Leaves in ring order (DFS, children natural-sorted -- matches leaf_order).
  const order = [];
  (function dfs(n) {
    if (n.is_leaf) { order.push(n.label); return; }
    (n.children || []).forEach(dfs);
  })(tree);

  // Which depth-2 branch each leaf descends from. The root splits in two, and
  // each of those splits again, giving FOUR branches; we colour them
  // Winter / Spring / Winter / Spring (alternating) rather than a single
  // Winter|Spring split at the root. The four depth-2 nodes are the grandchildren
  // of the root in ring order; branch index 0..3 follows that order.
  const branchOfLeaf = {};
  let branchCursor = 0;
  (tree.children || []).forEach((child) => {
    (child.children || []).forEach((grandchild) => {
      const bi = branchCursor++;
      (function mark(n) {
        if (n.is_leaf) { branchOfLeaf[n.label] = bi; return; }
        (n.children || []).forEach(mark);
      })(grandchild);
    });
  });

  // Build the two surface palettes once: LEFT (lit) gets the vibrant treatment,
  // RIGHT (shadow) gets the subdued treatment. Two DIFFERENT base lists.
  if (!WINTER_PALETTE) {
    WINTER_PALETTE = PALETTE_LEFT.map((h) => deriveVariant(h, "winter"));  // lit surface
    SPRING_PALETTE = PALETTE_RIGHT.map((h) => deriveVariant(h, "spring")); // shadow surface
  }

  // Walk EACH of the four branches' leaves by step-11 over its OWN variant
  // palette, so the colour index depends on the leaf's position WITHIN its
  // branch (not the global ring index) -- every branch uses the full family
  // range, red included. The four branches alternate Winter / Spring / Winter /
  // Spring: even branch index -> Winter (lit surface), odd -> Spring (shadow).
  const perBranchCount = {};
  order.forEach((label) => {
    const branch = branchOfLeaf[label] || 0; // 0..3, the depth-2 branch
    const surface = branch % 2;               // 0 = Winter/lit, 1 = Spring/shadow
    const j = perBranchCount[branch] || 0;    // index of this leaf within its branch
    perBranchCount[branch] = j + 1;
    const pal = surface === 0 ? WINTER_PALETTE : SPRING_PALETTE;
    const base = pal[(j * PALETTE_STEP) % pal.length];
    map[label] = paintByBranch(base, surface); // keep the faint +/-2% nudge on top
  });
  return map;
}

// Resolve a cluster's colour by its leaf key, honouring lineage colours when a
// tree is present, else the ordinal scheme. clusterIndex may be the leaf key
// ("L07") or the pie index; we look up by key first.
function clusterColorByKey(key, ordinalIndex) {
  if (leafColorMap && leafColorMap[key]) return leafColorMap[key];
  return color(ordinalIndex);
}

// Normalize angles to positive values within 2π
const normalizeAngle = (angle) => {
    angle = angle % (2 * Math.PI);
    return angle < 0 ? angle + (2 * Math.PI) : angle;
};

// Get configuration from UI controls
function getConfigFromUI() {
  const cfg = {
    ...VIZ_CONFIG,
    fonts: {
      globalMin: +document.getElementById("globalFontMin").value,
      globalMax: +document.getElementById("globalFontMax").value,
      clusterMin: +document.getElementById("clusterFontMin").value,
      clusterMax: +document.getElementById("clusterFontMax").value,
      clusterLabelSize: +document.getElementById("clusterLabelSize").value,
      volumeLabelSize: 11
    },
    wordCounts: {
      global: +document.getElementById("globalWords").value,
      clusters: +document.getElementById("clusterWords").value
    },
    visualization: {
      padding: +document.getElementById("vizPadding").value,
      volumeScale: +document.getElementById("volumeScale").value,
      innerRadiusStart: +document.getElementById("innerRadiusStart").value,
      innerRadiusEnd: +document.getElementById("innerRadiusEnd").value,
      outerRadiusStart: +document.getElementById("outerRadiusStart").value,
      rotationAngle: +document.getElementById("rotationAngle").value
    },
    treemap: {
      radialPosition: +document.getElementById("radialPosition").value || 0.7
    },
    legend: { ...VIZ_CONFIG.legend },
  };
  applyPaperProfile(cfg);
  return cfg;
}

// Paper-size profile (config/paper_profiles.js). When window.BLOOMMAP_PAPER_SIZE
// is set (e.g. "A1"), scale the bloom square + legend strip + legend density so
// the poster is sized for that physical sheet and the FULL ID dictionary fits.
// Paper size is a layout profile, not a uniform scale: legend rows/cols and the
// drawn-feature budget come from the profile, font floors stay physical.
function applyPaperProfile(cfg) {
  const size =
    (typeof window !== "undefined" && window.BLOOMMAP_PAPER_SIZE) || null;
  const PAPER = typeof window !== "undefined" ? window.BLOOMMAP_PAPER : null;
  if (!size || !PAPER) return;
  const prof = PAPER.getProfile(size);
  const cap = PAPER.legendCapacity(prof); // e.g. A0 -> 1200
  const cols = prof.density.legendCols;
  const rows = prof.density.legendRows;

  // The bloom must dominate the poster. Size the bloom square large, then make
  // the legend tall enough to hold `rows` entries within that height (more rows
  // per column if the bloom is taller than rows*rowH). Legend strip width comes
  // from the column count. A title band is reserved at the top of both.
  const rowH = cfg.legend.rowH;
  const bloomSide = Math.min(
    4200,
    Math.max(2200, rows * rowH * 1.4 + 2 * cfg.legend.pad),
  );
  const colW = Math.ceil(20 * cfg.legend.fontSize * 0.62);
  const legendWidth = cols * colW + (cols - 1) * cfg.legend.colGap + 2 * cfg.legend.pad;

  cfg.height = bloomSide;
  cfg.width = bloomSide; // base bloom square; init widens by legend
  cfg.titleBandPx = Math.round(bloomSide * 0.05); // reserved title strip height
  cfg.legend = {
    ...cfg.legend,
    width: legendWidth,
    capacity: cap,
    title: `${cfg.legend.title}   [${size}]`,
  };
  cfg._paper = { size, profile: prof, capacity: cap };
}

// Helper function to rotate a point around origin
function rotatePoint(x, y, angleInDegrees) {
  const angleInRadians = (angleInDegrees * Math.PI) / 180;
  return {
    x: x * Math.cos(angleInRadians) - y * Math.sin(angleInRadians),
    y: x * Math.sin(angleInRadians) + y * Math.cos(angleInRadians)
  };
}

// Calculate font size based on importance and context
function calculateFontSize(importance, isGlobal = false) {
  const config = getConfigFromUI();
  const { min, max } = isGlobal ? 
    { min: config.fonts.globalMin, max: config.fonts.globalMax } :
    { min: config.fonts.clusterMin, max: config.fonts.clusterMax };
    
  // Using power scale for non-linear emphasis
  const scale = d3.scalePow()
    .exponent(0.5) // Square root scale for more emphasis on higher ranks
    .domain([0, 1])
    .range([min, max]);
    
  return scale(importance);
}

// ---------------------------------------------------------------------------
// Leaf titles (petal cluster labels). Each leaf's label is the movie title(s)
// NEAREST that cluster's centroid — genre/topic discovery, drawn ON the leaf
// sector. Source: metaData.leaf_exemplars[leafId] = [{title, centroid_cosine},
// ...] already ordered nearest-first by the pipeline. Count is capped by
// window.BLOOMMAP_LEAF_LABELS (1 default, up to 3); never more than 3, never an
// id/code, never a wall of text.
function leafLabelCount() {
  const n =
    typeof window !== "undefined" && Number.isFinite(window.BLOOMMAP_LEAF_LABELS)
      ? window.BLOOMMAP_LEAF_LABELS
      : 1;
  return Math.max(1, Math.min(3, Math.round(n)));
}

// The petal labels for one leaf, nearest-centroid first, capped to leafLabelCount.
function leafTitles(leafId) {
  const ex = metaData && metaData.leaf_exemplars && metaData.leaf_exemplars[leafId];
  if (!Array.isArray(ex) || !ex.length) return [];
  return ex
    .slice(0, leafLabelCount())
    .map((e) => (e && typeof e.title === "string" ? e.title : null))
    .filter(Boolean);
}

// ---------------------------------------------------------------------------
// Per-cell members (Voronoi cell = one MOVIE nearest the cluster centroid). The
// classic BloomMap numbers every tessellation cell; on the MovieLens poster each
// leaf petal's cells hold that cluster's member movies nearest the leaf centroid
// (meta.leaf_members[label]), and the centre disc holds the globally most-central
// movies nearest the ROOT centroid (meta.root_members). The printed number is the
// PUBLIC MovieLens movieId (a data-delivered id joinable to movies.csv/links.csv,
// <=6 digits) — NOT the internal row ordinal, which never reaches the artwork. The
// hover shows the movie title and links to its IMDb page (from imdb_id). Both
// lists are ordered nearest-first by the pipeline.
//
// A dataset is in "cell-member mode" iff meta carries these lists. A corpus
// carrying neither keeps the feature-id cell behaviour untouched.
function datasetHasCellMembers() {
  return !!(
    metaData &&
    metaData.leaf_members &&
    metaData.root_members &&
    Object.keys(metaData.leaf_members).length
  );
}

// The ordered member list for one tessellation: a leaf label ("L01"..) -> that
// leaf's nearest-centroid movies; clusterIndex 'global' -> the root members.
// Returns [] when the dataset is not in cell-member mode or the key is unknown.
function cellMembersFor(clusterIndex, clusterKey) {
  if (!datasetHasCellMembers()) return [];
  if (clusterIndex === "global") return metaData.root_members || [];
  const lm = metaData.leaf_members[clusterKey];
  return Array.isArray(lm) ? lm : [];
}

// Voronoi input rows for a cell-member tessellation, capped to `budget` cells
// (the tessellation draws one cell per row). Each row is [movieIdString, weight]:
// the token is the PUBLIC MovieLens movieId as a string (printed in the cell, and
// the key that joins to the title + IMDb link on hover), the weight sizes the
// cell. Weight = a gentle nearest-first taper (rank-linear from 1.0 down to 0.35)
// so the movie nearest the centroid gets the largest cell — mirroring the feature
// path where higher score = bigger cell — without any cell collapsing to a sliver.
function cellMemberData(members, budget) {
  const n = Math.min(members.length, Math.max(1, budget));
  const rows = [];
  for (let i = 0; i < n; i++) {
    const w = n <= 1 ? 1.0 : 1.0 - 0.65 * (i / (n - 1));
    rows.push([String(members[i].movie_id), w]);
  }
  return rows;
}

// movieId (printed token) -> { title, href } for the per-cell hover. Built once
// per render from all member lists so a cell can name its own movie and link to
// its IMDb page. href is the IMDb title URL from imdb_id (tt + 7 digits), or ""
// when the movie has no IMDb id (then the hover shows the plain title only).
let cellInfoByMovieId = null;
function imdbUrl(imdbId) {
  const id = String(imdbId || "").trim();
  return id ? `https://www.imdb.com/title/tt${id}/` : "";
}
function buildCellTitleIndex() {
  cellInfoByMovieId = new Map();
  if (!datasetHasCellMembers()) return;
  const add = (m) => {
    if (m && m.movie_id != null && typeof m.title === "string")
      cellInfoByMovieId.set(String(m.movie_id), {
        title: m.title,
        href: imdbUrl(m.imdb_id),
      });
  };
  (metaData.root_members || []).forEach(add);
  Object.values(metaData.leaf_members || {}).forEach((list) =>
    (list || []).forEach(add),
  );
}
function cellInfoFor(movieIdToken) {
  if (!cellInfoByMovieId) buildCellTitleIndex();
  return cellInfoByMovieId.get(String(movieIdToken)) || { title: "", href: "" };
}
function cellTitleFor(movieIdToken) {
  return cellInfoFor(movieIdToken).title;
}
function cellHrefFor(movieIdToken) {
  return cellInfoFor(movieIdToken).href;
}

// Whether the standalone HTML hover layer is active for this render. Set by the
// render harness from --hover (window.BLOOMMAP_HOVER === "html"). When off (the
// default), NO hover attributes are added and the SVG is byte-identical to today.
function hoverActive() {
  return (
    typeof window !== "undefined" && window.BLOOMMAP_HOVER === "html"
  );
}

// The hover tooltip text for one leaf: the leaf's TOP-3 nearest-centroid movie
// titles (unabbreviated), one per line, regardless of how many are PRINTED on
// the petal (leafLabelCount). Hover reveals depth the static 1-title label omits.
// Returns "" when the leaf has no titles (non-title datasets), so the caller can
// skip attaching an empty tooltip.
function leafHoverTitle(leafId) {
  const ex = metaData && metaData.leaf_exemplars && metaData.leaf_exemplars[leafId];
  if (!Array.isArray(ex) || !ex.length) return "";
  const titles = ex
    .slice(0, 3)
    .map((e) => (e && typeof e.title === "string" ? e.title : null))
    .filter(Boolean);
  return titles.join("\n");
}

// Attach hover data to a d3 selection of petal elements. Adds BOTH a data-title
// attribute (read by the injected CSS/JS tooltip layer via event delegation) and
// a native SVG <title> child (the no-JS / accessibility fallback). keyFn maps a
// bound datum to its leaf id. No-op unless hoverActive(), so --hover off stays
// byte-identical. Skips elements whose leaf yields no title (non-title datasets).
function attachLeafHover(selection, keyFn) {
  if (!hoverActive()) return;
  selection.each(function (d) {
    const leafId = keyFn(d);
    const tip = leafHoverTitle(leafId);
    if (!tip) return;
    const el = d3.select(this);
    el.attr("data-title", tip);
    el.append("title").text(tip);
  });
}

// Whether THIS dataset carries printable leaf titles (the ML exemplar shape: a
// per-leaf array of {title, ...}). Distinct from merely having a leaf_exemplars
// key — chembl's exemplars are single {chembl_id, smiles} dicts with no title,
// so it must NOT trigger the title-lane layout (which would drop its volume
// counts). Returns true only if at least one leaf yields a title.
function datasetHasLeafTitles() {
  const le = metaData && metaData.leaf_exemplars;
  if (!le) return false;
  for (const k of Object.keys(le)) {
    const ex = le[k];
    if (Array.isArray(ex) && ex.some((e) => e && typeof e.title === "string"))
      return true;
  }
  return false;
}

// Drop EVERY trailing parenthetical group (alt titles AND the release year), one
// at a time from the right: "No Blood Relation (Stepchild, The) (Nasanunaka)
// (1932)" -> "No Blood Relation"; "Gen-Y Cops (Te jing xin ren lei 2) (2000)" ->
// "Gen-Y Cops". Used when the full title won't fit the petal. Never touches
// parentheses that sit inside the leading phrase (there are none once trailing
// groups are peeled), so it collapses to the base title.
function stripParentheticals(title) {
  let s = String(title).trim();
  let prev;
  do {
    prev = s;
    s = s.replace(/\s*\([^()]*\)\s*$/, "").trim();
  } while (s !== prev && s.length);
  return s || String(title).trim();
}

// WCAG relative luminance of an sRGB colour, 0..1 (gamma-correct, unlike the
// quick Rec.709 average) — the input to the WCAG contrast ratio.
function relLuminance(fill) {
  const c = d3.color(fill);
  if (!c) return 1;
  const rgb = c.rgb();
  const lin = (v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(rgb.r) + 0.7152 * lin(rgb.g) + 0.0722 * lin(rgb.b);
}

// WCAG contrast ratio between two colours, 1..21. >= 3:1 is the large-text /
// graphical-object legibility floor we hold every petal title to.
function contrastRatio(a, b) {
  const la = relLuminance(a);
  const lb = relLuminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

// The pale sector background a title's INNER portion sits on: white with the
// leaf's brighter(1.5) fill at 0.2 opacity (path.middle in createDonutRings).
// Alpha-composite over white so the guard sees the real backdrop, not the
// saturated cell (the title crosses both; the pale sector is the harder case).
function paleSectorColor(fill) {
  const c = d3.color(fill);
  if (!c) return "#ffffff";
  const t = c.brighter(1.5).rgb();
  const a = 0.2;
  const over = (ch) => Math.round(a * ch + (1 - a) * 255);
  return `rgb(${over(t.r)},${over(t.g)},${over(t.b)})`;
}

// Ink colour for a title on this leaf's petal, with a HARD contrast guard. The
// title crosses two backgrounds — the pale inner sector and the saturated outer
// cell — so we require >= 3:1 against BOTH. Try near-black and warm-cream; pick
// whichever clears 3:1 on both, preferring the one with the larger MINIMUM
// contrast across the two backgrounds. (The stroke halo is a second line of
// defence, but the ink itself must pass so the guard is real, not cosmetic.)
function pickInk(fill) {
  const bgs = [paleSectorColor(fill), fill];
  const candidates = ["#141414", "#fdfdf5"];
  let best = candidates[0];
  let bestMin = -1;
  for (const ink of candidates) {
    const minCr = Math.min(...bgs.map((bg) => contrastRatio(ink, bg)));
    if (minCr > bestMin) {
      bestMin = minCr;
      best = ink;
    }
  }
  return best;
}

// Initialize or reinitialize the visualization
function initializeVisualization() {
  try {
    const config = getConfigFromUI();
    
    // Clean up existing visualization
    if (svg) {
      svg.selectAll("*").remove();
    }
    
    // Legend strip is active only when a dictionary (meta.id_to_text) exists.
    // Some posters (MovieLens) carry a dictionary that is a pipeline-lookup axis
    // (user ordinals) which is NEVER printed as a legend — the leaf titles ARE the
    // labels. window.BLOOMMAP_NO_LEGEND forces the strip off regardless.
    const noLegend =
      typeof window !== "undefined" && !!window.BLOOMMAP_NO_LEGEND;
    legendActive =
      !noLegend &&
      !!(config.legend && config.legend.enabled && metaData && metaData.id_to_text);
    legendW = legendActive ? config.legend.width : 0;

    // The bloom occupies a square of side = config.height (the base canvas).
    // When a legend is active the SVG widens by legendW on the right; the bloom
    // stays centred in the left square so it is never distorted by the strip.
    const bloomSide = config.height;
    const titleBand = config.titleBandPx || 0;
    width = bloomSide + legendW;
    height = config.height + titleBand;

    svg = d3.select("#visualization")
      .attr("width", width)
      .attr("height", height);

    // bloom centred in the left square, BELOW the title band
    bloomCx = bloomSide / 2;
    bloomCy = titleBand + bloomSide / 2;

    radius = bloomSide / 2 - config.visualization.padding;
    
    // Validate radii
    if (config.visualization.innerRadiusStart >= config.visualization.innerRadiusEnd ||
        config.visualization.innerRadiusEnd >= config.visualization.outerRadiusStart) {
      throw new Error("Invalid radius configuration");
    }
    
    innerRadius = (config.visualization.innerRadiusStart / 100) * radius;
    middleRadius = (config.visualization.innerRadiusEnd / 100) * radius;
    outerRadius = (config.visualization.outerRadiusStart / 100) * radius;

    // Ensure color scheme exists
    color = d3.scaleOrdinal(config.colorScheme || d3.schemeCategory10);
    
    // Add resize handler
    window.removeEventListener('resize', handleResize);
    window.addEventListener('resize', handleResize);
    
  } catch (error) {
    console.error("Visualization initialization failed:", error);
    displayError(error.message);
    throw error;
  }
}

// Cleanup function for removing event listeners and clearing SVG
function cleanup() {
  window.removeEventListener('resize', handleResize);
  if (svg) {
    svg.selectAll("*").remove();
  }
}

// Handle window resize events
function handleResize() {
  const container = document.getElementById("visualization").parentElement;
  const newWidth = container.clientWidth;
  const newHeight = container.clientHeight;
  
  if (newWidth !== width || newHeight !== height) {
    width = newWidth;
    height = newHeight;
    createVisualization();
  }
}

// Validate input data structure
function validateData(themeData, volumeData) {
  if (!themeData || !volumeData) {
    throw new Error("Missing required data");
  }
  
  if (!themeData.global || !Array.isArray(themeData.global)) {
    throw new Error("Invalid global theme data format");
  }
  
  const clusters = Object.keys(themeData).filter(k => k !== 'global');
  if (clusters.length === 0) {
    throw new Error("No cluster data found");
  }
  
  clusters.forEach(cluster => {
    if (!Array.isArray(themeData[cluster])) {
      throw new Error(`Invalid data format for cluster: ${cluster}`);
    }
    if (!volumeData[cluster] || isNaN(volumeData[cluster].volume)) {
      throw new Error(`Missing or invalid volume data for cluster: ${cluster}`);
    }
  });
}


// Display error messages to user
function displayError(message) {
  const container = document.getElementById("visualization").parentElement;
  const errorDiv = document.createElement("div");
  errorDiv.className = "visualization-error";
  errorDiv.textContent = `Error: ${message}`;
  container.appendChild(errorDiv);
}

function createDonutRings(data, vizGroup, volumeData, config) {
  console.log("Creating donut rings with data:", data);
  console.log("Raw volume data:", volumeData);

  // Bars are NOT group-rotated (kaito exemplar): the petals' rotation lives in
  // their pre-rotated geometry, and the bars sit at the raw pie angle so each
  // petal's pre-rotated wedge lands over its own bar. Adding a bar-group spin here
  // fights the petals and throws the alignment off -- do not reintroduce it.
  const g = vizGroup.append("g");

  // Add white background for central area
  g.append("circle")
    .attr("r", innerRadius)
    .attr("fill", "white");

  const pie = d3.pie()
    .value(d => 1)
    .sort(null);

  const arc = d3.arc();

  // Inner ring (darker colors, cluster labels)
  const innerArc = arc.innerRadius(innerRadius).outerRadius(middleRadius);
  g.selectAll("path.inner")
    .data(pie(data))
    .enter()
    .append("path")
    .attr("class", "inner")
    .attr("d", innerArc)
    .attr("fill", (d, i) => clusterColorByKey(d.data, i))
    .attr("stroke", "white")
    .attr("stroke-width", 1);

  // Middle ring (pale, transparent background)
  const middleArc = arc.innerRadius(middleRadius).outerRadius(outerRadius);
  g.selectAll("path.middle")
    .data(pie(data))
    .enter()
    .append("path")
    .attr("class", "middle")
    .attr("d", middleArc)
    .attr("fill", (d, i) => d3.color(clusterColorByKey(d.data, i)).brighter(1.5))
    .attr("stroke", "none")
    .attr("opacity", 0.2);

  // Define volumeScale with robust global detection
  const volumes = Object.entries(volumeData)
    .filter(([key, value]) => typeof value.volume === 'number' && !isNaN(value.volume));
  
  console.log("Valid volume entries:", volumes);

  // Separate global and local volumes
  const globalVolume = volumeData.global.volume;
  const localVolumes = Object.keys(volumeData)
    .filter(key => key !== 'global')
    .map(key => volumeData[key].volume);

  if (localVolumes.length === 0) {
    console.error("No valid local volume data found");
    return {pie, middleArc};
  }

  const volumeScale = d3.scaleLinear()
    .domain([0, d3.max(localVolumes) * 1.2])
    .range([0, outerRadius - middleRadius]);

  // Volume bars (the coloured petal wedge the reader sees). On title datasets
  // these carry the hover data (leaf's top-3 nearest-centroid titles) when the
  // HTML hover layer is active; --hover off adds nothing (byte-identical).
  const volumeBars = g.selectAll("path.volume")
    .data(pie(data))
    .enter()
    .append("path")
    .attr("class", "volume")
    .attr("d", (d) => {
      const volume = volumeData[d.data].volume || 0;
      const outerRadiusAdjusted = middleRadius + volumeScale(volume);
      return arc
        .innerRadius(middleRadius)
        .outerRadius(outerRadiusAdjusted)
        .startAngle(d.startAngle + 0.02)
        .endAngle(d.endAngle - 0.02)
        (d);
    })
    .attr("fill", (d, i) => clusterColorByKey(d.data, i))
    .attr("stroke", "none")
    .attr("opacity", 0.95);
  attachLeafHover(volumeBars, (d) => d.data);

  // Outer ring (thin, clean look)
  const outerArc = arc.innerRadius(outerRadius).outerRadius(outerRadius + 2);
  g.selectAll("path.outer")
    .data(pie(data))
    .enter()
    .append("path")
    .attr("class", "outer")
    .attr("d", outerArc)
    .attr("fill", (d, i) => d3.color(clusterColorByKey(d.data, i)).darker(0.5))
    .attr("stroke", "none");

  // Inner-ring cluster labels (the leaf id, e.g. "L01"). On title datasets
  // (MovieLens) the leaf's name is the movie title drawn ON the petal wedge (see
  // drawPetalTitle), so the ring carries NO text — printing the leaf id here too
  // would be the inner-ring wall of text the contract bans. Non-title datasets
  // (e.g. chembl) keep the leaf id on the ring, unchanged.
  if (!datasetHasLeafTitles()) {
    g.selectAll("text.cluster-label")
      .data(pie(data))
      .enter()
      .append("text")
      .attr("class", "cluster-label")
      .attr("transform", d => {
        const angle = (d.startAngle + d.endAngle) / 2;
        const labelRadius = middleRadius + 5;
        const x = Math.cos(angle - Math.PI / 2) * labelRadius;
        const y = Math.sin(angle - Math.PI / 2) * labelRadius;
        let degrees = (angle - Math.PI / 2) * 180 / Math.PI;
        if (angle > Math.PI) degrees += 180;
        return `translate(${x},${y}) rotate(${degrees})`;
      })
      .attr("text-anchor", d => {
        const angle = (d.startAngle + d.endAngle) / 2;
        return angle > Math.PI ? "end" : "start";
      })
      .attr("dominant-baseline", "middle")
      .attr("fill", (d, i) => d3.color(clusterColorByKey(d.data, i)).darker(1.5))
      .attr("font-size", `${config.fonts.clusterLabelSize}px`)
      .attr("font-weight", "bold")
      .text(d => d.data);
  }


  // Add volume count labels. When leaf titles occupy the radial lane (the
  // MovieLens poster), a black count at every bar tip collides with the title
  // that reads outward across the whole bar band. There the population is left
  // encoded by BAR LENGTH alone (and is recoverable from the hover title /
  // volumes.json) so the single printed label per leaf stays the movie title —
  // no competing wall of numbers. On the label-less datasets the count sits at
  // the bar tip in black as before.
  const titlesActive = datasetHasLeafTitles();
  if (!titlesActive) {
    g.selectAll("text.volume-label")
      .data(pie(data))
      .enter()
      .append("text")
      .attr("class", "volume-label")
      .attr("transform", d => {
        const volume = volumeData[d.data].volume || 0;
        const angle = (d.startAngle + d.endAngle) / 2;
        const outerRadiusAdjusted = middleRadius + volumeScale(volume);
        const x = Math.cos(angle - Math.PI / 2) * outerRadiusAdjusted;
        const y = Math.sin(angle - Math.PI / 2) * outerRadiusAdjusted;
        return `translate(${x},${y})`;
      })
      .attr("text-anchor", d => {
        const angle = (d.startAngle + d.endAngle) / 2;
        if (angle < Math.PI * 0.25 || angle > Math.PI * 1.75) return "start";
        if (angle >= Math.PI * 0.75 && angle <= Math.PI * 1.25) return "end";
        return "middle";
      })
      .attr("dominant-baseline", d => {
        const angle = (d.startAngle + d.endAngle) / 2;
        return angle < Math.PI ? "baseline" : "hanging";
      })
      .attr("fill", "black")
      .attr("font-size", "10px")
      .text(d => volumeData[d.data].volume || 0);
  }

  return {pie, middleArc};
}


// Create Voronoi treemap
function createVoronoiTreemap(data, clipPolygon, clusterIndex) {
  if (!data || !clipPolygon) {
    console.error("Invalid data or clipPolygon:", {data, clipPolygon});
    return null;
  }

  const voronoiTreemap = d3.voronoiTreemap()
    .clip(clipPolygon)
    .minWeightRatio(0.01)
    .prng(seededPrng(clusterIndex));

  const rootNode = d3.hierarchy({children: data})
    .sum(d => d[1]);

  try {
    voronoiTreemap(rootNode);
    return rootNode;
  } catch (e) {
    console.error("Error creating treemap:", e);
    return null;
  }
}

// Draw Voronoi treemap with enhanced text rotation
function drawVoronoiTreemap(treemap, x, y, clusterIndex, clusterName, vizGroup, angle) {
  if (!treemap) return;
  
  const config = getConfigFromUI();
  
  // Calculate base rotation for the cluster
  const clusterRotation = clusterIndex === 'global' ? 0 : (angle * 180 / Math.PI - 90); 
  
  // Create group for this treemap
  const g = vizGroup.append("g")
    .attr("transform", `translate(${x},${y})`);

  // Resolve an ID token to its full dimension name (screen hover tooltip).
  // Same id_to_text table the print legend uses; null-safe for the Bible
  // baseline (no meta) where tokens are already human words.
  const tooltipFor = (token) => {
    if (metaData && metaData.id_to_text && metaData.id_to_text[token]) {
      return `${token}  ->  ${metaData.id_to_text[token]}`;
    }
    return token;
  };

  // Add paths for treemap cells
  const cells = g.selectAll("path")
    .data(treemap.descendants().filter(d => d.depth > 0 && d.polygon))
    .enter()
    .append("path")
    .attr("d", d => `M${d.polygon.join("L")}Z`)
    .attr("fill", clusterIndex === 'global'
      ? "#333333"
      : clusterColorByKey(clusterName, clusterIndex))
    .attr("stroke", "white")
    .attr("stroke-width", 0.5);
  // Cell-member mode (MovieLens): each cell is a MOVIE, so its hover names the
  // movie title (per-cell), joined off the printed ordinal token. In the classic
  // feature mode the hover resolves the ID to its dimension name.
  // A native SVG <title> child is always added (no-JS / a11y). When the HTML
  // hover layer is active AND we are in cell-member mode, ALSO set data-title on
  // each cell so the delegated tooltip layer (which walks up to the nearest
  // data-title ancestor) reveals THAT cell's movie — the per-cell deliverable.
  const cellMembers = datasetHasCellMembers();
  if (cellMembers) {
    // Native <title> stays PLAIN text (no-JS / a11y fallback). The HTML hover
    // layer additionally reads data-title (the movie title) and data-href (the
    // IMDb URL) to render a clickable anchor in the tooltip.
    cells.append("title").text(d => cellTitleFor(d.data[0]));
    if (hoverActive()) {
      cells.attr("data-title", d => cellTitleFor(d.data[0]));
      cells.attr("data-href", d => cellHrefFor(d.data[0]));
    }
  } else {
    cells.append("title").text(d => tooltipFor(d.data[0]));
  }

// Per-cell ID labels. Some datasets tessellate over a feature axis with no
// printable name — user ordinals — so labelling each cell with its code would be
// a wall of meaningless text; window.BLOOMMAP_NO_CELL_LABELS suppresses the cell
// text there (the tessellation + the hover <title> stay). In cell-member mode the
// cells are MOVIES and the printed number is the movie ORDINAL (a joinable id, not
// a meaningless code), so numbering is the whole point — the suppress flag does
// NOT apply. Only the feature-mode path honours BLOOMMAP_NO_CELL_LABELS.
const noCellLabels =
  !cellMembers && typeof window !== "undefined" && !!window.BLOOMMAP_NO_CELL_LABELS;
if (noCellLabels) return;

// Add text with enhanced rotation calculation
  g.selectAll("text")
    .data(treemap.descendants().filter(d => d.depth > 0 && d.polygon))
    .enter()
    .append("text")
    .attr("transform", d => {
      // Calculate centroid of the polygon for text placement
      const x = d.polygon.reduce((acc, point) => acc + point[0], 0) / d.polygon.length;
      const y = d.polygon.reduce((acc, point) => acc + point[1], 0) / d.polygon.length;
      
      // Calculate text rotation to maintain horizontal text
      // Counter-rotate against both cluster angle and overall visualization rotation
      //const textRotation = clusterIndex === 'global' ? 
      //  -config.visualization.rotationAngle : 
      //  -(clusterRotation + config.visualization.rotationAngle);

      // Counter-rotate against the overall visualization rotation
      const globalRotation = config.visualization.rotationAngle;


      // For non-global clusters, rotate text to match sector angle

      if (clusterIndex !== 'global') {
        return `translate(${x},${y}) rotate(${globalRotation})`;
      } else {
        return `translate(${x},${y})`;
      }

return `translate(${x},${y}) rotate(${-globalRotation})  `;
    })
    .attr("text-anchor", "middle")
    .attr("dominant-baseline", "central")
    .attr("font-size", d => {
      // Importance-driven size, then CLAMPED to fit the cell so labels in small
      // Voronoi cells stop overlapping their neighbours. Fit width = the cell's
      // bbox width / (label length * 0.6 advance); fit height = ~0.9 * bbox
      // height. Take the smaller of importance-size and the cell-fit size.
      let fontSize = calculateFontSize(d.data[1], clusterIndex === 'global');
      const xs = d.polygon.map(p => p[0]);
      const ys = d.polygon.map(p => p[1]);
      const cw = Math.max(...xs) - Math.min(...xs);
      const ch = Math.max(...ys) - Math.min(...ys);
      const label = String(d.data[0]);
      const fitW = (cw * 0.92) / Math.max(1, label.length * 0.6);
      const fitH = ch * 0.9;
      fontSize = Math.min(fontSize, fitW, fitH);
      return `${fontSize}px`;
    })
    .attr("fill", "white")
    .text(d => d.data[0]);
}

// ---------------------------------------------------------------------------
// Petal title (the cluster label, drawn ON the petal wedge). For datasets with
// leaf titles (MovieLens) the leaf's name is the movie nearest its centroid; it
// is written along the petal's radial axis, sized by a cell-fit clamp against
// the wedge, coloured by luminance for contrast against the petal fill. The
// title rides the SAME pre-rotated geometry as the petal (drawn into the petal's
// translate+rotate frame), so it lands on the petal, not the inner ring.
//
//   fill        : the petal's fill colour (for the luminance ink choice)
//   cx, cy      : the petal's pre-rotated centroid (radial midpoint of the wedge)
//   petalDeg    : the petal's on-screen rotation in degrees (its radial direction)
//   radialLen   : the wedge's radial length (outerRadius - middleRadius)
//   arcWidth    : the wedge's tangential width at the label radius
//   titles      : nearest-centroid-first movie titles (1..3) for this leaf
//   hoverTitle  : full top-3 titles for the hover layer ("" => no hover attr)
// ---------------------------------------------------------------------------
function drawPetalTitle(vizGroup, fill, cx, cy, petalDeg, radialLen, arcWidth, titles, hoverTitle) {
  if (!titles || !titles.length) return;
  const config = getConfigFromUI();
  const nLines = titles.length;

  // The title reads along the petal's radial axis. Text HEIGHT (font size) is set
  // by the petal's tangential WIDTH (arcWidth / nLines) — the petal is narrow, so
  // this is what keeps a leaf's title from bleeding into its neighbours. Text
  // LENGTH then runs radially with budget radialLen. Rather than shrink the font
  // to cram a long title in, we hold a legible font and CLEAN the title until it
  // fits. Cleanup order (per review): keep the full title (with year) only while
  // it fits comfortably; the moment it overflows, strip ALL trailing
  // parentheticals — alternate titles AND the year — down to the leading proper
  // title ("No Blood Relation (Stepchild, The) (Nasanunaka) (1932)" -> "No Blood
  // Relation"); ellipsis is the final resort for a bare title still too long.
  const CEIL = Math.min(config.fonts.clusterMax || 20, 22);
  let fontSize = Math.min(CEIL, (arcWidth * 0.82) / nLines);
  const maxChars = Math.max(5, Math.floor((radialLen * 0.92) / (fontSize * 0.55)));

  const fits = (arr) => arr.every((t) => t.length <= maxChars);
  const full = titles.slice();
  // stripParentheticals peels every trailing (...) group, so it removes alt-title
  // parentheticals and the (YYYY) year together — exactly the "bare leading
  // title" the review asks for when a label overflows.
  const bare = titles.map(stripParentheticals);
  let drawn = fits(full) ? full : bare;

  // Final resort: ellipsis-truncate whatever still overflows at this font.
  drawn = drawn.map((t) =>
    t.length > maxChars ? t.slice(0, maxChars - 1).trimEnd() + "…" : t,
  );

  // Orient the baseline along the petal's radial direction. petalDeg points from
  // the bloom centre outward; a text rotated by that reads radially. Flip 180°
  // on the lower half so no title is upside down (keep it left-to-right).
  let deg = petalDeg;
  const flip = deg > 90 || deg < -90;
  if (flip) deg += 180;

  const ink = pickInk(fill);
  // Contrast halo: a thin stroke in the OPPOSITE tone, drawn BEHIND the fill
  // (paint-order: stroke). Keeps the title legible even where it grazes the pale
  // sector background or a lighter Voronoi cell — never hue-on-same-hue.
  const halo = ink === "#141414" ? "#ffffff" : "#141414";
  const g = vizGroup
    .append("g")
    .attr("class", "petal-title")
    .attr("transform", `translate(${cx},${cy}) rotate(${deg})`);

  // Hover on the printed label too: same top-3 tooltip as the petal wedge. Only
  // when the HTML hover layer is active and the leaf has titles; otherwise this
  // adds nothing so --hover off stays byte-identical.
  if (hoverActive() && hoverTitle) {
    g.attr("data-title", hoverTitle);
    g.append("title").text(hoverTitle);
  }

  // Stack lines tangentially (the y axis in the rotated frame), centred on the
  // wedge midline. Nearest-centroid title is the centre/first line.
  const lineGap = fontSize * 1.12;
  const y0 = -((nLines - 1) / 2) * lineGap;
  drawn.forEach((t, li) => {
    g.append("text")
      .attr("x", 0)
      .attr("y", y0 + li * lineGap)
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "central")
      .attr("font-size", `${fontSize}px`)
      .attr("font-weight", "bold")
      .attr("fill", ink)
      .attr("stroke", halo)
      .attr("stroke-width", Math.max(0.6, fontSize * 0.11))
      .attr("stroke-linejoin", "round")
      .attr("paint-order", "stroke")
      .text(t);
  });
}

// Get clip polygon for treemap boundaries
function getClipPolygon(startAngle, endAngle, innerRadius, outerRadius) {
  if (isNaN(startAngle) || isNaN(endAngle) || isNaN(innerRadius) || isNaN(outerRadius)) {
    console.warn('Invalid parameters in getClipPolygon:', {startAngle, endAngle, innerRadius, outerRadius});
    return [[0,0]];
  }

  const step = Math.PI / 180;
  const points = [];

  for (let angle = startAngle; angle <= endAngle; angle += step) {
    points.push([Math.cos(angle) * innerRadius, Math.sin(angle) * innerRadius]);
  }
  for (let angle = endAngle; angle >= startAngle; angle -= step) {
    points.push([Math.cos(angle) * outerRadius, Math.sin(angle) * outerRadius]);
  }

  return points;
}

// ---------------------------------------------------------------------------
// Radial phylogram (the signature element). Draws the clustering hierarchy as
// branches from the centre out to each leaf, with leaf k landing exactly on
// pie slice k (== bar k) so branch / leaf / bar share one angle by
// construction (wedge alignment). Consumes treeData (bloommap.tree.json).
//
// Geometry (drawn in the BARS' OWN frame so alignment is identity):
//   angle: leaf i at a_i = (i+0.5)/N*2π from +y, clockwise (the d3.arc slice
//          centre); point map polar(r,a) = [sin(a)·r, -cos(a)·r] (d3.arc's own).
//   radius: ALL leaves pinned to rLeaf (so every tip reaches its bar); internal
//          nodes move inward by HEIGHT (edges to farthest descendant leaf), the
//          root nearest the centre at rRoot. A node's angle is the mean angle of
//          its descendant leaves. Each parent->child link = an elbow arc at the
//          parent radius spanning to the child angle, then a radial spoke out to
//          the child radius. No wrapper rotate(): the group inherits only the
//          bloom-centre translate from staticGroup.
// ---------------------------------------------------------------------------
function drawPhylogram(tree, group, leafKeys) {
  if (!tree) return;
  const nLeaves = leafKeys.length;
  if (!nLeaves) return;

  // ANGLE FRAME (the load-bearing fix). The bars are drawn by
  // d3.pie().value(1).sort(null) + d3.arc, whose slice i centre points in
  // screen-direction a_i = (i + 0.5)/N * 2π measured from +y (12 o'clock),
  // clockwise. We draw the WHOLE tree in that exact frame so leaf i lands on
  // bar i by construction -- no wrapper rotate(), no -π/2 patch, no +x frame.
  //   leaf angle:  a_i = (i + 0.5)/N * 2π          (radians, from +y, CW)
  //   point map:   polar(r,a) = [sin(a)·r, -cos(a)·r]   (d3.arc's own mapping)
  // These two together ARE the bar's geometry, so alignment is identity.
  const leafAngle = (i) => ((i + 0.5) / nLeaves) * 2 * Math.PI;
  const polar = (r, a) => [Math.sin(a) * r, -Math.cos(a) * r];

  const leafIndex = new Map(leafKeys.map((k, i) => [k, i]));

  // radii: the phylogram is squeezed into the narrow ring between the centre
  // Voronoi disc (0..innerRadius) and the leaf bars/labels (at middleRadius) --
  // the dark band where the leaf labels sit. Root hub just outside the disc;
  // leaf tips just inside the label ring. Leave a solid-colour buffer at BOTH
  // the inner edge (against the centre disc) and the outer edge (against the
  // bars) so the tree sits as a compressed band, not filling the ring.
  // PHYLO_BUFFER is that margin in px. Tunable taste constant.
  const PHYLO_BUFFER = Math.max(3, radius * 0.012); // ~3pt-scale solid margin
  const rRoot = innerRadius + PHYLO_BUFFER;
  const rLeaf = middleRadius - PHYLO_BUFFER;

  // RADIUS RULE. ALL leaves pin to the single outer radius rLeaf so every leaf
  // tip reaches its bar (the old depth-proportional rule floated shallow leaves
  // -- L34 depth 3, L20 depth 4 -- in mid-band, never touching their bars).
  // Internal nodes move INWARD toward the centre by their HEIGHT (edges to the
  // farthest descendant leaf), not raw depth: height gives clean concentric
  // rings of branch points; depth makes elbows ragged when leaf depth varies.
  //   height(leaf)=0 ; height(n)=1+max(height(child)) ; H=height(root)
  //   r_internal(n) = rLeaf - (rLeaf - rRoot) * (height(n) / H)
  function heightOf(n) {
    if (n.is_leaf || !(n.children && n.children.length)) return 0;
    return 1 + Math.max(...n.children.map(heightOf));
  }
  const H = heightOf(tree);
  const radiusForHeight = (h) =>
    H === 0 ? rLeaf : rLeaf - (rLeaf - rRoot) * (h / H);

  // compute each node's angle (mean of descendant-leaf angles) + radius
  function annotate(n) {
    let ang;
    if (n.is_leaf) {
      const i = leafIndex.get(n.label);
      ang = leafAngle(i == null ? 0 : i);
      n._r = rLeaf; // every leaf reaches the bar
    } else {
      const kids = (n.children || []).map(annotate);
      const angs = kids.map((k) => k.ang);
      ang = angs.reduce((a, b) => a + b, 0) / angs.length;
      n._r = radiusForHeight(heightOf(n));
    }
    n._ang = ang;
    return { ang };
  }
  annotate(tree);

  const g = group.append("g").attr("class", "phylogram");

  // emphasis: branch stroke width grows with log10_lift (clamped), so the
  // splits the clustering was most confident about read as heavier branches.
  const lifts = [];
  (function collect(n) {
    if (typeof n.log10_lift === "number") lifts.push(n.log10_lift);
    (n.children || []).forEach(collect);
  })(tree);
  const liftExtent = d3.extent(lifts);
  const strokeFor = d3
    .scaleLinear()
    .domain(liftExtent[0] === liftExtent[1] ? [0, 1] : liftExtent)
    .range([3.2, 7.2]) // doubled again: bold white dendrogram, very legible
    .clamp(true);
  const PHYLO_STROKE = "#ffffff"; // white, reads cleanly on the tinted wedges

  // draw links parent -> each child
  (function link(n) {
    (n.children || []).forEach((c) => {
      // elbow arc at the PARENT radius from parent angle to child angle. Our
      // angles a are already in d3.arc's native frame (+y, clockwise), so they
      // pass to startAngle/endAngle UNCHANGED -- no +π/2 offset.
      const a0 = Math.min(n._ang, c._ang);
      const a1 = Math.max(n._ang, c._ang);
      const arc = d3
        .arc()
        .innerRadius(n._r)
        .outerRadius(n._r)
        .startAngle(a0)
        .endAngle(a1);
      g.append("path")
        .attr("d", arc())
        .attr("fill", "none")
        .attr("stroke", PHYLO_STROKE)
        .attr("stroke-width", strokeFor(n.log10_lift ?? liftExtent[0]))
        .attr("stroke-opacity", 0.95)
        .attr("stroke-linecap", "round");
      // radial spoke at the CHILD angle, from the parent radius out to the
      // child radius (a leaf child's radius is rLeaf, so its spoke ends on the bar).
      const [x0, y0] = polar(n._r, c._ang);
      const [x1, y1] = polar(c._r, c._ang);
      g.append("line")
        .attr("x1", x0)
        .attr("y1", y0)
        .attr("x2", x1)
        .attr("y2", y1)
        .attr("stroke", PHYLO_STROKE)
        .attr("stroke-width", strokeFor(c.log10_lift ?? liftExtent[0]))
        .attr("stroke-opacity", 0.95)
        .attr("stroke-linecap", "round");
      link(c);
    });
  })(tree);

  // node dots: small markers at internal nodes, larger at the root
  (function dots(n) {
    const [x, y] = polar(n._r, n._ang);
    if (!n.is_leaf) {
      g.append("circle")
        .attr("cx", x)
        .attr("cy", y)
        // the root (depth 0) is marked RED -- the origin of the whole tree;
        // internal nodes stay white to match the dendrogram strokes.
        .attr("r", n.depth === 0 ? 6 : 3.4)
        .attr("fill", n.depth === 0 ? "#d62828" : PHYLO_STROKE);
    }
    (n.children || []).forEach(dots);
  })(tree);
}

// ---------------------------------------------------------------------------
// Right-edge legend (print-canonical). A poster has no hover, so every drawn
// feature ID gets a row mapping ID -> full dimension name.
// Only IDs actually drawn in the bloom are listed, deduplicated, sorted by ID,
// laid out in as many sub-columns as fit the reserved strip. If more IDs exist
// than fit, the top-ranked subset is shown and the overflow is stated (never a
// silent truncation).
// ---------------------------------------------------------------------------
function drawLegend(svgSel, drawnIds, config) {
  if (!legendActive || !drawnIds.length) return;
  const L = config.legend;
  const band = config.titleBandPx || 0;
  const stripX = width - legendW; // strip occupies [width-legendW, width]
  const g = svgSel
    .append("g")
    .attr("class", "legend")
    .attr("transform", `translate(${stripX},${band})`);

  // hairline separating the bloom from the legend
  g.append("line")
    .attr("x1", 0).attr("y1", L.pad)
    .attr("x2", 0).attr("y2", height - band - L.pad)
    .attr("stroke", "#ddd").attr("stroke-width", 1);

  const i2t = (metaData && metaData.id_to_text) || {};
  // sort by ID string (IDs are zero-padded so lexical == numeric order)
  const ids = drawnIds.slice().sort();

  // layout: rows that fit the height (below the title band), columns that fit
  const usableTop = L.pad + L.headerSize + 14;
  const top = usableTop;
  const usableH = height - band - top - L.pad;
  const rowsPerCol = Math.max(1, Math.floor(usableH / L.rowH));
  const colW =
    Math.floor(
      (legendW - 2 * L.pad + L.colGap) / (estimateLegendColWidth(L) + L.colGap),
    ) || 1;
  const maxCols = Math.max(1, colW);
  const capacity = rowsPerCol * maxCols;

  const shown = ids.slice(0, capacity);
  const dropped = ids.length - shown.length;

  // title
  g.append("text")
    .attr("x", L.pad)
    .attr("y", L.pad + L.headerSize)
    .attr("font-size", `${L.headerSize}px`)
    .attr("font-weight", "bold")
    .attr("fill", "#222")
    .text(L.title);

  // entries
  shown.forEach((id, k) => {
    const col = Math.floor(k / rowsPerCol);
    const row = k % rowsPerCol;
    const x = L.pad + col * (estimateLegendColWidth(L) + L.colGap);
    const y = top + row * L.rowH + L.fontSize;
    g.append("text")
      .attr("x", x)
      .attr("y", y)
      .attr("font-size", `${L.fontSize}px`)
      .attr("font-family", "monospace")
      .attr("fill", "#222")
      .text(`${id}  ${i2t[id] || "dim?"}`);
  });

  // overflow honesty: never a silent truncation
  if (dropped > 0) {
    g.append("text")
      .attr("x", L.pad)
      .attr("y", height - L.pad + L.fontSize - 2)
      .attr("font-size", `${L.fontSize}px`)
      .attr("fill", "#a00")
      .text(
        `(+${dropped} more not shown at this paper size; ${ids.length} drawn IDs total)`,
      );
  }
}

// width estimate for one legend sub-column: "C0001  CUST0000123456" ~ 20 chars
// of monospace at fontSize ~0.6em advance.
function estimateLegendColWidth(L) {
  return Math.ceil(20 * L.fontSize * 0.62);
}

// Title band across the top of the poster. Names the mark (UltraDim BloomMap)
// and states what the figure shows, drawn from meta (domain, n_leaves, n_rows,
// n_dims, orientation). Academic, no emoji.
function drawTitle(svgSel, config) {
  const band = config.titleBandPx || 0;
  if (!band || !metaData) return;
  const g = svgSel.append("g").attr("class", "poster-title");
  const cx = width / 2;
  g.append("text")
    .attr("x", cx)
    .attr("y", band * 0.52)
    .attr("text-anchor", "middle")
    .attr("font-family", "Georgia, 'Times New Roman', serif")
    .attr("font-size", `${Math.round(band * 0.42)}px`)
    .attr("font-weight", "bold")
    .attr("fill", "#1a1a1a")
    .text("UltraDim BloomMap");
  const o = metaData.orientation || {};
  // Petal-label descriptor: when the meta carries leaf_exemplars the labels are
  // the movie nearest each cluster centroid (not the feature-axis dictionary).
  const petalDesc = datasetHasLeafTitles()
    ? "cluster labels = title nearest centroid"
    : `petal labels: ${o.dictionary || "feature id"}`;
  // In cell-member mode name what the numbered cells are, so a website visitor
  // knows the numbers are public movieIds and that hovering reveals the title.
  const cellDesc = datasetHasCellMembers()
    ? "  |  cells = MovieLens movieIds nearest each centroid — hover for titles (HTML)"
    : "";
  const sub =
    `${metaData.n_leaves} clusters of ${Number(metaData.n_rows).toLocaleString()} ` +
    `${(o.cluster_axis || "items")} over ${Number(metaData.n_dims).toLocaleString()} ` +
    `${(o.feature_axis || "dimensions")}  |  ${petalDesc}${cellDesc}`;
  g.append("text")
    .attr("x", cx)
    .attr("y", band * 0.86)
    .attr("text-anchor", "middle")
    .attr("font-family", "Georgia, 'Times New Roman', serif")
    .attr("font-size", `${Math.round(band * 0.2)}px`)
    .attr("fill", "#555")
    .text(sub);
}

// Main visualization creation function
function createVisualization() {
  try {
    console.log("Starting visualization creation...");
    validateData(clusterData, volumeData);
    
    const config = getConfigFromUI();
    initializeVisualization();

    const staticGroup = svg.append("g")
      .attr("transform", `translate(${bloomCx},${bloomCy})`);

    const rotatableGroup = svg.append("g")
      .attr("transform", `translate(${bloomCx},${bloomCy})`);

    const clusters = Object.keys(clusterData).filter(k => k !== 'global');

    // Lineage colours from the tree (siblings share a family hue). Built once
    // per render; null map -> ordinal fallback inside clusterColorByKey.
    leafColorMap = buildLineageColors(treeData);

    // Create the base arc for consistent measurements
    const arc = d3.arc()
      .innerRadius(innerRadius)
      .outerRadius(middleRadius);
      
    const pie = d3.pie()
      .value(d => 1)
      .sort(null);

    const pieData = pie(clusters);

    // Create donut rings first
    //const {middleArc} = createDonutRings(clusters, staticGroup, volumeData);
    //const config = getConfigFromUI(); // Make sure this is at the top of createVisualization
    const {middleArc} = createDonutRings(clusters, staticGroup, volumeData, config); // Pass config as parameter

    // Build the per-cell movie-title index once (cell-member mode only).
    buildCellTitleIndex();

    // Create global treemap. In cell-member mode the centre disc's cells are the
    // globally most-central MOVIES (root_members), one per cell; otherwise they are
    // the global top features (themes.global).
    if (clusterData['global'] || datasetHasCellMembers()) {
      const clipPolygon = getClipPolygon(0, 2 * Math.PI, 0, innerRadius);
      const globalData = datasetHasCellMembers()
        ? cellMemberData(cellMembersFor('global', 'global'), config.wordCounts.global)
        : clusterData['global'].slice(0, config.wordCounts.global);
      const treemap = createVoronoiTreemap(
        globalData,
        clipPolygon,
        'global'
      );
      if (treemap) {
        drawVoronoiTreemap(treemap, 0, 0, 'global', 'Global', staticGroup, 0);
      }
    }

    // Create cluster treemaps
    // Petal titles are collected during the petal loop and drawn AFTER the
    // de-rotation pass (so the pass never strips their radial orientation).
    const petalTitleJobs = [];
    pieData.forEach((d, i) => {
      const cluster = clusterData[d.data];
      if (cluster) {
        const radialPos = middleRadius + (outerRadius - middleRadius) * config.treemap.radialPosition;
        const placementArc = d3.arc()
          .innerRadius(radialPos)
          .outerRadius(radialPos);
	
        // WEDGE ALIGNMENT (kaito exemplar mechanism, verified by rendering kaito's
        // unmodified renderer on this data): pre-rotate BOTH the placement centroid
        // AND every clip-polygon point by -rotationAngle in geometry. This is what
        // produces the sheared turbine-blade bloom AND lands each petal over its
        // bar. The petal group stays translate-only (NOT spun); the rotation lives
        // entirely in the pre-rotated geometry. (My earlier "group spin" rewrite
        // removed this and broke the bloom -- do not reintroduce a group spin.)
        const centroid = placementArc.centroid(d);
        const globalRotation = config.visualization.rotationAngle;
        // The kaito-pre-rotated petal leans HALF a slice clockwise of its bar (its
        // colour petal drifts into the next lane). Counter-shift the pre-rotation by
        // half the petal's OWN slice width so each petal re-centres on its bar --
        // verified visually: the red 1381 bar then radiates straight into its red
        // petal, green into green, etc. Derived per-petal from d's slice width, so
        // exact for ANY leaf count N (not a fixed angular fudge). Sign: minus = the
        // counter-clockwise direction that brings the CW-leaning petal back.
        const halfSliceDeg = ((d.endAngle - d.startAngle) / 2) * (180 / Math.PI);
        // Base centring is -halfSliceDeg; per request, rotate ONE more slice
        // clockwise (+2*halfSliceDeg) -> net +halfSliceDeg. Still derived per-petal
        // from d's slice width, so exact for any leaf count N.
        const rotationCompensation = -1 * globalRotation - halfSliceDeg + 2 * halfSliceDeg;
        const rotatedCentroid = rotatePoint(centroid[0], centroid[1], rotationCompensation);

        const angle = (d.startAngle + d.endAngle) / 2;

        const clipPolygon = getClipPolygon(d.startAngle, d.endAngle, middleRadius, outerRadius);
        const rotatedClipPolygon = clipPolygon.map(point => {
          const rotated = rotatePoint(point[0], point[1], rotationCompensation);
          return [rotated.x, rotated.y];
        });


        // In cell-member mode the petal's cells are the leaf's nearest-centroid
        // MOVIES (one per cell); otherwise the leaf's top features (themes[leaf]).
        const cellData = datasetHasCellMembers()
          ? cellMemberData(cellMembersFor(i, d.data), config.wordCounts.clusters)
          : cluster.slice(0, config.wordCounts.clusters);
        const treemap = createVoronoiTreemap(
          cellData,
          rotatedClipPolygon,
          i
        );

        if (treemap) {
          drawVoronoiTreemap(
            treemap,
            rotatedCentroid.x,
            rotatedCentroid.y,
            i,
            d.data,
            rotatableGroup,
            angle
          );
        }

        // Collect the petal title (movie nearest this leaf's centroid) to draw
        // ON the petal wedge, AFTER the de-rotation pass below so it is not
        // stripped. The petal's coloured Voronoi tessellation fills the whole clip
        // band [middleRadius, outerRadius]; centre the title on that band, biased
        // slightly OUTWARD (0.54) so it sits over the saturated rim colour rather
        // than the pale inner edge, and give it the band's near-full radial length
        // so long titles read in full instead of ellipsising. Reads along the
        // petal's radial direction (petalDeg); tangential budget = arc width there.
        const titles = leafTitles(d.data);
        if (titles.length) {
          const band = outerRadius - middleRadius;
          const rTitle = middleRadius + 0.54 * band;
          const scale = rTitle / radialPos;
          const cx = rotatedCentroid.x * scale;
          const cy = rotatedCentroid.y * scale;
          const petalDeg = (Math.atan2(cy, cx) * 180) / Math.PI;
          const span = Math.abs(d.endAngle - d.startAngle);
          petalTitleJobs.push({
            fill: clusterColorByKey(d.data, i),
            cx,
            cy,
            petalDeg,
            radialLen: band * 0.94,
            arcWidth: Math.max(8, span * rTitle),
            titles,
            // Full top-3 titles for the hover layer (the printed label may be
            // just the nearest one; hover reveals the rest). Empty string => no
            // hover attribute added (off mode, or non-title dataset).
            hoverTitle: leafHoverTitle(d.data),
          });
        }
      }
    });

    // The rotation is baked into each petal's pre-rotated geometry (kaito), so the
    // petal group carries ONLY the bloom-centre translation -- no flower-spin. Strip
    // any leftover text rotation so petal labels read horizontal.
    rotatableGroup.selectAll("text")
      .attr("transform", function () {
        const t = d3.select(this).attr("transform") || "";
        const m = t.match(/translate\(([-\d.]+),([-\d.]+)\)/);
        return m ? `translate(${m[1]},${m[2]}) rotate(0)` : t;
      });
    rotatableGroup.attr("transform", `translate(${bloomCx},${bloomCy})`);

    // Petal titles: drawn LAST into the bloom-centre frame (a fresh child of
    // rotatableGroup, added after the de-rotation pass so their radial baseline
    // survives). Each rides its petal's pre-rotated centroid + radial direction.
    if (petalTitleJobs.length) {
      const titleGroup = rotatableGroup.append("g").attr("class", "petal-titles");
      petalTitleJobs.forEach((j) => {
        drawPetalTitle(
          titleGroup,
          j.fill,
          j.cx,
          j.cy,
          j.petalDeg,
          j.radialLen,
          j.arcWidth,
          j.titles,
          j.hoverTitle,
        );
      });
    }

    // Radial phylogram (signature element) — drawn LAST so its branches sit on
    // top of the pale wedge band, in the spoke ring between the centre disc and
    // the bars. The tree is drawn in the BARS' OWN frame (leaf i angle == bar i
    // angle, d3.arc point map), so leaf tips land on their bars by construction.
    // staticGroup already carries the bloom-centre translate; the bars sit in a
    // plain (transform-less) child of it. So the phylogram group is also a plain
    // child of staticGroup with NO transform of its own -- it inherits exactly
    // the bloom-centre translate and nothing else. NO rotate(): any spin would
    // slide leaves off their bars.
    if (treeData) {
      const phyloGroup = staticGroup.append("g");
      drawPhylogram(treeData, phyloGroup, clusters);
    }

    // Right-edge legend: collect every drawn ID across the centre + all petals.
    if (legendActive) {
      const drawn = new Set();
      Object.keys(clusterData).forEach((key) => {
        (clusterData[key] || []).forEach((entry) => drawn.add(entry[0]));
      });
      drawLegend(svg, Array.from(drawn), config);
    }

    // Poster title band across the top.
    drawTitle(svg, config);

  } catch (error) {
    console.error("Failed to create visualization:", error);
    displayError(error.message);
  }
}

// Global state
let clusterData = {}, volumeData = {};

// Event listeners
window.addEventListener('beforeunload', cleanup);

// SVG Download functionality
document.getElementById("downloadSVG").addEventListener("click", () => {
  const svgData = new XMLSerializer().serializeToString(svg.node());
  const svgBlob = new Blob([svgData], {type: "image/svg+xml;charset=utf-8"});
  const svgUrl = URL.createObjectURL(svgBlob);
  const downloadLink = document.createElement("a");
  downloadLink.href = svgUrl;
  downloadLink.download = "radial_clusters.svg";
  document.body.appendChild(downloadLink);
  downloadLink.click();
  document.body.removeChild(downloadLink);
  URL.revokeObjectURL(svgUrl);
});

// Update visualization button
document.getElementById("updateViz").addEventListener("click", () => {
  createVisualization();
});


// Data source is configurable so one renderer drives any dataset.
// window.BLOOMMAP_SOURCE = { themes, volumes, meta?, tree? } (paths), or
// defaults to the original Bible files (the Phase-0 provenance baseline).
const DATA_SOURCE =
  (typeof window !== "undefined" && window.BLOOMMAP_SOURCE) || {
    themes: "kjb_proc_themes.json",
    volumes: "kjb_cluster_volumes.json",
    meta: null,
    tree: null,
  };

// meta (id->text dictionary, leaf_order) and tree (phylogram) are optional:
// a minimal corpus has neither; a corpus with a dictionary and ordering has both.
let metaData = null, treeData = null;

Promise.all([
  d3.json(DATA_SOURCE.themes),
  d3.json(DATA_SOURCE.volumes),
  DATA_SOURCE.meta ? d3.json(DATA_SOURCE.meta) : Promise.resolve(null),
  DATA_SOURCE.tree ? d3.json(DATA_SOURCE.tree) : Promise.resolve(null),
])
  .then(([themeData, loadedVolumeData, loadedMeta, loadedTree]) => {
    try {
      validateData(themeData, loadedVolumeData);
      clusterData = themeData;
      volumeData = loadedVolumeData;
      metaData = loadedMeta;
      treeData = loadedTree;
      setTimeout(createVisualization, 0);
    } catch (error) {
      console.error("Data validation failed:", error);
      displayError(error.message);
    }
  })
  .catch((error) => {
    console.error("Error loading data:", error);
    displayError("Failed to load visualization data");
  });






