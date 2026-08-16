# TODO: Decompressing the pristine multi-language `subT` (Rdat) table

Status as of this writing: **unsolved**. This file exists so a future session
doesn't have to re-derive the container layer from scratch before getting to
the actual open problem.

## Goal

Extract clean text for all 9 languages (`DEU`, `ENG`, `FRA`, `ITA`, `NLD`,
`POL`, `POR`, `SPA`, `SWE`) from the `subT` resource inside the **pristine
English/international master install**:

```
C:\Program Files (x86)\EA GAMES\LOTR - The Return of the King ENG\Data\Game\GlobScen.scw
```

This is a different, harder problem than the one `lotr_scw_tool.py` already
solves. That tool works great on the **regional single-language repack**
(`C:\Program Files (x86)\Return of the King\Data\Game\GlobScen.scw`, Russian
retail install) because its `subT` resource is stored uncompressed (`SDAT`
chunks). The pristine ENG install's `subT` resource uses **compressed**
(`Rdat`) chunks instead, and that compression has not been cracked.

## What's already solved (don't redo this)

- The `.scw` container format itself: chunk tags, byte offsets, SDAT vs Rdat
  distinction, padding chunks. All implemented and validated in
  `lotr_scw_tool.py` in this repo -- decompiled from the real, open-source
  **Game Extractor** tool (`org.watto.ge.plugin.archive.Plugin_SCW`), not
  guessed. If you need to re-verify anything about the container layer,
  decompile that class again (see "Tools" below) rather than trust hand
  calculations from an exploratory session -- see the "gotcha" below for why.
- `list_resources()` on the pristine ENG install's `GlobScen.scw` correctly
  enumerates all 36 resources in the regional repack; it should work
  unchanged on the ENG install too for *listing* (it only reads headers, not
  compressed payload) -- confirm this still holds before doing anything else.
- The `subT` resource in the ENG install was located via `list_resources()`-style
  scanning: search for a `SHDR` chunk whose `ext` field is `subT`. In the copy
  examined this session it was `fileID=5`, `decompLen=195068`, and its first
  payload chunk's `fileHeader` was `Rdat`, not `SDAT`.

## Important gotcha: re-verify byte offsets before trusting old numbers

During this session, `lotr_scw_tool.py`'s container-walking code had an
off-by-8 bug (the internal `fileHeader` field was read from the wrong offset:
`chunk_start + 8` instead of the correct `chunk_start + 16`, discovered only
by decompiling `Plugin_SCW.class` and comparing against a hex dump). That bug
is now **fixed** in the committed version of `lotr_scw_tool.py`.

However, some exploratory numbers below (the exact `Rdat` chunk's compressed
length, its `chunkDecompLength` field, the first bytes of compressed data)
were computed with **one-off scratch scripts during the same exploration
session**, some of which pre-date the fix. They are recorded here as leads,
not as verified ground truth. **Step 1 of any future session on this problem
should be: re-read those specific fields using the current, fixed
`lotr_scw_tool.py` constants (`_FILE_HEADER_OFFSET=16`, `_RDAT_PAYLOAD_PREFIX=68`,
etc.), and confirm the numbers below still hold before building anything on
top of them.**

## What was found about the Rdat chunk (needs re-verification, see above)

For the `subT` resource's first `Rdat` chunk:

- Chunk's declared total length: 8188 bytes (includes the 8-byte SHOC header)
- After subtracting the fixed 56-byte prefix (8 reserved + 4 file-header tag
  + 44 reserved) and the chunk's own `chunkDecompLength` field (4 bytes):
  **stored (compressed) payload = 8120 bytes**
