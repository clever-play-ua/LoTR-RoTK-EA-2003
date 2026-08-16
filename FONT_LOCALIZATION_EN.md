# LOTR: The Return of the King (2003, EA) — Ukrainian Font/Text Localization

Working reference for continuing the Cyrillic/Ukrainian font patching effort for the PC
version of *The Lord of the Rings: The Return of the King* (EA Redwood Shores, 2003).

Game install used for all testing:
`C:\Program Files (x86)\Return of the King\` (Russian localized install, used as the base
for all rebuilds — its Cyrillic glyphs for codes 192-255 already render correctly in-game).
A clean English install also exists at
`C:\Program Files (x86)\EA GAMES\LOTR - The Return of the King ENG\` (used once, only to
compare what the ORIGINAL English 165-191 slots contained).

---

## 1. Container format: `.scw`

Every `.scw` file (both the localization archive `GlobScen.scw` and the per-level audio
archives like `cra01.scw`) uses the **same custom chunk container**. This is now
implemented, documented field-by-field, and validated byte-for-byte in
**`lotr_scw_tool.py`** (this repo) — treat that file as the authoritative reference, not
the prose below (kept here as a summary; if the two ever disagree, trust the code and its
own docstring, which was cross-checked against a decompile of the real, open-source
**Game Extractor** tool's `org.watto.ge.plugin.archive.Plugin_SCW` class):

- Chunk tags are stored **byte-reversed** on disk. Examples: raw bytes `COHS` on disk =
  `SHOC` read forward; `RDHS` = `SHDR`; `LLIF` = `FILL`; `LRTC` = `CTRL`; `ONOS` = `SONO`.
- Chunk header = 4-byte reversed tag + 4-byte little-endian length (length **includes**
  the 8-byte header itself, i.e. "next chunk starts at `this_offset + length`").
- Inside a `COHS`/`ONOS` chunk, byte offsets **relative to the chunk's own tag**:
  `[8:16)` 8 reserved bytes, `[16:20)` a file-header tag (`RDHS`=SHDR / `TADS`=SDAT /
  `tadR`=Rdat/compressed). For an `SHDR` chunk specifically: `[24:28)` = `ext` (reversed,
  e.g. `"font"`, `"subT"`), `[32:36)` = `decompLen` (little-endian u32, total decompressed
  size of the resource across every chunk in its chain). **An earlier version of this
  section had the file-header tag 8 bytes too early (at `+8` instead of `+16`) — that was
  wrong; it went uncorrected for a long time because font work still happened to produce
  working output (see below for why), but do not copy the old numbers from memory.**
- For an `SDAT` (uncompressed) chunk, the raw payload starts at byte offset **64**
  (relative to the chunk's own tag) and runs to the end of the chunk — this part of the
  old numbers (64-byte overhead, 8128 usable bytes out of an 8192-byte chunk) was correct
  and matches `lotr_scw_tool.py`'s `_SDAT_PAYLOAD_PREFIX`.
- `Rdat` chunks are **compressed** and are not used anywhere in the font/subT pipeline
  described in this document (only the pristine multi-language master install uses them —
  see `TODO_MASTER_SUBT_DECOMPRESSION.md`). Font and `subT` resources in the regional
  single-language install used for all work here are `SDAT` (uncompressed).
- `LLIF` (=FILL) chunks pad to 65536-byte boundaries (confirmed byte-exact in both
  `GlobScen.scw` and the audio `.scw` files).
- To locate a resource's usable byte ranges: find its `SHDR` chunk (by `ext`), then walk
  chunks from wherever that `SHDR` chunk ends, collecting `(payload_start, payload_len)`
  segments until the resource's declared `decompLen` is covered. Font files, `subT` text,
  etc. are all injected using this same "segmented write" logic (same-size or
  capacity-checked replacement, zero-padded if shorter).

**Use `lotr_scw_tool.py` directly instead of re-deriving any of this** —
`list_resources()` / `read_resource()` / `write_resource()` implement exactly the above,
tested end-to-end (round-tripped byte-for-byte against known-good extracted files). Why
the font pipeline's earlier ad-hoc scripts still worked despite the offset mistake above:
those scripts most likely found each resource's payload start empirically (by scanning for
recognizable content, e.g. the `FNTS` signature) rather than computing it purely from the
header field layout, which sidesteps the bug — but that also means their exact internal
logic was never fully captured in writing before this rewrite. Any future font work should
switch to `lotr_scw_tool.py`'s `read_resource()`/`write_resource()` rather than resurrect
the old approach.

---

## 2. `.font` (FNTS) file format — fully reverse-engineered

Reverse-engineered via the **source code** of a real, working GUI tool:
`bartlomiejduda/EA-Font-Manager` (GitHub) plus the `reversebox` PyPI package it depends
on for pixel decoding (`pip install reversebox`). This was the breakthrough — trust the
real tool's source over any amount of guessing.

### 2.1 File header (32 bytes, all little-endian)
```
sign            4 bytes  "FNTS"
total_f_size    u32
file_version    u16      (200 in all our files)
num_of_characters u16    (288 in all our files)
font_flags      u32
center_x        u8
center_y        u8
ascent          u8
descent         u8
char_info_offset u32     (=32, i.e. right after this header)
kerning_table_offset u32 (= exact end of the pixel/shape data)
shape_header_offset u32  (= char_info_offset + num_of_characters*12)
```

### 2.2 Character table
Starts at `char_info_offset` (32), one 12-byte `Character12Entry` per character, for
`num_of_characters` entries (288). Struct format `"<HBBHHBBBB"`:
```
code      u16
width     u8
height    u8
x         u16   (position in the pixel atlas)
y         u16
advance   u8
x_offset  u8
y_offset  u8
num_kern  u8
```
**This was originally mis-read for months as `"<HBBHHHH"`** (2×u16 instead of 4×u8 for
the last fields) — that bug explained a huge amount of earlier confusing calibration
noise. Use the 12-byte / 9-field layout above; it is confirmed correct.

The table has **two logical blocks**:
- **Primary block**: indices `0..223`, codes `32..255` sequentially (`index = code-32`).
- **"Duplicate" block**: indices `224..287`, which *mirror* codes `192..255` a second
  time, but with a **fixed, oversized bounding box** (observed height is uniformly
  **93px** for every entry in this block, regardless of file). The real glyph ink inside
  that box is normal-sized (e.g. real height ~22px) sitting with large top/bottom padding
  — confirmed by scanning for non-zero rows inside the box.
- **Building `by_code` (code → entry) must deduplicate**: naive
  `{e["code"]: e for e in entries}` lets the *last*-processed entry win, which means the
  oversized duplicate-block entry silently overrides the primary one for every code in
  192-255. Always build the dict so the **primary** (index < 224) entry wins for direct
  lookups, e.g.:
  ```python
  by_code = {}
  for i, e in enumerate(entries):
      if not (e["code"] in by_code and i >= 224):
          by_code[e["code"]] = e
  ```
- **However — critical finding —** for at least one font file
  (`Unnamed File 000001.font`, the largest/"main" one), the **primary-block** entries for
  several Cyrillic codes are themselves corrupted/wrong (leftover English/Latin glyph
  data, e.g. code 195 "Г" primary slot actually contains an "Ã" shape, code 227 "г"
  primary slot contains a digit "3"). The **duplicate block** reliably held the *correct*
  glyph for these same codes. **When using an existing Cyrillic letter as a donor/source
  for copying or mirroring, prefer the duplicate-block entry, ink-trimmed down to its real
  bounding box** (scan for the tight non-zero rectangle inside the oversized box — see
  §4). Do **not** trust the primary block blindly as a source; always visually verify.

### 2.3 Pixel format — `ALPHA4_17X` (entry_type 122 / 0x7A)
**Confirmed via `reversebox/image/image_decoder.py`, `_decode_generic` for
`bits_per_pixel==4`, `image_endianess="big"`** (matches
`bartlomiejduda/EA-Font-Manager`'s `src/EA_Font/ea_image_decoder.py`, entry_type 122
branch, which calls `decode_image(image_data, width, height, ImageFormats.ALPHA4_17X,
image_endianess="big")` directly — **no swizzling of any kind is applied** for this
entry type; a PS2-swizzle hypothesis was tested and definitively ruled out).

- 4 bits per pixel, alpha-only (RGB always white 0xFF; alpha = nibble × 17).
- **2 pixels packed per byte, big-endian nibble order**: first/left pixel = **high**
  nibble, second/right pixel = **low** nibble.
- Decode: `pixel(i) = (byte>>4)&0xF`, `pixel(i+1) = byte&0xF`, sequential flat scan,
  row-major (`byte_width = true_pixel_width / 2`).
- Verified pixel-perfect against a real export from the EA Font Manager GUI tool.

**Where the pixel data actually starts (this was a real, months-long bug):**
There is a **16-byte "shape/image directory entry" sub-header** at `shape_header_offset`,
*separate from* the character table, which was never accounted for originally:
```
record_id        u8     (122 = ALPHA4_16X/17X for our files)
size_of_the_block u24   (little-endian 3-byte, usually 0 in our files)
width             u16   (declared full atlas width, e.g. 512 or 1024)
height            u16   (declared full atlas height)
center_x          s16
center_y          s16
[2 more packed fields, unused for our purposes]
```
**True pixel data starts at `shape_header_offset + 16`**, and ends at
`kerning_table_offset` (exact, from the file header — no fudge factor). The image byte
size **must** equal `declared_width * declared_height / 2` (4bpp) — assert this.

For **months**, the working scripts used a **hardcoded** `table_end = 32 + 224*12 = 2720`
as the pixel-data start offset — this is **wrong on two counts**: (a) it assumes only 224
entries instead of the true 288, and (b) it doesn't skip the 16-byte shape sub-header. The
effective error was writing new glyph pixels ~784 bytes earlier in the file than where the
game actually reads them — i.e. the glyph existed in the file, was even visible in
self-consistent verification crops (because the verification used the *same* wrong
offset), but the game read a different, still-blank region. **This fully explains the
long-standing "the game draws the character but it's empty" symptom.**

**Correct, current formula (verified working in-game as of variant 20/21):**
```python
pixel_start = shape_header_offset + 16
pixel_end   = kerning_table_offset       # from the 32-byte file header, exact
byte_width  = declared_width // 2
# image_bytes = data[pixel_start:pixel_end]; len(image_bytes) == declared_width*declared_height//2
```

### 2.4 Kerning table
After the pixel data, at `kerning_table_offset`. Entries are
`(char1: u16, char2: u16, delta: i8, padding: 3×0x00)` = 8 bytes each. Not modified by any
of this work; only read to find where the pixel region ends.

---

## 3. cp1251 codepage discovery (removes the "sacrificial letter" problem)

Codes `165, 170, 175, 178, 179, 180, 186, 191` are **not arbitrary "sacrifice" slots** —
they are the **real, standard Windows-1251 codepage positions** for the Ukrainian-specific
letters Ґ/ґ, Є/є, Ї/ї, І/і:
```python
>>> "ҐЄЇІіґєї".encode("cp1251")
```
gives exactly `0xA5(165)=Ґ, 0xAA(170)=Є, 0xAF(175)=Ї, 0xB2(178)=І, 0xB3(179)=і,
0xB4(180)=ґ, 0xBA(186)=є, 0xBF(191)=ї`. This means the `subT` text can be encoded with
**plain, unmodified `str.encode("cp1251")`** — no character substitution table is needed
for these letters; cp1251 already places them at the exact codes we need to patch glyphs
for. (An earlier, since-abandoned approach substituted these letters with visually-similar
Russian letters in the text — that approach is explicitly rejected by the project owner
and must never be reintroduced.)

The base Cyrillic block `192-255` (32 uppercase + 32 lowercase, standard Russian
alphabetical order under cp1251) is the **only** code range confirmed to render correctly
in-game unmodified. Ranges `128-159` (C1 controls) and `176-223`/other DOS/Latin-remnant
ranges were tested and do **not** render new content reliably.

---

## 4. Glyph-editing techniques that work (in order of preference)

All of these were validated by direct pixel inspection (small crops with a few pixels of
margin, viewed at 8-10x zoom) **before** injecting into the game, and then confirmed
in-game via screenshots. All are driven off the *same* header-derived offsets from §2.3 —
never hardcoded constants.

1. **Direct 1:1 copy from a proven glyph, same case-class.** Best when a Ukrainian letter
   is visually identical or near-identical to an existing correct glyph.
   - `Ґ (165) ← Г (195)`, `ґ (180) ← г (227)` — literal copies.
   - `І (178) ← latin 'i' (105)`, `і (179) ← latin 'i' (105)` — per explicit instruction,
     both the uppercase and lowercase Ukrainian "dotted i" use the *same* small glyph as
     Latin lowercase `i` (this matches real Ukrainian typography, where capital І has no
     distinct larger form).
   - **When the donor code is in 192-255, source from the duplicate block (ink-trimmed),
     not blindly from the primary block** — see §2.2's corruption finding.
   - After copying pixels, **recompute** `advance`/`x_offset`/`y_offset` using the
     destination case's own calibration (see §5) — do **not** reuse the donor's raw
     metrics verbatim if the donor came from the duplicate block (its metrics describe
     the oversized box, not the trimmed glyph).

2. **Horizontal mirror of an existing glyph.** Used for `Є (170) ← Э (221)` mirrored
   left-right (Cyrillic Є looks like a mirrored/backwards Э-ish "Ɛ" shape). Same
   ink-trim + recalibrate rule applies when the source is in 192-255.

3. **Scale down an already-fixed glyph for the other case.** `є (186)` was built by
   taking the *already-corrected* `Є (170)` bitmap and resizing it down by
   `x_height/cap_height` ratio (PIL `Image.resize(..., Image.LANCZOS)`), then
   re-quantizing 8-bit alpha back to 4-bit. Useful when you don't have a clean lowercase
   donor but do have a clean uppercase one.

4. **Render fresh from a TTF (Open Sans)** — last resort, still used for `Ї (175)` /
   `ї (191)` as of the latest working version. This is the technique most prone to the
   "letter looks too small" bug (see §5) because of how target height is computed for
   glyphs with diacritics.

**Placement:** new/modified glyphs are placed in genuinely free space *within the
already-declared atlas bounds* (`declared_width × declared_height` from §2.3), below the
lowest real content (`max(e.y+e.h for e in entries if e.w>0)`), in a simple left-to-right,
wrap-to-new-row packing. This means **file size never needs to change** — confirmed: every
rebuilt `.font` file stays byte-identical in size to the original, which sidesteps any
risk around the `.scw` chunk-capacity limits entirely. There is a large amount of genuinely
free space in every checked file (hundreds of unused rows) — no need to ever consider
appending past the declared canvas.

---

## 5. Metric calibration (advance / x_offset / y_offset)

For any new/edited glyph, don't reuse a donor's raw metrics blindly. Instead:
```python
def calibrate(by_code, code_range):
    # code_range = range(65,91) for uppercase reference (Latin A-Z),
    #              range(97,123) for lowercase reference (Latin a-z)
    adv_delta = mode(entry.advance - entry.w for entry in code_range)
    xoff_mode = mode(entry.x_offset for entry in code_range)
    yref      = mode((signed(entry.y_offset) + entry.h) for entry in code_range)
    return adv_delta, xoff_mode, yref

