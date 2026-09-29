// ===========================================================================
// UltraDim BloomMap -- Paper-Size Layout Profiles (ISO 216: A0..A3)
// ===========================================================================
//
// DESIGN PRINCIPLE: "paper size is a LAYOUT PROFILE, not a uniform scale."
//
// Naively, you might render the BloomMap once at 1400x1400 px and scale the
// whole bitmap up to A0 or down to A3. That is wrong for a poster:
//
//   1. FONT FLOORS ARE PHYSICAL, NOT PIXEL. A label must be legible when the
//      printed sheet is held in the hand. Legibility is governed by the
//      physical height of the glyph (in millimetres), independent of paper
//      size. So we express minimum font sizes in mm and convert to px at the
//      export DPI. A 1.8 mm petal label is 1.8 mm on A0 and 1.8 mm on A3 --
//      uniform scaling would instead shrink it to an unreadable size on A3.
//
//   2. CONTENT DENSITY SCALES WITH USABLE AREA, NOT LINEARLY WITH WIDTH. A
//      bigger sheet has more usable area to spend on detail, so it can DRAW
//      more features and a wider legend without crowding. A smaller sheet
//      must draw FEWER features so the (physically floored) fonts still fit.
//      Density is therefore a per-paper editorial decision, monotonic in area
//      (A0 >= A1 >= A2 >= A3 for every density field).
//
//   3. EXPORT IS AT A PRINT DPI. Screen pixels are irrelevant to a printed
//      poster; what matters is dots-per-inch on paper. We raster at the
//      profile DPI (300 for A1..A3; 200 for A0 to bound the pixel count --
//      see the A0 entry for the exact target pixel dimensions and why).
//
// This module is PURE DATA + small PURE HELPER FUNCTIONS. It performs no DOM
// access, makes no d3 calls, and has no external dependencies. It is safe to
// load in the browser via <script> (attaches to window.BLOOMMAP_PAPER) and to
// require() in Node (module.exports). The renderer (visualization.js) is the
// only consumer; this file deliberately does NOT touch it.
//
// ASCII only throughout (no emoji): a professor reads this.
// ===========================================================================