- **`chunkDecompLength` field for this chunk = 8651 bytes**
- Compression ratio implied: 8120 / 8651 ≈ 93.9% -- i.e. only **~6% size
  reduction**. This is unusually weak for general-purpose text compression
  (plain English/German/etc. UI strings normally compress 40-60%+ with any
  competent LZ-family scheme). Two competing explanations:
  1. The measured lengths are wrong because of the offset bug above --
     re-verify first.
  2. If the numbers hold up, this might not be "space-saving" compression in
     the usual sense at all -- could be a fixed-width encoding, a weak/simple
     obfuscation scheme, or genuine LZ compression on data that just happens
     to compress poorly (unlikely for prose text, but not impossible if the
     table is dominated by lots of short/unique strings with little
     cross-string redundancy within a single chunk's window).
- **First bytes of the compressed payload: `88 0f 09 00 00 00 00 03 00 00
  b8 7f 00 00 45 4e ...`** -- the leading `0x88` byte matches the exact
  "impossible" RefPack backreference byte that blocked the *audio* format
  investigation for this same game (see `AUDIO_INVESTIGATION_EN.md` in this
  repo, section on RefPack attempts). This is either a strong hint that both
  formats share the same compression scheme, or a coincidence worth treating
  with suspicion until proven otherwise.

## What was tried and did NOT work

- **Naive "read until next `\x00`" parsing**, treating the resource as if it
  were the same simple key/value-blob format as the SDAT-based single
  -language repack. Produces garbage/truncated values for anything beyond
  single short words (multi-word phrases came out chopped up with binary
  junk mid-string). This on its own doesn't prove compression -- it's also
  consistent with an embedded formatting/markup byte scheme (like the
  `\u0007`-style hotkey-highlight markers already solved for the *StarCraft*
  localization work elsewhere in this project) -- but combined with the
  `Rdat` tag and the bogus-huge-integer test below, compression is the far
  more likely explanation.
- **Interpreting the first bytes of the resource as a raw offset table**
  (assuming, wrongly, that Rdat chunks are transparently readable the same
  way SDAT ones are). Produced nonsense multi-million values, far larger
  than the file itself -- confirms the bytes are not literal offsets/text,
  consistent with them being compressed.
- **Manually mapping the internal key order** by walking one clean-looking
  per-language block and matching known key names against known-good keys
  from the simplified repack's key list. This DID work well enough to prove
  the internal key order is **not alphabetical** (unlike the simplified
  single-language repack) and that `abilitiesUnlocked` is the first key in
  every language's block -- useful context, but doesn't get you decoded text
  since the block's *content* is still compressed.
- **Checking Game Extractor's own decompiled source for how it handles
  `Rdat`**: `Plugin_SCW.read()` wraps `Rdat` chunks in a `BlockExporterWrapper`
  using `Exporter_Default.getInstance()` -- **the exact same exporter class
  used for uncompressed `SDAT` chunks**. This strongly suggests Game
  Extractor's SCW plugin does **not** actually decompress `Rdat` chunks
  either -- it likely just dumps the raw (still-compressed) bytes when you
  extract such a resource through the GUI. If true, Game Extractor itself
  doesn't solve this problem, and extracting the `subT` resource with it
  directly would need to be verified/wouldn't help by itself.
- Everything already tried and abandoned for the *audio* format's RefPack
  puzzle (documented in `AUDIO_INVESTIGATION_EN.md`) is relevant background
  but was not re-attempted here specifically against this compressed text
  chunk: `reversebox`'s `RefpackHandler` DLL (unstable/garbage output), a
  from-scratch RefPack decoder tested at 200+ candidate offsets (zero
  success), zlib/DEFLATE (ruled out).

## Hypotheses / next steps, roughly in priority order

1. **Re-verify the Rdat field measurements with the fixed tool first.**
   Before anything else, re-read `chunkDecompLength`, the stored payload
   length, and the first N compressed bytes using the corrected offset
   constants in the committed `lotr_scw_tool.py`. If the ~6% compression
   ratio doesn't hold up under correct offsets, everything above needs
   re-deriving.

2. **Look for an EA-compression-specific exporter class inside
   `GameExtractor.jar`, separate from `Plugin_SCW`.** Since `Plugin_SCW`
   itself doesn't appear to decompress `Rdat`, search the jar for exporter
   classes whose names suggest EA's compression scheme specifically --
   things like `Exporter_*RefPack*`, `Exporter_*QFS*`, `Exporter_*LZ*`, or
   any class referenced by *other* EA-game plugins in the same tool that
   might share the format (EA reused RefPack/QFS compression across many
   titles from the SimCity/Need For Speed era onward). If one exists,
   decompile it the same way `Plugin_SCW` was decompiled (see "Tools" below)
   and port its actual decompression logic to Python.

3. **Search specifically for standalone EA RefPack/QFS decompressors**,
   independent of Game Extractor and independent of the `reversebox` PyPI
   package already tried (and already found unreliable for this game's
   audio). RefPack (also called QFS) was used across many EA titles
   (SimCity 4, various racing games, etc.) and has multiple independent
   open-source re-implementations in C/C++ floating around game-modding
   communities -- a different, more battle-tested implementation than
   whatever `reversebox` wraps might behave differently against this
   specific byte stream, especially around the `0x88` "impossible
   backreference" byte that blocked the from-scratch attempt.

4. **Check for a dedicated *Return of the King* modding community/tool.**
   This is a real, released PC game with an active-enough fanbase that a
   dedicated tool or documented format writeup may already exist outside of
   Game Extractor's generic SCW support -- worth a targeted search before
   assuming this needs solving from first principles again.

5. **Question whether it's RefPack at all.** The unusually weak ~6%
   compression ratio (if it survives step 1's re-verification) is not
   typical of LZ-family text compression. Consider testing against other EA
   proprietary schemes (there were several across different EA engines and
   eras, not just RefPack), or consider that this might be some kind of
   fixed encoding/obfuscation rather than general-purpose compression --
   e.g. try a fixed-width bit-packing or simple XOR/substitution hypothesis
   against a short, structurally-simple chunk before assuming a full LZ
   decompressor is required.

6. **If a working decompressor is found**, it plugs into `lotr_scw_tool.py`
   fairly cleanly: extend `_read_segments()` to call it instead of raising
   `UnsupportedCompressionError` for `Rdat` chunks, verify `chunkDecompLength`
   bytes come out, then the existing `parse_subt()` logic (36-byte header +
   offset table + blob) should still apply -- **though this needs
   confirming**: the multi-language table's internal layout (given the
   confirmed non-alphabetical key order, and per-language blocks that don't
   look like simple 36-byte-header tables in the raw bytes seen so far) may
   turn out to be a different structure on top of the decompressed bytes,
   not the same header+offset-table+blob format used by the simplified
   single-language repack. Re-derive the decompressed structure fresh once
   you can actually see real decompressed bytes, rather than assuming it
   matches the simpler format.

## Tools

- **Game Extractor** (already installed): `C:\Users\UserM\Desktop\extract\GameExtractor.jar`
  -- open-source, `org.watto.ge.plugin.*` package. Decompile any `.class`
  file from it with CFR:
  ```
  curl -sL -o cfr.jar https://github.com/leibnitz27/cfr/releases/download/0.152/cfr-0.152.jar
  unzip -o GameExtractor.jar "org/watto/ge/plugin/archive/Plugin_SCW.class" -d extracted/
  java -jar cfr.jar extracted/org/watto/ge/plugin/archive/Plugin_SCW.class --outputdir decompiled/
  ```
  This is exactly how the container format (and the fact that `Plugin_SCW`
  doesn't decompress `Rdat`) was confirmed this session. **Trust a fresh
  decompile over any notes in this file if they disagree.**
- `lotr_scw_tool.py` (this repo) -- the working container reader/writer for
  the *already-solved* SDAT case. Its `list_resources()` / `_read_segments()`
  internals are the right starting point to extend for `Rdat` support.
- Reference files used this session:
  - Pristine ENG (compressed) install: `C:\Program Files (x86)\EA GAMES\LOTR - The Return of the King ENG\Data\Game\GlobScen.scw`
  - Regional RU (uncompressed, already solved) install: `C:\Program Files (x86)\Return of the King\Data\Game\GlobScen.scw`
  - `AUDIO_INVESTIGATION_EN.md` in this repo -- the parallel, also-unsolved
    RefPack investigation for this game's audio format. Read it before
    re-attempting RefPack from scratch; several dead ends are already
    documented there in detail.
