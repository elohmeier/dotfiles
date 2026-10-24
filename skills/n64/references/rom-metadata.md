# ROM Metadata

Read this when inspecting or embedding homebrew descriptions, author/release information, versions, or artwork, or diagnosing their display on SummerCart64.

## Scope and Evidence

Keep three consumers distinct: SummerCart firmware/PC deployer, the separately installed `sc64menu.n64` (N64FlashcartMenu), and the SDK's packaging tools. Updating firmware alone does not establish menu metadata support.

Source and file-format checks on 2026-09-06 covered:

- SummerCart64 `a1e7996d2cbece686820a5c785029c68514f17b0` (2025-05-09).
- N64FlashcartMenu V0.3.3, `8c5fb11fa5f3bc4f26670e1bb03a25557f725a6a` (2026-08-26).
- Libdragon preview `5e8bd05cbc1f3f2383d156a6a0939f634bcffd9b`, including `n64metadata` and `n64.mk`. Do not assume an installed SDK or libdragon trunk contains these tools.

V0.3.2 added embedded homebrew metadata display; V0.3.3 added `num-players`. Treat the behavior below as specific to the inspected revisions. For other versions, inspect the parser and UI as well as documentation: some menu documentation still describes older behavior. The packaging tool was compiled and checked with a synthetic ROM and external ZIP extraction; menu display and hardware boot were not tested.

## Fields the Menu Consumes

The menu reads these INI keys from `[meta]`:

| Key            | V0.3.3 behavior                                                                                                                     |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `short-desc`   | Shown on the ROM screen, limited by `%.120s` to the first 120 bytes. Keep it short; this is not a 120-Unicode-character guarantee.  |
| `author`       | Shown in extra ROM information.                                                                                                     |
| `release-date` | Shown in extra ROM information; use `YYYY-MM-DD`.                                                                                   |
| `website`      | Shown as text.                                                                                                                      |
| `osi-license`  | Shown as text; use an SPDX identifier such as `MIT` when applicable.                                                                |
| `age-rating`   | Mapped to age-rating labels. `0` is unspecified; `1`, `10`, `13`, `17`, and `18` map to the displayed ESRB-style categories.        |
| `num-players`  | Maximum simultaneous players, shown in extra ROM information; defaults to 1.                                                        |
| `name`         | Parsed and used in deciding whether external metadata was found. The displayed title still comes from the 20-byte ROM header title. |

No dedicated application `version`, Git commit, build date, or build ID is interpreted. The broader libdragon metadata format accepts long descriptions, screenshots, artwork, and localized sections, but the inspected menu does not consume `long-desc`, `screenshots`, `[boxart]`, `[cartart]`, or localized metadata sections. Do not equate a file being embedded with the menu displaying it.

The ZIP metadata reader caps uncompressed `metadata.ini` at 64 KiB. The INI parser limits individual values to 255 bytes; the description display's 120-byte limit is narrower.

## Header Flags and Versioning

Offsets below refer to a big-endian ROM, normally `.z64`, starting with `80 37 12 40`.

| Offset           | Meaning                                                                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `0x20–0x33`      | 20-byte internal title, used by the menu and homebrew artwork lookup.                                                            |
| `0x38`, bit 0    | Embedded metadata ZIP is present.                                                                                                |
| `0x3C–0x3D`      | ASCII `ED` marks the homebrew header; these are the middle two characters of the four-character game code.                       |
| `0x3F`, bits 7–4 | Homebrew save type: 0 none, 1 EEPROM 4 Kbit, 2 EEPROM 16 Kbit, 3 SRAM 256 Kbit, 4 banked SRAM, 5 FlashRAM 1 Mbit, 6 SRAM 1 Mbit. |
| `0x3F`, bit 0    | Homebrew RTC support.                                                                                                            |

Do not write an application release number into `0x3F` for an `ED` ROM: it changes the save/RTC declaration. V0.3.3 still displays this byte numerically as “Version”; for example, `0x51` means FlashRAM plus RTC but appears as version 81. “SDK version” is also a legacy header value, not application version information.

For visible version information without menu changes, prefix `short-desc` with the version, such as `v1.2.3 - ...`. Keep the header title stable across releases if artwork should remain associated with it. Extra custom keys can be carried in the INI, but are not interpreted by this menu and may produce packaging-tool warnings. If asked to implement proper version support, add explicit metadata fields and UI handling rather than overloading the header byte.

The inspected SummerCart PC deployer's `guess_save_type` reads the `ED` signature and save nibble; it does not parse descriptive metadata. It checks the raw header before its database-hashing byte-order conversion, so use big-endian input for this path. Its firmware metadata/info commands describe SummerCart firmware files, not homebrew releases.

## Package Metadata

Use the project's selected host tools and inspect their availability before adding build dependencies. Current libdragon preview provides a standalone, dependency-free C++ host tool, `n64metadata`, which also works with ROMs built using other SDKs. Its availability need not justify changing the project's guest SDK revision.

Create an INI file in UTF-8, preferably with LF line endings. For example:

```ini
[meta]
name=My Homebrew
author=Example Studio
release-date=2026-09-06
osi-license=MIT
website=https://example.com/my-homebrew
age-rating=0
num-players=2
short-desc=v1.2.3 - A two-player exploration game.
```

Configure save and RTC declarations to match runtime behavior using the project's existing `N64_ROM_SAVETYPE`, `N64_ROM_RTC`, or `ed64romconfig` workflow. The metadata tool preserves that configuration; it does not infer it from game code.

