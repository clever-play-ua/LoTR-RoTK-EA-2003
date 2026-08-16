# LOTR: The Return of the King (2003, EA) — Audio/Dialogue Format Investigation

Status: **UNSOLVED**. This is a detailed record of a deep reverse-engineering attempt at
extracting/decoding the in-game dialogue audio, so a future session (or another person)
doesn't have to re-derive everything from scratch. Substantial, *verified* progress was
made on the container/metadata layer; the final audio *codec/compression* layer remains
uncracked. Publicly, nobody appears to have solved this either (see the pre-existing
`LOTR ROTK audio format notes.md` in this project, sourced from a 2019-2020 XeNTax forum
thread that also gave up on the external/dialogue audio specifically).

Test file used throughout: `cra01.scw` at
`C:\Program Files (x86)\EA GAMES\LOTR - The Return of the King ENG\Data\Game\cra\cra01.scw`
(48,955,392 bytes). This is a per-level archive (level "cra" = likely Cracks of Doom /
Mount Doom sequence). Other level archives exist alongside it
(`bla01.scw`, `cir00.scw`, `hel01.scw`, `min00.scw`, etc.) with the same structure — any
of them should work equally well for continued testing.

---

## 1. What's SOLID — container/metadata layer (fully reverse-engineered)

### 1.1 Outer container = same family as `GlobScen.scw`
`cra01.scw` starts with the same `COTS`/`COHS`/`RDHS`/`LLIF` chunk tags already fully
understood from the font work (see `FONT_LOCALIZATION_EN.md` §1). Game Extractor 3.16
(installed at `C:\Program Files (x86)\Game Extractor\`) parses this top level directly
and lists named sub-archives with type "SWVR Archive":
```
initial_load.swvr        offset 65536     decompressed 7274496
zone_cra01_zone1.swvr    offset 7340032   decompressed 1441792
zone_cra01_zone2.swvr    offset 8781824   decompressed 1310720
zone_cra01_zone3.swvr    offset 10092544  decompressed 458752
zone_cra01_zone4.swvr    offset 10551296  decompressed 1179648
zone_cra01_zone5.swvr    offset 11730944  decompressed 1638400
igc_crak_igc_bank.swvr   offset 13369344  decompressed 393216
```
(`igc` = "in-game cinematic" — this is the bank most likely to hold actual dialogue.
`crak` matches the level, likely "Cracks of Doom".)

### 1.2 Inner `SWVR` sub-archive format — decompiled from a REAL WORKING TOOL

**Game Extractor itself has a proper plugin for this exact game and format.** This is the
single most valuable finding of the whole investigation — instead of guessing, decompile
the tool that the user already confirmed can play *some* sound from this game.

Location inside `GameExtractor.jar`:
```
org/watto/ge/plugin/archive/Plugin_SWVR_RVWS.class
org/watto/ge/plugin/archive/Plugin_SCW_COTS.class
org/watto/ge/plugin/archive/Plugin_SCW.class
org/watto/ge/plugin/viewer/Viewer_FFMPEG_Audio_EA_SCHl.class   <-- confirms codec family
```
The last one's name (`Viewer_FFMPEG_Audio_EA_SCHl`) is direct confirmation that the real
audio codec is from the **EA "SCHl" family** (a well-known, historically-documented EA
multimedia format — see §2).

**How to decompile** (no C compiler available on the test machine, but Java bytecode
decompiles cleanly): download a standalone decompiler jar (e.g. CFR,
`https://github.com/leibnitz27/cfr/releases`), then:
```
"C:\Program Files (x86)\Game Extractor\jre\bin\java.exe" -jar cfr.jar \
    "C:\Program Files (x86)\Game Extractor\GameExtractor.jar" --outputdir out
```
(or extract just the specific `.class` files with `unzip` first for speed, then decompile
those individually).

**Game Extractor also has a real, working CLI batch-extract mode** — run it from *inside*
its own install directory (needed so it finds its bundled `settings/`, `plugins.zip` etc.):
```
cd "C:\Program Files (x86)\Game Extractor"
./jre/bin/java.exe -jar GameExtractor.jar -extract -input <file> -output <dir>
```
This is recursive-capable: run it once on `cra01.scw` to get the `.swvr` sub-archives,
then run it *again* pointing `-input` at one of those `.swvr` files to get the next
level down (`.bnk` bank files + a small `.Cact` file), confirming the tool's own plugin
chain matches the manually-derived structure below.

### 1.3 Exact chunk-walking algorithm (from the decompiled `Plugin_SWVR_RVWS.read()`)

Tags are reversed on disk exactly like the font `.scw` format (`SWVR`↔`RVWS`,
`SHOC`↔`COHS`, `SHDR`↔`RDHS`, `FILL`↔`LLIF`, `CTRL`↔`LRTC`, `SDAT`↔`TADS`,
`Rdat`↔`tadR` — note `Rdat`/`tadR` is **mixed-case**, distinct from `SDAT`).

```python
while pos < arc_size:
    tag = data[pos:pos+4][::-1].decode("latin1")   # read reversed 4-byte tag
    if tag == "FILL":
        pos += 4
        pos += pad_to_boundary(pos, 65536)          # no length field for FILL here
        continue
    pos += 4
    length = read_i32_le(data, pos) - 8
    pos += 4
    if length == -8:
        break                                        # end of archive marker
    chunk_body_start = pos

    if tag == "SWVR":
        # skip 8, then reversed 4-byte sub-tag
        sub = data[pos+8:pos+12][::-1].decode("latin1")
        if sub == "FILE":
            filename = data[pos+12 : pos+12+(length-12)].split(b"\0")[0].decode("latin1")
        pos = chunk_body_start + length
        continue

    if tag == "CTRL":
        pos = chunk_body_start + length
        continue

    if tag in ("SHOC", "SONO"):          # BOTH tags share this handling
        p2 = pos + 8
        sub = data[p2:p2+4][::-1].decode("latin1")
        p2 += 4
        if sub == "SHDR":
            # === starts a NEW logical audio/data stream ===
            if currently_reading_a_stream:
                flush_previous_stream()             # finalize accumulated blocks
            p2 += 4
            extension = data[p2:p2+4][::-1].split(b"\0")[0].decode("latin1")  # e.g. "samp", "bnk", "efxt"
            p2 += 4
            p2 += 4                                  # skip 4 more (unknown)
            decomp_length = read_i32_le(data, p2)     # DECLARED total decompressed size for the whole stream
            block_offsets, block_lengths, block_decomp_lengths = [], [], []
            currently_reading_a_stream = True
            pos = chunk_body_start + length
            continue
        elif sub == "SDAT":
            # === an UNCOMPRESSED data block ===
            body = p2 + 44
            blen = length - 56
            block_offsets.append(body); block_lengths.append(blen)
            block_decomp_lengths.append(blen)         # same as blen: no compression
            pos = chunk_body_start + length
            continue
        elif sub == "Rdat":
            # === a block with an EXTRA per-block declared size (presumed compressed) ===
            body_hdr = p2 + 44
            chunk_decomp_length = read_i32_le(data, body_hdr)  # per-BLOCK declared size
            body = body_hdr + 4
            blen = (length - 56) - 4
            block_offsets.append(body); block_lengths.append(blen)
            block_decomp_lengths.append(chunk_decomp_length)
            pos = chunk_body_start + length
            continue
    pos = chunk_body_start + length
```
Then on flush: if `extension == "samp"`, Game Extractor's own plugin treats the
concatenated block bytes as **raw PCM**, hardcoding:
```java
resource.setFrequency(22050);
resource.setBitrate((short) 16);
resource.setChannels((short) 1);
```
**This confirms the FINAL target audio format is 22050 Hz, 16-bit, mono** — this part is
not in doubt.

**Important structural fact confirmed by direct inspection**: the 44-byte region skipped
before each block's own fields is **byte-for-byte identical boilerplate across every
block tested** (`0000000080fc12000850400018b04a0004000000b0fd1200206b6e620900000074fe1200a1334000b4fe1200`)
— it is a fixed per-file template, not per-block metadata. Nothing useful was found
hidden inside it.

### 1.4 What "extension" values mean, and the recursion needed

Walking `cra01.scw` → `.swvr` sub-archives only gets you `.swvr` **files themselves**
(named `initial_load`, `zone_craXX_zoneN`, `igc_crak_igc_bank`). Each `.swvr` file is
itself ANOTHER instance of the exact same `SWVR`/`SHOC`/`SONO` chunk format (self-similar,
recursive) — walking `igc_crak_igc_bank.swvr` with the same algorithm yields **9 further
streams**, most with `extension == "bnk"` (one is `.Cact`). **None of the streams found
this way have `extension == "samp"` directly** — meaning `.bnk` itself is presumably yet
another nested container that should recurse ONE more level to reach actual `.samp`
entries, but **no dedicated Game Extractor plugin exists for this specific `.bnk`
sub-format** (checked all `Plugin_BNK*.class` variants in the jar — every one of them is
tied to a *different*, unrelated game: `Plugin_BNK_BKHD`=Wwise-family titles,
`Plugin_BNK_KNAB`="Test Drive Unlimited", etc. — none of them declare LOTR/EA
Redwood/Return of the King). **This ".bnk further-recursion" possibility was flagged but
never fully investigated — see §6, this is a promising untried lead.**

`initial_load.swvr` and the `zone_craXX_zoneN.swvr` files were also inspected directly:
their `Rdat`-heavy content decodes (once you strip the chunk framing) to **readable ASCII
text** — sound-event *scripts*, not raw audio. Examples of literal decoded strings found:
`PLAY, 0, 0, 255, 0`, `STARTING TO FALL`, `brick10` (a footstep-surface-material name).
These are SFX/cue *trigger definitions* (volume, pan, material type), not the dialogue
audio itself. **Do not waste time treating `initial_load` or `zone_*` content as audio —
they are metadata/scripts.**

---

## 2. Codec identification: EA MicroTalk (UTK)

Given the `Viewer_FFMPEG_Audio_EA_SCHl` plugin name, the target format family is **EA
SCHl** — a well-documented (if obscure), decades-old EA multimedia container used across
many EA titles ~1997-2010, created by EA's internal "sx.exe"/"Sound eXchange" tool. It is
supported by the open-source **vgmstream** project (`github.com/vgmstream/vgmstream`),
whose source was used as ground truth here (much like EA-Font-Manager was for fonts).

`vgmstream.exe` (pre-compiled, r1917-39-g46eb81ac, May 2024 build) is **already bundled
with Game Extractor** at
`C:\Program Files (x86)\Game Extractor\external_bins\vgmstream\vgmstream.exe` — a real,
working reference decoder for dozens of EA codec variants, if the container/codec
selection can be gotten right.

### 2.1 `ea_schl.c` patch-tag header format (verified via raw source, not summarized)
Source: `github.com/vgmstream/vgmstream/blob/master/src/meta/ea_schl.c` (fetch the RAW
file with `curl`, not via a summarizing web-fetch tool — the summarizer drops exact
byte/table values needed for byte-perfect reconstruction).

- Block tags: `"SCHl"` (0x5343486C) = header block, `"SCDl"` (0x5343446C) = data block,
  `"SCEl"` = end block. **Not reversed** in the standalone SCHl format (this differs from
  our game's own SWVR container, which does reverse tags — the SCHl format is a
  *different*, EA-standard sub-format used inside the audio payload, if the codec turns
  out to be plain EA-SCHl-wrapped after all).
- Header: `"SCHl"` + 4-byte size (endianness auto-detected via a heuristic,
  `guess_endian32`) + a `"PT\0\0"` (or `"GSTR"`) platform marker + 2-byte LE platform ID +
  a sequence of **patch tags**: `tag(1 byte) + byte_count(1 byte) + big-endian value
  (byte_count bytes)`. Key tags: `0x80`=version, `0x82`=channels, `0x83`=codec1,
  `0x84`=sample_rate, `0x85`=num_samples, `0x86`/`0x87`=loop points, `0xA0`=codec2,
  `0xFF`=header-end marker (stop parsing tags).
- Codec constants that matter here:
  `EA_CODEC1_MT10 = 0x09`, `EA_CODEC2_MT10 = 0x04` ("MicroTalk (10:1 compression)").
- `"SCDl"` data block: payload effectively starts at
  `block_offset + 0x0c + channels*4 + <a u32 LE offset field read at +0x0c>`.

### 2.2 MicroTalk (UTK) decoder — fully ported to Python, verified against the source

MicroTalk (aka UTK/UMT) is EA's proprietary CELP/RELP **speech** codec. Ground-truth
source (public domain, Andrew D'Addesio's `utkencode`, adapted into vgmstream):
```
https://raw.githubusercontent.com/vgmstream/vgmstream/master/src/coding/ea_mt_decoder.c
https://raw.githubusercontent.com/vgmstream/vgmstream/master/src/coding/libs/utkdec.c
https://raw.githubusercontent.com/vgmstream/vgmstream/master/src/coding/libs/utkdec.h
```
`utkdec.c` (617 lines) was fetched **raw via `curl`** (not through a summarizing fetch —
that drops the lookup tables) and ported **line-for-line** to Python
(`utk_decoder.py` in the scratch working folder — not preserved long-term, but the
algorithm is fully documented here well enough to re-port in under an hour):

- Bit reader: **LSB-first**, 8-bit-at-a-time refill into a wider accumulator (matches C's
  `uint32_t bits_value`). Verified **by hand** bit-by-bit against real file bytes — this
  part is 100% confirmed correct (see §4 for the trace).
- `parse_header`: 1 bit `reduced_bandwidth` + 4 bits `base_thre` + 4 bits `base_gain` +
  6 bits `base_mult` (15 bits total), then derives `multipulse_threshold = 32-base_thre`
  and a table of 64 `fixed_gains` via `fixed_gains[0]=8*(1+base_gain)`,
  `fixed_gains[i] = fixed_gains[i-1] * (1.04 + base_mult*0.001)`. **Verified by hand** —
  confirmed correct against real bytes.
- Per frame (432 samples/frame): reads 12 reflection-coefficient (RC) table indices
  (a 64-entry table, `utk_rc_table`, values roughly -0.997 to +0.997), interpolates them
  over 4 sub-frames, converts RC→LPC coefficients via a Levinson-Durbin-style recursion
  (`rc_to_lpc`), decodes an "excitation" signal per sub-frame (either RELP — signal coded
  explicitly — or multi-pulse — sparse pulses via a Huffman-style codebook lookup,
  `utk_codebooks`/`utk_commands`), then runs it through a 12-tap LPC synthesis (IIR)
  filter (`lp_synthesis_filter`) to get final samples.
- `rc_to_lpc` was **independently sanity-tested** in isolation (all-zero input → all-zero
  output; small varied inputs → small bounded outputs) and behaves correctly for
  well-conditioned inputs.

**This decoder is believed correct** (see next section for why real input still produces
garbage — it's very likely an upstream data problem, not a decoder bug).

---

## 3. What does NOT work — every approach tried and ruled out

### 3.1 `reversebox`'s `RefpackHandler` (Python/DLL wrapper) — unstable, unreliable
`pip install reversebox` bundles a compiled `refpack.dll` used successfully for the
*font* pixel data (unrelated to audio — see the font doc). Tried here on audio blocks by
synthesizing a fake standalone-refpack header (`b"\x10\xFB" + 3-byte-BE-size + raw_block_bytes`)
and calling `RefpackHandler().decompress_data(fake)`.
- **First call in a fresh process**: appears to succeed, returns exactly the requested
  byte count.
- **On closer inspection, the returned content is >90% literal zero bytes** (one single
  contiguous run of tens of thousands of zero bytes) — this is NOT plausible for genuine
  compressed speech data. **The DLL is producing garbage while still reporting "success"
  and the exact requested length** — it apparently just pads/repeats degenerate output
  once it runs out of genuinely-decodable tokens, rather than erroring.
- **Repeated calls within the same process become increasingly unstable**: subsequent
  calls to the same DLL function start throwing native
  `OSError: exception: access violation reading 0x...` — a real memory-corruption bug in
  the DLL itself (confirmed by isolating each call into its own fresh subprocess, which
  fixes the *crash* but not the garbage-content problem).
- **Verdict: do not trust this DLL for anything beyond very small/simple inputs. Its
  reported byte-length matching your request proves nothing about content correctness.**

### 3.2 A from-scratch, spec-verified pure-Python RefPack (QFS) decoder — 200+ offsets tried, zero success
Given the DLL's unreliability, a **complete, independent RefPack/QFS decompressor** was
written in Python, ported command-by-command from the actively-maintained Rust reference
implementation `actioninja/refpack-rs`
(`src/data/control/mod.rs` + `src/data/decompression.rs`, fetched raw via `curl`). The
command byte-layout (verified against this source, not guessed):
```
0x00-0x7F: "short" copy  (2 bytes total)
0x80-0xBF: "medium" copy (3 bytes total)
0xC0-0xDF: "long" copy   (4 bytes total)
0xE0-0xFB: literal run   (1 byte + N literal bytes, N=((first&0x1F)<<2)+4)
0xFC-0xFF: STOP code     (1 byte + 0-3 trailing literal bytes, then decompression ends)
```
Each copy command carries an offset+length back-reference into the *already-decompressed
output* (classic LZ77-style RLE, allowing overlapping self-referential copies) plus 0-3
literal bytes to emit first.

**Result: every single tested Rdat block, from every stream, in every file position
(including the very first Rdat block in the entire file), begins with the exact same
byte `0x88`.** `0x88` falls in the "medium copy" range (0x80-0xBF) and decodes to a
backreference into an **empty output buffer** (offset > 0 bytes written so far) — which
is **structurally impossible** for a valid, freshly-starting RefPack stream (a real
stream must begin with either a literal-run or stop command, since there is nothing yet
to reference).
- Brute-forced 200 different starting-byte skip offsets (0 through 199) inside a single
  block — none produced more than ~5 valid-looking commands before hitting the same
  "backreference into nothing" failure.
- Tested the **"continuous shared history across all blocks in a stream"** theory
  (i.e. don't reset the output buffer between blocks — concatenate the raw *compressed*
  bytes of all 3 blocks of a multi-block stream first, decode once) — **still fails
  identically at command 1**.
- Tested the **"continuous shared history across the whole file"** theory (decode from
  the very first Rdat block in the entire `.swvr` file, in raw file order) — **still
  fails identically** — the first-ever Rdat block in the whole file also starts with
  `0x88` and an impossible backreference.
- **Conclusion: this is very unlikely to be standard RefPack/QFS at all** (or at minimum,
  not starting where the current parsing places it — see §6 for the biggest remaining
  unknown).

### 3.3 zlib/DEFLATE — no match
Tried `zlib.decompressobj()` with `wbits` = 15 (zlib header), -15 (raw deflate), 31
(gzip), 47 (auto) at skip offsets 0-19. No combination produced any output. Ruled out.

### 3.4 Feeding raw (undecompressed) block bytes directly into the MicroTalk decoder
On the theory that "Rdat" might just mean "raw data" (not "refpack data") and there's no
compression layer at all — fed the raw block bytes straight into the Python MicroTalk
port.
- The 15-bit header decodes to *plausible* values
  (`reduced_bandwidth=False`, `multipulse_threshold=20`, `fixed_gains[0]=64.0`,
  `fixed_gains[1]=67.136` — all hand-verified correct against the real header-parsing
  algorithm).
- But the very next data — the 12 reflection-coefficient table indices for frame 0 —
  come out heavily degenerate: `[0, 62, 22, 0, 16, 16, 19, 16, 16, 16, 16, 16]`
  (7 of the last 8 values identical, meaning 6-7 out of 8 raw 5-bit reads returned
  exactly 0 — statistically almost impossible for real varied data).
- Traced this down to actual **real zero bytes in the source file** at byte offset 4-5 of
  the block (confirmed via hex dump: `88 0b c0 b7 00 00 06 00 00 00 ...`), i.e. genuinely
  present in the file, not a bug in the bit-reader.
- Resulting decoded audio, when run through the full pipeline: amplitude blows up
  immediately (frame 0 already reaches sample magnitudes >100,000, i.e. >3x a 16-bit
  range) — classic **unstable LPC synthesis filter** behavior, which mathematically
  should be *impossible* if the reflection coefficients are correctly decoded (Levinson-
  Durbin recursion from |RC|<1 inputs is provably stable) — strong evidence that the
  *input bits themselves* are wrong at this point in the stream, not the filter math.
- **Verdict: raw block bytes are also NOT directly a valid MicroTalk bitstream** — some
  transformation is still missing between "raw Rdat block bytes" and "clean MicroTalk
  bitstream". The real zero-byte run this early rules out "it's just quiet audio."

### 3.5 Constructing a real EA-SCHl-wrapped file and handing it to vgmstream.exe
Built a byte-accurate `SCHl` + `SCDl` + `SCEl` wrapper from scratch (per §2.1), embedding
a raw block's bytes as the payload, explicitly setting both `codec1=0x09` (MT10) and
`codec2=0x04` (MT10) via the correct patch-tag encoding.
- `vgmstream.exe -m <file>` **does recognize the container** as a valid-enough EA SCHl
  file to attempt playback (progress! — earlier malformed attempts were rejected
  outright) — but then **tries to decode it via an MP3 decoder** instead of MicroTalk,
  failing with `Failed to read frame size: Could not seek to <N>`.
- Confirmed via GitHub commit history that `ea_mt_decoder.c` has existed in vgmstream
  since **2017**, well before this bundled May-2024 build, so "missing codec in this
  build" was ruled out as the explanation.
- **Root cause not found**: either the hand-built `SCHl` header has a subtle field-order
  or byte-count bug causing the codec2 tag to be misread as something in the MP3/Layer3
  range, or there's a header field/precedence rule not yet understood. **This is the
  closest miss of everything tried — worth revisiting first** (see §6).

---

## 4. Verified-correct building blocks (safe to reuse without re-deriving)

- The entire SWVR/SHOC/SONO/SHDR/SDAT/Rdat chunk-walking algorithm in §1.3 — this is
  ground truth from decompiled, shipped, working code, not a guess.
- Target output format: 22050 Hz, 16-bit signed PCM, mono.
- The MicroTalk bit-reader and header-parsing (`parse_header`) — hand-verified bit by bit
  against real file bytes (see the trace below for methodology, worth repeating on any
  new candidate input).
- `EA_CODEC2_MT10 = 0x04`, `EA_CODEC1_MT10 = 0x09` (from vgmstream's `ea_schl.c`).
- The exact patch-tag byte format for constructing EA-SCHl headers (`tag, byte_count,
  BE-value`), and the tag numbers for channels(0x82)/sample_rate(0x84)/
  codec1(0x83)/codec2(0xA0)/num_samples(0x85)/end(0xFF).
- The exact RefPack/QFS command byte-layout (§3.2) — independently re-derivable from
  `actioninja/refpack-rs` any time it's needed for a *different* part of this game or a
  different EA title, even though it didn't pan out for this specific audio blob.

### Methodology for hand-verifying the bit reader (reusable technique)
Take the first few raw bytes of a candidate stream, and manually trace `read_bits` calls
bit by bit against the known `parse_header` field layout, checking that the derived
values (`base_thre`, `base_gain`, `multipulse_threshold`, `fixed_gains[0]`,
`fixed_gains[1]`, etc.) match what the code *should* produce arithmetically. This was
done successfully for our test data and the header fields check out perfectly — so if a
future attempt still gets garbage after the header, the bug is almost certainly **after**
byte ~3 of whatever buffer is being fed in, not in the bit-reading primitives themselves.

---

## 5. Files/tools fetched or built during this investigation (re-fetch as needed — not preserved in the repo)

All of these were downloaded fresh via `curl`/`WebFetch` during the session; none are
guaranteed to still be sitting on disk, but the exact URLs are given so they can be
re-fetched in under a minute each:
- `https://raw.githubusercontent.com/vgmstream/vgmstream/master/src/meta/ea_schl.c`
- `https://raw.githubusercontent.com/vgmstream/vgmstream/master/src/coding/ea_mt_decoder.c`
- `https://raw.githubusercontent.com/vgmstream/vgmstream/master/src/coding/libs/utkdec.c`
- `https://raw.githubusercontent.com/vgmstream/vgmstream/master/src/coding/libs/utkdec.h`
- `https://raw.githubusercontent.com/actioninja/refpack-rs/main/src/data/control/mod.rs`
- `https://raw.githubusercontent.com/actioninja/refpack-rs/main/src/data/decompression.rs`
- CFR decompiler: `https://github.com/leibnitz27/cfr/releases/download/0.152/cfr-0.152.jar`
  (used to decompile Game Extractor's own `.class` plugin files — genuinely essential,
  do this again first thing in any follow-up session, it's what unlocked the exact
  container algorithm in §1.3)

**IMPORTANT: always fetch raw source files via `curl -o file.c <raw-github-url>` and read
them directly, never via a "summarize this URL" style web-fetch tool** — for anything
containing lookup tables or exact byte layouts, a summarizer silently drops or
approximates the numbers, which is fatal for this kind of byte-exact reverse engineering.
This mistake was made once early on and cost real time.

---

## 6. Recommended next steps, in priority order

1. **Finish debugging the hand-built EA-SCHl wrapper (§3.5)** — this got the closest to a
   working result (vgmstream recognized the container). Compare the hand-built header
   byte-for-byte against a **real, known-good `.SCHl` file from any other EA game of this
   era** (search for one — many are floating around game-modding sites/vgmstream's own
   test corpus) rather than constructing purely from the text spec, to catch whatever
   subtle field is being misread.
2. **Investigate the `.bnk`→`.samp` recursion gap (§1.4)** — no Game Extractor plugin
   handles this game's specific `.bnk` sub-format, but the SAME `SWVR`/`SHOC`/`Rdat`
   chunk-walking algorithm from §1.3 might apply recursively one more level (it wasn't
   tried on the `.bnk` payload itself, only assumed to need a "refpack-like" step) —
   worth directly re-running the §1.3 walker against the extracted `.bnk` bytes before
   assuming a compression layer is needed at all.
3. **Get a real C/C++ compiler on the machine** (none was available this session — no
   `gcc`, `clang`, or `cl.exe` found) and compile vgmstream from source directly, or at
   minimum compile a tiny standalone RefPack reference decompressor, to get byte-exact
   A/B comparison against the Python ports instead of guessing blind. This would resolve
   the §3.2 mystery almost immediately.
4. **Search specifically for existing modding/extraction tools for OTHER EA Redwood
   Shores / EA Black Box games from 2002-2004** (this game shares its engine generation
   with several other EA titles) — if someone has already solved audio extraction for a
   sibling title using the same SWVR/SCHl-family container, their tool's source would
   likely resolve this immediately, the same way Game Extractor's own bundled plugin
   resolved the container-format mystery.
5. Consider directly asking in game-preservation/reverse-engineering communities (e.g. the
   XeNTax-successor Discord/forums, `hcs64.com/mboard`, the vgmstream GitHub issues) —
   the original 2019-2020 forum thread on this exact problem is linked in
   `LOTR ROTK audio format notes.md`; a follow-up post referencing everything solved here
   (full container format, confirmed codec identity, target PCM format) might attract
   someone who already has the missing piece.
