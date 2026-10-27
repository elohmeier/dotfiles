# Pi TUI

Use `@earendil-works/pi-tui` when building terminal UIs or custom Pi extension UI components.

Source entry points:

- `packages/tui/src/index.ts`
- `packages/tui/src/tui.ts`
- `packages/tui/src/terminal.ts`
- `packages/tui/src/keys.ts`
- `packages/tui/src/components/*`

## Primary Exports

Core:

- `TUI`
- `Container`
- `Component`
- `Focusable`
- `CURSOR_MARKER`
- `ProcessTerminal`
- `Terminal`

Components:

- `Text`
- `TruncatedText`
- `Input`
- `Editor`
- `Markdown`
- `Loader`
- `CancellableLoader`
- `SelectList`
- `SettingsList`
- `Spacer`
- `Image`
- `Box`

Input/utilities:

- `matchesKey`
- `parseKey`
- `Key`
- `KeybindingsManager`
- `CombinedAutocompleteProvider`
- `visibleWidth`
- `truncateToWidth`
- `wrapTextWithAnsi`

## Component Contract

Every component implements:

```typescript
interface Component {
  render(width: number): string[];
  handleInput?(data: string): void;
  wantsKeyRelease?: boolean;
  invalidate(): void;
}
```

Rules:

- Every rendered line must fit within `width`.
- Use `truncateToWidth()` or wrapping utilities for dynamic text.
- Call or implement `invalidate()` for cached rendering.
- If emitting styled multi-line text, reapply styles per line or use `wrapTextWithAnsi()`.
- The TUI appends reset sequences to each rendered line; styles do not carry across lines.

## TUI Rendering

`TUI` owns:

- child component tree
- focus
- overlays
- input listeners
- differential rendering
- synchronized output
- hardware cursor positioning
- Kitty/iTerm image cleanup

Rendering strategies:

- first render writes all lines
- width change or change above viewport triggers full re-render
- normal updates move to first changed line and render changed suffix

Use `tui.requestRender()` after state changes.

## Focus And IME

Components that show a text cursor should implement `Focusable` and emit `CURSOR_MARKER` at the cursor position when focused.

Containers with child inputs must propagate focus to the child:

```typescript
class SearchDialog extends Container implements Focusable {
  private _focused = false;

  get focused(): boolean {
    return this._focused;
  }

  set focused(value: boolean) {
    this._focused = value;
    this.searchInput.focused = value;
  }
}
```

This matters for IME candidate window positioning.

## Overlays

Use `tui.showOverlay(component, options?)` for dialogs and modal UI.

Options include:

- `width`, `minWidth`, `maxHeight`
- `anchor`
- `offsetX`, `offsetY`
- `row`, `col`
- `margin`
- `visible(termWidth, termHeight)`
- `nonCapturing`

Overlay handle:

- `hide()`
- `setHidden(hidden)`
- `isHidden()`
- `focus()`
- `unfocus(options?)`
- `isFocused()`

Prefer overlays for modal/select/editor surfaces in extensions instead of replacing the whole app when the task is localized.

## Keyboard Input

Use `matchesKey(data, Key.*)`:

```typescript
import { Key, matchesKey } from "@earendil-works/pi-tui";

if (matchesKey(data, Key.escape)) {
  cancel();
}
if (matchesKey(data, Key.ctrl("c"))) {
  quit();
}
```

`Key` supports special keys, symbols, and modifiers such as:

- `Key.enter`, `Key.escape`, `Key.tab`
- `Key.up`, `Key.down`, `Key.left`, `Key.right`
- `Key.ctrl("c")`
- `Key.ctrlShift("p")`
- `Key.alt("left")`

`ProcessTerminal` negotiates Kitty keyboard protocol when possible and normalizes terminal quirks such as Apple Terminal Shift+Enter.

## Built-In Components

Use `Editor` for multi-line prompt input with autocomplete and paste handling.

Use `Input` for single-line text.

Use `SelectList` for option selection.

Use `SettingsList` for settings panels.

Use `Markdown` for rendered markdown. Provide a `MarkdownTheme` and optional highlighter.

Use `Image` for inline terminal images. It supports Kitty and iTerm2 protocols and falls back to text on unsupported terminals.

Use `Loader` or `CancellableLoader` for async work indicators.

## Extension Custom UI

Pi coding-agent exports additional interactive components from `@earendil-works/pi-coding-agent`, but custom extension UI should still follow the `pi-tui` component contract.

When using `ctx.ui.custom()`, return a component and call `done(result)` when complete.

When replacing the editor, extend `CustomEditor` from `@earendil-works/pi-coding-agent` when you need app-level keybindings to keep working. Call `super.handleInput(data)` for keys your editor does not consume.

## Debugging

Set `PI_TUI_WRITE_LOG` to capture raw ANSI output:

```bash
PI_TUI_WRITE_LOG=/tmp/tui-ansi.log npx tsx test/chat-simple.ts
```

Use `VirtualTerminal` test patterns in `packages/tui/test/` for component and rendering tests.