```sh
# Modifies the big-endian ROM, sets ED and the metadata flag, and appends a ZIP.
n64metadata game.z64 metadata.ini

# Alternative: creates game.meta as a ZIP without modifying the ROM.
n64metadata --external game.z64 metadata.ini
```

The ZIP contains a root entry named exactly `metadata.ini`. Let the tool handle ZIP offsets and final 16 KiB padding. Use `--force` only when intentionally replacing existing embedded metadata. Keep the packaged release big-endian: byte-swapping the entire ROM also swaps the appended ZIP, which this menu opens directly from the file.

For a compatible libdragon preview `n64.mk`, integrate metadata into the existing build:

```make
# Set before the project's existing n64.mk include so its padding logic sees it.
N64_ROM_METADATA := metadata/metadata.ini

# Add to the actual ROM target's existing prerequisites.
game.z64: $(N64_ROM_METADATA)
```

Also declare referenced text/images and any generated metadata inputs as prerequisites. Otherwise changing release information alone may leave an old ROM. The inspected `n64.mk` runs metadata packaging after ROM construction and homebrew header configuration. Validate and hash the final packaged artifact.

For file-format validation, check the ROM magic, `ED` signature, metadata flag, expected save/RTC byte, ZIP entry names/content/CRC, and final size/alignment. `zipfile.ZipFile` can inspect the packaged ROM directly. Header-only changes and append-only packaging should preserve the existing ROM body. These checks establish container integrity, not menu rendering or hardware compatibility.

## Sidecars, Precedence, and Artwork

V0.3.3 text metadata lookup proceeds as follows:

1. Try sibling `game.meta` as a ZIP containing `metadata.ini`.
2. Otherwise try sibling `game.metadata.ini` as plain INI.
3. If that INI file does not exist, try `sd:/menu/metadata/<code0>/<code1>/<code2>/<code3>/metadata.ini`.
4. Try embedded metadata only if the resulting `[meta] name` is still empty.

Consequently, an external file with a nonempty `name` prevents embedded metadata from loading; fields are not merged from both sources. Include `name` in intended external overrides. The documentation describing a plain INI named `game.meta` is stale for this implementation. A directory-level `metadata.ini` is not the sibling filename constructed by this code. Its text-metadata database fallback does not implement the `homebrew/<title>` path or the three-character region fallback used by artwork.

Artwork is loaded separately from SD files, not from the ROM's embedded ZIP. For an `ED` homebrew ROM:

```text
sd:/menu/metadata/homebrew/<ROM-header-title>/boxart_front.png
```

Use the internal header title, not the ROM filename or `[meta] name`. Supported fixed filenames are `boxart_front.png`, `boxart_back.png`, `boxart_top.png`, `boxart_bottom.png`, `boxart_left.png`, `boxart_right.png`, `gamepak_front.png`, and `gamepak_back.png`. Typical front/back art is 158×112 PNG; Japanese box art is 112×158. Top/bottom spines are 158×22 and left/right spines are 112×22. The menu can cycle available images.

## Sources to Re-check

- [Menu V0.3.2 release](https://github.com/Polprzewodnikowy/N64FlashcartMenu/releases/tag/V0.3.2) and [V0.3.3 release](https://github.com/Polprzewodnikowy/N64FlashcartMenu/releases/tag/V0.3.3).
- [V0.3.3 ROM parser](https://github.com/Polprzewodnikowy/N64FlashcartMenu/blob/8c5fb11fa5f3bc4f26670e1bb03a25557f725a6a/src/menu/rom_info.c): `extract_rom_info`, `load_rom_meta_from_file`, `load_rom_meta_from_embedded_zip`, `rom_config_load`.
- [V0.3.3 ROM view](https://github.com/Polprzewodnikowy/N64FlashcartMenu/blob/8c5fb11fa5f3bc4f26670e1bb03a25557f725a6a/src/menu/views/load_rom.c), [INI parser](https://github.com/Polprzewodnikowy/N64FlashcartMenu/blob/8c5fb11fa5f3bc4f26670e1bb03a25557f725a6a/src/menu/ini_parser.c), and [artwork loader](https://github.com/Polprzewodnikowy/N64FlashcartMenu/blob/8c5fb11fa5f3bc4f26670e1bb03a25557f725a6a/src/menu/ui_components/boxart.c).
- [Libdragon packaging tool](https://github.com/DragonMinded/libdragon/blob/5e8bd05cbc1f3f2383d156a6a0939f634bcffd9b/tools/n64metadata.cpp), [n64.mk integration](https://github.com/DragonMinded/libdragon/blob/5e8bd05cbc1f3f2383d156a6a0939f634bcffd9b/n64.mk), and [metadata example](https://github.com/DragonMinded/libdragon/blob/5e8bd05cbc1f3f2383d156a6a0939f634bcffd9b/examples/brew-volley/metadata/metadata.ini).
- [Inspected SummerCart deployer parser](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/sw/deployer/src/n64.rs); the menu is a separate repository.
- [N64brew metadata specification](https://n64brew.dev/wiki/ROM_Metadata) and [homebrew ROM header](https://n64brew.dev/wiki/ROM_Header#Advanced_Homebrew_ROM_Header) describe the broader convention. Direct wiki retrieval was unavailable during the recorded check; the implementation and SDK example above established the observed support.