(function (root) {
  "use strict";

  // -------------------------------------------------------------------------
  // 1. ISO 216 dimensions (PORTRAIT, millimetres). Width x Height portrait;
  //    landscape swaps them. These are the exact standard sizes -- the A
  //    series halves the long edge at each step (A0 -> A1 -> A2 -> A3), so the
  //    AREA roughly halves each step. We use the exact rounded ISO values, not
  //    the irrational sqrt(2) ideal, because printers/RIPs expect these.
  // -------------------------------------------------------------------------
  var ISO_216_MM = {
    A0: { widthMm: 841, heightMm: 1189 }, // 0.999 m^2 nominal; the reference sheet
    A1: { widthMm: 594, heightMm: 841 }, // A0 long edge halved (1189/2 = 594.5 -> 594)
    A2: { widthMm: 420, heightMm: 594 }, // A1 long edge halved (841/2 = 420.5 -> 420)
    A3: { widthMm: 297, heightMm: 420 } // A2 long edge halved (594/2 = 297)
  };

  // -------------------------------------------------------------------------
  // 2. PROFILES TABLE.
  //
  // Density rationale (monotonic with usable area):
  //   The reference renderer (visualization.js) draws ~100 global/centre words
  //   and ~50 words per petal at its hardcoded 1400x1400 canvas, which prints
  //   roughly at A2 scale. We anchor A2 near those reference values, then
  //   spend the extra area of larger sheets on MORE detail and recover space
  //   on smaller sheets by drawing LESS. Area roughly halves per step down, so
  //   feature counts step down in kind (but never below a useful minimum, so
  //   even A3 still tells the story).
  //
  //   globalFeatures : Voronoi cells in the centre disc (VIZ_CONFIG.wordCounts.global).
  //   petalFeatures  : Voronoi cells per outer petal (VIZ_CONFIG.wordCounts.clusters).
  //   legendRows/Cols: a printed key mapping cluster IDs -> labels. The legend
  //                    capacity (rows*cols) is the max distinct IDs the sheet
  //                    can show. A0 must be able to show ~1200 IDs (a
  //                    large legend budget), hence 200 rows x 6 cols =
  //                    1200. Smaller sheets show proportionally fewer.
  //
  // Font floor rationale (physical mm, identical across all sizes by design):
  //   petal 1.8 mm  : the smallest petal-cell labels; ~5 pt, the practical
  //                   floor for a poster glyph read at arm's length.
  //   centre 2.2 mm : centre-disc words sit denser; a slightly larger floor
  //                   keeps them legible against the dark centre fill.
  //   leafLabel 2.4 mm: phylogram leaf / cluster names -- structural, must read.
  //   legend 2.0 mm : legend rows; small but must be scannable when sought out.
  //   title 6.0 mm  : poster title; large enough to read across a room.
  //   (The floors are the SAME object for every profile precisely because
  //    legibility is physical; only the px conversion differs via DPI.)
  // -------------------------------------------------------------------------

  // Shared physical font floors (mm). One object, reused by every profile,
  // to make the "floors are physical, not per-paper" principle literal in code.
  var FONT_FLOOR_MM = {
    petal: 1.8, // ~5 pt smallest petal label; poster legibility floor at arm's length
    centre: 2.2, // centre-disc words are denser/darker -> a touch larger
    leafLabel: 2.4, // phylogram leaf / cluster names; structural, must read clearly
    legend: 2.0, // legend rows; small but scannable on close inspection
    title: 6.0 // poster title; readable across a room
  };

  var PAPER_PROFILES = {
    // ---- A0: biggest sheet -> most detail, widest legend, DPI bounded to 200.
    A0: {
      name: "A0",
      widthMm: ISO_216_MM.A0.widthMm,
      heightMm: ISO_216_MM.A0.heightMm,
      // DPI 200 (not 300) to BOUND the raster pixel count on the largest sheet:
      //   width px  = 841  * 200 / 25.4 ~= 6622 px
      //   height px = 1189 * 200 / 25.4 ~= 9362 px  (target ~6622 x 9362)
      // At 300 DPI A0 would be ~9933 x 14043 px (~140 MP) -- a heavy PNG that
      // strains browser canvas limits and download size. 200 DPI on a sheet
      // viewed from >1 m still resolves finer than the eye; 300 buys nothing
      // at that viewing distance. (A1..A3 are smaller, so 300 stays safe there.)
      dpi: 200,
      fontFloorMm: FONT_FLOOR_MM,
      density: {
        globalFeatures: 120, // most centre cells; the big sheet can carry the detail
        petalFeatures: 50, // matches the renderer's richest per-petal count
        legendRows: 200, // 200 x 6 = 1200 IDs -> a large legend budget
        legendCols: 6
      },
      strokeScale: 2.0, // strokes scale ~with linear size; A0 long edge ~= 2x A2's
      legendColWidthMm: 70, // wide enough for an ID + a short label at 2.0 mm type
      marginMm: 25 // generous print margin for a large mounted poster
    },

    // ---- A1: large -> rich detail, full 300 DPI (pixel count comfortable).
    A1: {
      name: "A1",
      widthMm: ISO_216_MM.A1.widthMm,
      heightMm: ISO_216_MM.A1.heightMm,
      // DPI 300:
      //   width px  = 594 * 300 / 25.4 ~= 7016 px
      //   height px = 841 * 300 / 25.4 ~= 9933 px  (target ~7016 x 9933)
      // ~70 MP -- large but within typical browser canvas limits; full print DPI.
      dpi: 300,
      fontFloorMm: FONT_FLOOR_MM,
      density: {
        globalFeatures: 90, // between A0 (120) and A2 (60): area ~0.5x A0
        petalFeatures: 36, // between A0 (50) and A2 (24)
        legendRows: 120, // 120 x 5 = 600 IDs
        legendCols: 5
      },
      strokeScale: 1.5, // A1 long edge ~= 1.4x A2's; round to a clean 1.5
      legendColWidthMm: 62,
      marginMm: 20
    },

    // ---- A2: ~ the reference scale of the original 1400x1400 renderer.
    A2: {
      name: "A2",
      widthMm: ISO_216_MM.A2.widthMm,
      heightMm: ISO_216_MM.A2.heightMm,
      // DPI 300:
      //   width px  = 420 * 300 / 25.4 ~= 4961 px
      //   height px = 594 * 300 / 25.4 ~= 7016 px  (target ~4961 x 7016)
      dpi: 300,
      fontFloorMm: FONT_FLOOR_MM,
      density: {
        globalFeatures: 60, // ~ the renderer's default-ish centre richness on this sheet
        petalFeatures: 24, // about half of A0's per-petal count, matching area
        legendRows: 70, // 70 x 4 = 280 IDs
        legendCols: 4
      },
      strokeScale: 1.0, // A2 is the baseline; base stroke widths unscaled
      legendColWidthMm: 55,
      marginMm: 16
    },

    // ---- A3: smallest sheet -> fewest features so physical fonts still fit.
    A3: {
      name: "A3",
      widthMm: ISO_216_MM.A3.widthMm,
      heightMm: ISO_216_MM.A3.heightMm,
      // DPI 300:
      //   width px  = 297 * 300 / 25.4 ~= 3508 px
      //   height px = 420 * 300 / 25.4 ~= 4961 px  (target ~3508 x 4961)
      // This is also the canonical "A3 == ISO A3" sanity number for tests.
      dpi: 300,
      fontFloorMm: FONT_FLOOR_MM,
      density: {
        globalFeatures: 40, // floor on usefulness: still enough centre cells to read
        petalFeatures: 18, // sparse petals so 1.8 mm labels do not collide
        legendRows: 45, // 45 x 3 = 135 IDs (a curated subset, not the full budget)
        legendCols: 3
      },
      strokeScale: 0.75, // smaller sheet -> thinner strokes keep fine detail crisp
      legendColWidthMm: 48,
      marginMm: 12
    }
  };

  var DEFAULT_PROFILE = "A1"; // a practical, common poster size; the sensible default

  // -------------------------------------------------------------------------
  // 3. PURE HELPER FUNCTIONS (no side effects, no DOM, no d3).
  // -------------------------------------------------------------------------

  // Millimetres -> device pixels at a given DPI. 1 inch = 25.4 mm exactly.
  // Rounded to whole pixels (canvas/raster dimensions are integers).
  function mmToPx(mm, dpi) {
    return Math.round((mm * dpi) / 25.4);
  }

  // Device pixels -> millimetres at a given DPI. Inverse of mmToPx (unrounded,
  // since a length in mm is continuous).
  function pxToMm(px, dpi) {
    return (px * 25.4) / dpi;
  }

  // Canvas pixel dimensions for a profile at its export DPI. "portrait" keeps
  // the ISO width x height; "landscape" swaps them. Defaults to portrait.
  function canvasPx(profile, orientation) {
    var w = profile.widthMm;
    var h = profile.heightMm;
    if (orientation === "landscape") {
      var t = w;
      w = h;
      h = t;
    }
    return {
      width: mmToPx(w, profile.dpi),
      height: mmToPx(h, profile.dpi)
    };
  }

  // Convert a profile's physical font floors (mm) to pixel floors at its DPI.
  // Returns a NEW object with the same keys (petal, centre, leafLabel, ...),
  // each value an integer pixel size the renderer can hand to SVG/canvas.
  function fontFloorsPx(profile) {
    var out = {};
    var floors = profile.fontFloorMm;
    for (var key in floors) {
      if (Object.prototype.hasOwnProperty.call(floors, key)) {
        out[key] = mmToPx(floors[key], profile.dpi);
      }
    }
    return out;
  }

  // Max distinct IDs the legend can show on this sheet: rows * cols.
  function legendCapacity(profile) {
    return profile.density.legendRows * profile.density.legendCols;
  }

  // Resolve a profile from a name string OR a profile object.
  //   - undefined/null  -> the DEFAULT_PROFILE ("A1")
  //   - string          -> PAPER_PROFILES[name] (throws on unknown name)
  //   - object          -> returned as-is (caller-supplied custom profile)
  function getProfile(nameOrObj) {
    if (nameOrObj === undefined || nameOrObj === null) {
      return PAPER_PROFILES[DEFAULT_PROFILE];
    }
    if (typeof nameOrObj === "string") {
      var p = PAPER_PROFILES[nameOrObj];
      if (!p) {
        throw new Error(
          "Unknown paper profile: '" +
            nameOrObj +
            "'. Known profiles: " +
            Object.keys(PAPER_PROFILES).join(", ")
        );
      }
      return p;
    }
    if (typeof nameOrObj === "object") {
      return nameOrObj;
    }
    throw new Error(
      "getProfile expects a profile name (string) or profile object; got " +
        typeof nameOrObj
    );
  }

  // -------------------------------------------------------------------------
  // 4. SELF-CHECK. validateProfiles() returns {ok:true} or THROWS with a clear
  //    message. Checks: required keys present; ISO dims match the standard;
  //    every density field is monotonic non-increasing across A0 >= A1 >= A2
  //    >= A3 (the core "bigger paper draws more" invariant).
  // -------------------------------------------------------------------------
  function validateProfiles() {
    var order = ["A0", "A1", "A2", "A3"]; // largest -> smallest
    var requiredTop = [
      "name",
      "widthMm",
      "heightMm",
      "dpi",
      "fontFloorMm",
      "density",
      "strokeScale",
      "legendColWidthMm",
      "marginMm"
    ];
    var requiredFontFloor = ["petal", "centre", "leafLabel", "legend", "title"];
    var requiredDensity = [
      "globalFeatures",
      "petalFeatures",
      "legendRows",
      "legendCols"
    ];

    // (a) Every profile exists, has every required key, and ISO dims match.
    order.forEach(function (key) {
      var p = PAPER_PROFILES[key];
      if (!p) {
        throw new Error("validateProfiles: missing profile '" + key + "'");
      }
      requiredTop.forEach(function (k) {
        if (!(k in p)) {
          throw new Error(
            "validateProfiles: profile '" + key + "' missing key '" + k + "'"
          );
        }
      });
      if (p.name !== key) {
        throw new Error(
          "validateProfiles: profile '" +
            key +
            "' has name '" +
            p.name +
            "' (must equal its key)"
        );
      }
      requiredFontFloor.forEach(function (k) {
        if (typeof p.fontFloorMm[k] !== "number") {
          throw new Error(
            "validateProfiles: profile '" +
              key +
              "' fontFloorMm missing numeric '" +
              k +
              "'"
          );
        }
      });
      requiredDensity.forEach(function (k) {
        if (typeof p.density[k] !== "number") {
          throw new Error(
            "validateProfiles: profile '" +
              key +
              "' density missing numeric '" +
              k +
              "'"
          );
        }
      });
      // ISO dimension match (the canonical sanity check).
      var iso = ISO_216_MM[key];
      if (p.widthMm !== iso.widthMm || p.heightMm !== iso.heightMm) {
        throw new Error(
          "validateProfiles: profile '" +
            key +
            "' dims " +
            p.widthMm +
            "x" +
            p.heightMm +
            " do not match ISO 216 " +
            iso.widthMm +
            "x" +
            iso.heightMm
        );
      }
      // DPI must be positive.
      if (!(p.dpi > 0)) {
        throw new Error(
          "validateProfiles: profile '" + key + "' has non-positive dpi"
        );
      }
    });

    // (b) Density monotonic non-increasing A0 >= A1 >= A2 >= A3 for EVERY field.
    requiredDensity.forEach(function (field) {
      for (var i = 1; i < order.length; i++) {
        var bigger = PAPER_PROFILES[order[i - 1]].density[field];
        var smaller = PAPER_PROFILES[order[i]].density[field];
        if (smaller > bigger) {
          throw new Error(
            "validateProfiles: density." +
              field +
              " not monotonic: " +
              order[i - 1] +
              "=" +
              bigger +
              " < " +
              order[i] +
              "=" +
              smaller +
              " (bigger paper must draw >= smaller paper)"
          );
        }
      }
    });

    // (c) Area monotonic strictly decreasing (A0 > A1 > A2 > A3) -- a guard that
    //     the dims themselves were not transcribed out of order.
    for (var j = 1; j < order.length; j++) {
      var bp = PAPER_PROFILES[order[j - 1]];
      var sp = PAPER_PROFILES[order[j]];
      var areaBig = bp.widthMm * bp.heightMm;
      var areaSmall = sp.widthMm * sp.heightMm;
      if (!(areaBig > areaSmall)) {
        throw new Error(
          "validateProfiles: area not strictly decreasing: " +
            order[j - 1] +
            "=" +
            areaBig +
            " mm^2 vs " +
            order[j] +
            "=" +
            areaSmall +
            " mm^2"
        );
      }
    }

    return { ok: true };
  }

  // -------------------------------------------------------------------------
  // 5. EXPORTS. Dual-target: browser <script> -> window.BLOOMMAP_PAPER;
  //    Node require() -> module.exports. The typeof guard means neither path
  //    fails in the other environment.
  // -------------------------------------------------------------------------
  var API = {
    ISO_216_MM: ISO_216_MM,
    PAPER_PROFILES: PAPER_PROFILES,
    DEFAULT_PROFILE: DEFAULT_PROFILE,
    mmToPx: mmToPx,
    pxToMm: pxToMm,
    canvasPx: canvasPx,
    fontFloorsPx: fontFloorsPx,
    legendCapacity: legendCapacity,
    getProfile: getProfile,
    validateProfiles: validateProfiles
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = API; // Node / CommonJS
  }
  if (root) {
    root.BLOOMMAP_PAPER = API; // browser global (window)
  }
})(typeof window !== "undefined" ? window : this);