# then, per new glyph of width gw/height gh:
advance   = clamp(gw + adv_delta, 0, 255)
x_offset  = xoff_mode
y_offset  = (yref - gh) % 256   # unsigned-wrap
```
Use the **uppercase** calibration (from Latin `A-Z`, codes 65-90) for uppercase Cyrillic
targets, **lowercase** calibration (from Latin `a-z`, codes 97-122) for lowercase targets.
`cap_h = by_code[65].height`, `x_h = by_code[97].height` are the target render heights
when rendering fresh from a TTF.

### Known open bug: "small letter" sizing issue
When rendering fresh from a TTF (technique #4 in §4) for a character **with a diacritic**
(dot, hook, breve — e.g. Ґ, І, Ї, ґ, і, ї), the *whole* glyph bounding box (letter body +
diacritic) gets scaled to match the target height (`cap_h`/`x_h`), which visually shrinks
the letter body itself to make room for the diacritic above it. Letters *without* a
diacritic (Є, є) don't show this problem. **This is why technique #4 was abandoned in
favor of #1-3 wherever possible** — Ї/ї are the only two letters still using it as of the
last working version, and they still show this "too small" artifact in-game. **Next step
for whoever continues this: give Ї/ї the same copy/mirror/shrink treatment as the other
six letters, sourcing from an existing dotted/breved Latin or Cyrillic glyph instead of
re-rendering from Open Sans.**

---

## 6. Practical pipeline / how to rebuild

1. Load each of the 8 `.font` files fresh from the **pristine** RU install folder
   (`C:\Users\UserM\Documents\lotr\*.font` in the working session — re-derive an
   equivalent pristine copy if these are gone) — never chain edits on top of a
   previous variant's output.
2. Per file: read header (§2.1), build `entries`/`by_code`/`by_code_dup` (§2.2), apply the
   glyph edits (§4) using calibration (§5), write back — same file size, same header
   values except the touched character-table rows.
3. Build `subT` from the Ukrainian translation text (`key = value` per line) using
   **plain `str.encode("cp1251")`**, no substitution table (§3). `subT` binary layout:
   36-byte header (copied verbatim from the source file, not recomputed) +
   `pair_count*2` little-endian u32 offsets (key_offset, value_offset pairs, relative to
   a blob base) + the blob itself (`key\0value\0` repeated, cp1251). This whole step is
   now `lotr_scw_tool.py`'s `build_subt()` / `inject_text_into_subt()` — use those
   instead of re-deriving it; see that file's module docstring and
   `extract_subt_to_text()`/`parse_text_pairs()` for the matching `key = value` text
   format it reads and writes.
4. Inject all 8 fonts + `subT` into a fresh copy of the pristine RU `GlobScen.scw`, using
   the segmented-write logic from §1. `lotr_scw_tool.py`'s `list_resources()` finds every
   resource's `SHDR` position automatically (by scanning for its `ext` field) — no need to
   hunt for offsets empirically per-file the way earlier work in this session had to.
   `write_resource()` handles the same-size-or-capacity-checked overwrite for you.
5. **Always do a visual sanity check before delivering**: crop a handful of known-good
   reference glyphs (Latin A/a, Cyrillic А/а) *and* every newly-touched glyph, with a
   small margin (3-5px) around each, at 8-10x zoom, from the **final saved file** using
   the exact same offset math as the write path. This is standing project policy after an
   earlier catastrophic delivery (screenshot showed giant corrupted bars) reached the user
   without this check.
6. Copy the built `GlobScen_UA.scw` into
   `C:\Program Files (x86)\Return of the King\Data\Game\GlobScen.scw` for the user to
   test in-game.

---

## 7. What still doesn't work / open items

- **Ї / ї** still use the TTF-render technique and show the "too small" sizing artifact
  in-game (§5). Needs the copy/mirror/shrink treatment instead.
- **The 33rd Ukrainian letter problem**: if a future task wants to re-sequence the *entire*
  192-255 block into Ukrainian alphabetical order (as opposed to the current
  minimal-patch approach of only touching 8 codes), there is a **hard capacity mismatch**:
  Ukrainian has 33 letters, the primary block only has 32 slots (192-223 upper /
  224-255 lower). This was flagged but never resolved — candidate solutions discussed but
  not implemented: reuse one of the already-touched 165/170/175/178 style slots for Я/я,
  or accept dropping one letter for a reduced test. **The current shipped approach avoids
  this entirely** by only patching 8 specific codes and leaving the rest of 192-255 as
  standard cp1251 Russian-order Cyrillic (which is also valid Ukrainian for those shared
  letters).
- **The Cyrillic "duplicate block" (indices 224-287, 93px-tall boxes)** — its actual
  in-game purpose was never determined. It is not used by anything in the current
  approach except as a (verified reliable) donor source for a few letters in one specific
  font file. Left completely untouched otherwise.
- No attempt was made to re-encode `subT` for any scheme other than plain cp1251 — if a
  future task changes which codes represent which letters (e.g. the alphabetical
  resequencing idea above), the `subT` text encoding step in §6.3 will need a custom
  per-character mapping instead of `str.encode("cp1251")`.

---

## 8. Key external references used

- `bartlomiejduda/EA-Font-Manager` (GitHub) — the GUI tool whose source code was the
  ground truth for the whole `.font` format. Clone and read
  `src/EA_Font/ea_font_file.py` (header/table parsing) and
  `src/EA_Font/ea_image_decoder.py` (entry_type → decode dispatch, confirms no swizzle
  for type 122).
- `reversebox` (PyPI package) — `pip install reversebox`. Used for
  `reversebox.image.image_decoder.ImageDecoder` (ground-truth ALPHA4_17X pixel decode,
  confirms nibble order) — **do not** use `reversebox.compression.compression_refpack`
  for anything in the font pipeline; it was investigated for the *audio* work and found
  unstable/unreliable (see the separate audio findings doc) but was never actually needed
  for fonts since font pixel data isn't refpack-compressed.
- **Game Extractor** (`GameExtractor.jar`, vendored in this repo) — open-source Java tool;
  its `org.watto.ge.plugin.archive.Plugin_SCW` class is the ground truth for the `.scw`
  container format described in §1 and implemented in `lotr_scw_tool.py`. Decompile it
  with [CFR](https://github.com/leibnitz27/cfr) if you need to re-verify anything:
  `java -jar cfr.jar Plugin_SCW.class --outputdir out/` (extract the `.class` from the jar
  first with `unzip`). Trust a fresh decompile over any notes in this document if they
  disagree.
- `lotr_scw_tool.py` (this repo) — the actual, tested implementation of everything in §1
  and the `subT` build/inject steps in §6. Read its module docstring for the full format
  writeup with exact byte offsets.
