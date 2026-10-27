# Text Sizing and Layout

Primary files:

- `src/shapes/Text/Text.ts`
- `src/shapes/Text/constants.ts`
- `src/shapes/Text/StyledText.ts`
- `src/shapes/IText/IText.ts`
- `src/shapes/Textbox.ts`
- `src/parser/parseAttributes.ts`
- `src/parser/normalizeValue.ts`
- `src/parser/parseFontDeclaration.ts`
- `src/shapes/Text/Text.spec.ts`
- `src/shapes/Textbox.spec.ts`

## Text Classes

- `FabricText` measures text and sets its own `width` and `height` from rendered content.
- `IText` adds editing behavior on top of `FabricText`; most sizing behavior is inherited.
- `Textbox` extends `IText`, keeps `width` as the wrapping box, and recalculates `height` from wrapped lines.
- Textbox side controls resize width instead of scaling text; height follows wrapping.
- Do not assume a text object's dimensions are stable after changing text, font, styles, or `width` on a `Textbox`.

## Defaults and Layout Properties

- Text defaults live in `textDefaultValues`, not declarations: `fontSize: 40`, `fontFamily: 'Times New Roman'`, `lineHeight: 1.16`, `charSpacing: 0`, `MIN_TEXT_WIDTH: 2`, `CACHE_FONT_SIZE: 400`, and `_fontSizeMult: 1.13`.
- Textbox defaults include `minWidth: 20`, `dynamicMinWidth: 2`, `lockScalingFlip: true`, `noScaleCache: false`, and `splitByGrapheme: false`.
- Text layout properties include `fontSize`, `fontWeight`, `fontFamily`, `fontStyle`, `lineHeight`, `text`, `charSpacing`, `textAlign`, `styles`, and path-related text props.
- `Textbox.textLayoutProperties` adds `width`, because width changes require wrapping and height recalculation.
- Text visual/layout props are in text `cacheProperties`; changing them should dirty cached rendering.

## Measurement Flow

- `initDimensions()` is the main recalculation path after text layout changes.
- `FabricText.initDimensions()` splits text, clears line/char caches, marks the object dirty, then sets `width` from `calcTextWidth()` and `height` from `calcTextHeight()`.
- If text follows a `path`, `width` and `height` come from the path dimensions instead of measured text lines.
- Text width is based on measured grapheme boxes and kerning pairs, not a simple character count.
- `_measureChar()` measures at `CACHE_FONT_SIZE` and scales by `charStyle.fontSize / CACHE_FONT_SIZE` to reduce browser rounding issues.
- Font measurement uses a shared canvas context and the Fabric font declaration, so loaded/available fonts affect results.
- `__lineWidths`, `__lineHeights`, and `__charBounds` are measurement caches; stale values usually mean the layout path was bypassed.

## Font Size, Line Height, and Text Height

- `fontSize` is in CSS pixels and can be overridden per character through `styles`.
- A line's base height uses the maximum character `fontSize` on that line multiplied by `_fontSizeMult`.
- `getHeightOfLine(lineIndex)` returns base line height multiplied by `lineHeight`.
- `calcTextHeight()` applies full `lineHeight` to all lines except the last line, where it uses the base line height.
- For a single-line text object, changing `lineHeight` does not change object `height`.
- `deltaY`, superscript, and subscript affect character positioning and can combine with per-character `fontSize`.
- Large text decoration thickness can render outside the text bounding box; caching may clip extreme underline/overline cases.

## Char Spacing, Letter Spacing, and Units

- Fabric `charSpacing` is expressed in thousandths of the current object `fontSize`, not pixels.
- `_getWidthOfCharSpacing()` calculates `(fontSize * charSpacing) / 1000`.
- `charSpacing` is object-level for spacing math; styled `fontSize` affects glyph width/height but not the object-level char-spacing conversion.
- SVG/CSS `letter-spacing` values are normalized to Fabric `charSpacing` through parser unit conversion.
- `textDecorationThickness` also uses thousandths of `fontSize`, matching the `charSpacing` unit convention.

## Textbox Wrapping and Min Width

- `Textbox.initDimensions()` clears `dynamicMinWidth`, wraps text through `_splitText()`, updates `_styleMap`, and recalculates `height`.
- Textbox wrapping splits hard lines first, then wraps each line against `width`.
- Normal wrapping splits on `_wordJoiners`; `splitByGrapheme: true` wraps by grapheme for languages or strings without spaces.
- `_wrapLine()` uses `Math.max(desiredWidth, largestWordWidth, dynamicMinWidth)`, so a long word can force the effective minimum width.
- `dynamicMinWidth` is derived from the largest measured word and char spacing; `getMinWidth()` returns `Math.max(minWidth, dynamicMinWidth)`.
- `reservedSpace` in wrapping subtracts from the desired width and contributes to `dynamicMinWidth`; check it when extending Textbox layout.
- Textbox styles are stored by original hard lines, while `_styleMap` maps wrapped visual lines back to source lines and offsets.

## Padding and Box Misconceptions

- Object `padding` is interactive padding for selection/control hit areas and border drawing; it is not CSS-like inner padding for text layout.
- `padding` does not add inset space inside `Text` or `Textbox`, does not change wrapping width, and is not part of measured text dimensions.
- To create visual text padding, use a separate background shape, custom rendering, or adjust `Textbox.width` and text position deliberately.
- When users ask why text does not wrap inside "padding", check whether they are expecting CSS box-model behavior; Fabric text does not implement that box model.
- Text backgrounds (`textBackgroundColor`) paint behind text runs/lines, not a padded rounded text container.

## Changing Text Programmatically

- Prefer `set()` for property changes so cache dirtying runs for `cacheProperties`.
- After changing text layout properties directly, call `initDimensions()` when dimensions must update immediately.
- After dimension or position changes that affect interaction, call `setCoords()` before relying on hit tests, controls, or bounding coordinates.
- On a canvas, call `requestRenderAll()` when a visual update should be scheduled.
- In editing mode, `Textbox.initDimensions()` may also refresh delayed cursor state.

## SVG and CSS Font Parsing

- SVG `font-size` and relative units are parsed through `parseAttributes()` and `parseUnit()`, using parent font size where applicable.
- CSS `font` shorthand is parsed by `parseFontDeclaration()`, including `fontSize`, optional `lineHeight`, style, weight, and family.
- `letter-spacing` and text decoration thickness normalize through `normalizeValue()` into Fabric thousandths-of-font-size units.
- SVG export serializes Fabric text with explicit font attributes and generated `tspan` positions; do not expect browser SVG text layout to be preserved exactly.

## Test Guidance

- For text measurement changes, update focused tests in `src/shapes/Text/Text.spec.ts` or `src/shapes/Textbox.spec.ts`.
- Cover default text, multiline text, styled character `fontSize`, `charSpacing`, and `lineHeight` when sizing math changes.
- For `Textbox`, test wrapping, long words, `splitByGrapheme`, `minWidth`, and style-map behavior when relevant.
- For parser changes, add SVG/CSS unit cases under parser tests and round-trip SVG tests when export behavior changes.
