/**
 * extension.js — Window Move & Resize GNOME Shell extension.
 *
 * Provides two hold-to-act keyboard shortcuts that drive the focused window
 * with the pointer:
 *   - Move (drag): hold the chord and the window follows the pointer until the
 *     Super key is released (or a left-button click).
 *   - Resize (center scale): hold the chord and the window scales about its
 *     pinned center as the pointer moves, until Super is released (or a mouse
 *     click / Escape).
 *
 * Components:
 *   - getFocusWindow(): Resolve the focused, user-manageable window.
 *   - startPointerDrag()/stopPointerDrag(): Pointer-driven window dragging.
 *   - startCenterScale()/stopCenterScale(): Pointer-driven scaling about the
 *     window center, keeping the center pinned in place.
 *   - WindowMoveResizeExtension: Extension lifecycle (enable/disable).
 */
import Meta from 'gi://Meta';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import Shell from 'gi://Shell';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const POINTER_POLL_INTERVAL_MS = 8;
const MIN_WINDOW_WIDTH = 160;
const MIN_WINDOW_HEIGHT = 120;

// Modifier bits that mean the Super key is held. X11 reports Super as Mod4;
// some layouts also set the dedicated Super bit, so accept either. Move/resize
// stay active only while Super is held (the <Super> in <Alt><Super>W / E).
const SUPER_HELD_MASK = Clutter.ModifierType.MOD4_MASK | Clutter.ModifierType.SUPER_MASK;

const POINTER_DRAG_KEY = 'drag-active-window-with-pointer';
const CENTER_SCALE_KEY = 'scale-active-window-from-center';

/**
 * Return the currently focused, user-manageable window.
 *
 * Windows that are absent or marked skip-taskbar (panels, docks, OSDs) are
 * ignored so hotkeys only ever act on real application windows.
 *
 * @returns {Meta.Window|null} The focused window, or null when none qualifies.
 */
function getFocusWindow() {
  const win = global.display.focus_window;
  const skipTaskbar = typeof win?.is_skip_taskbar === 'function'
    ? win.is_skip_taskbar()
    : win?.skip_taskbar;

  if (!win || skipTaskbar) {
    return null;
  }

  return win;
}

/**
 * Unmaximize a window across the differing GNOME Shell/Mutter APIs.
 *
 * Newer Mutter exposes get_maximized(); older versions expose the
 * maximizedHorizontally/maximizedVertically flags. Both paths are handled.
 *
 * @param {Meta.Window} win Window to unmaximize.
 * @returns {void}
 */
function unmaximizeWindow(win) {
  if (typeof win.get_maximized === 'function') {
    const maximized = win.get_maximized();
    if (maximized) {
      win.unmaximize(maximized);
    }
    return;
  }

  if (win.maximizedHorizontally && typeof win.unmaximize === 'function') {
    win.unmaximize(Meta.MaximizeFlags.HORIZONTAL);
  }
  if (win.maximizedVertically && typeof win.unmaximize === 'function') {
    win.unmaximize(Meta.MaximizeFlags.VERTICAL);
  }
}

/**
 * Report whether a window can be both moved and resized.
 *
 * @param {Meta.Window|null} win Candidate window.
 * @returns {boolean} True when the window supports move_resize_frame and any
 *   available allows_resize()/allows_move() checks pass.
 */
function canMoveResizeWindow(win) {
  if (!win || typeof win.move_resize_frame !== 'function') {
    return false;
  }

  // Check allows_resize/allows_move only when those methods exist.
  if (typeof win.allows_resize === 'function' && !win.allows_resize()) {
    return false;
  }
  if (typeof win.allows_move === 'function' && !win.allows_move()) {
    return false;
  }

  return true;
}

/**
 * Report whether a window can be moved (without requiring resize support).
 *
 * @param {Meta.Window|null} win Candidate window.
 * @returns {boolean} True when the window supports move_frame and any available
 *   allows_move() check passes.
 */
function canMoveWindow(win) {
  if (!win || typeof win.move_frame !== 'function') {
    return false;
  }

  if (typeof win.allows_move === 'function' && !win.allows_move()) {
    return false;
  }

  return true;
}

/**
 * Normalize a window's state so it can be freely positioned/resized.
 *
 * Clears maximized, fullscreen, minimized, and always-on-top states when the
 * corresponding methods are available on this GNOME Shell version.
 *
 * @param {Meta.Window} win Window to prepare.
 * @returns {void}
 */
function prepareWindowForMoveResize(win) {
  unmaximizeWindow(win);
  if (typeof win.unmake_fullscreen === 'function') {
    win.unmake_fullscreen();
  }
  if (typeof win.unminimize === 'function') {
    win.unminimize();
  }
  if (typeof win.unmake_above === 'function') {
    win.unmake_above();
  }
}

/**
 * Raise a window to the top and mark it most-recently-used.
 *
 * Uses the workspace-aware API when present, otherwise falls back to the
 * legacy raise_and_make_recent().
 *
 * @param {Meta.Window} win Window to raise.
 * @returns {void}
 */
function raiseWindow(win) {
  if (typeof win.raise_and_make_recent_on_workspace === 'function') {
    win.raise_and_make_recent_on_workspace(global.workspace_manager.get_active_workspace());
  } else if (typeof win.raise_and_make_recent === 'function') {
    win.raise_and_make_recent();
  }
}

/**
 * Resolve a valid monitor index for a window.
 *
 * Mutter aborts the entire shell (assertion `which_monitor >= 0` in
 * meta_window_get_work_area_for_monitor) when get_work_area_for_monitor() or
 * move_to_monitor() is called with -1. win.get_monitor() returns -1 while a
 * window is transiently off all monitors, e.g. mid workspace-switch animation.
 * Because that abort is at the C level it cannot be caught with try/catch, so
 * every monitor lookup must be clamped to a usable index here. Falls back to
 * the current monitor and finally returns -1 when no monitor is available, so
 * callers can bail out instead of crashing the shell.
 *
 * @param {Meta.Window} win Window whose monitor is requested.
 * @returns {number} A valid zero-based monitor index, or -1 when none exists.
 */
function resolveWindowMonitor(win) {
  const monitorCount = global.display.get_n_monitors();
  if (monitorCount <= 0) {
    return -1;
  }

  let index = typeof win.get_monitor === 'function' ? win.get_monitor() : -1;
  if (index < 0 || index >= monitorCount) {
    index = global.display.get_current_monitor();
  }
  if (index < 0 || index >= monitorCount) {
    return -1;
  }

  return index;
}

/**
 * Get the usable work area (excluding panels) for a window's monitor.
 *
 * @param {Meta.Window} win Window whose monitor work area is requested.
 * @returns {Meta.Rectangle|null} The work area rectangle for that monitor, or
 *   null when the window is not on any valid monitor.
 */
function getWindowWorkArea(win) {
  const monitorIndex = resolveWindowMonitor(win);
  if (monitorIndex < 0) {
    return null;
  }

  return win.get_work_area_for_monitor(monitorIndex);
}

/**
 * Test whether an event signals the end of a pointer drag.
 *
 * @param {Clutter.Event} event Event received from the captured-event signal.
 * @returns {boolean} True for a primary (left) mouse button release.
 */
function pointerDragReleaseEvent(event) {
  if (event.type !== Clutter.EventType.BUTTON_RELEASE) {
    return false;
  }

  const button = event.get_button();
  return button === 1;
}

/**
 * Test whether an event should finish an active center scale.
 *
 * Center scaling is keyboard-initiated (no button is held), so it ends on any
 * mouse-button press or an Escape key press. These events are consumed by the
 * caller so the click/keypress that finishes scaling does not also reach the
 * underlying window.
 *
 * @param {Clutter.Event} event Event received from the captured-event signal.
 * @returns {boolean} True when the scale should stop.
 */
function centerScaleEndEvent(event) {
  if (event.type === Clutter.EventType.BUTTON_PRESS) {
    return true;
  }

  return event.type === Clutter.EventType.KEY_PRESS
    && event.get_key_symbol() === Clutter.KEY_Escape;
}

/**
 * Stop an in-progress pointer drag and settle the window in place.
 *
 * Cancels the drag timeout, clamps the window inside its work area, raises it,
 * and clears the drag state. Safe to call when no drag is active.
 *
 * @param {{timeoutId: ?number, window: ?Meta.Window}} state Pointer drag state.
 * @returns {void}
 */
function stopPointerDrag(state) {
  if (!state) {
    return;
  }

  if (state.timeoutId) {
    GLib.source_remove(state.timeoutId);
    state.timeoutId = null;
  }

  const win = state.window;
  if (!win) {
    return;
  }

  try {
    prepareWindowForMoveResize(win);
    const workArea = getWindowWorkArea(win);
    if (!workArea) {
      return;
    }
    const frame = win.get_frame_rect();

    // Clamp to work area.
    let x = Math.max(workArea.x, Math.min(frame.x, workArea.x + workArea.width - frame.width));
    let y = Math.max(workArea.y, Math.min(frame.y, workArea.y + workArea.height - frame.height));

    win.move_frame(true, x, y);
    raiseWindow(win);
  } catch (error) {
    console.error(`window-move-resize: failed to stop pointer drag: ${error}`);
  }

  state.window = null;
}

/**
 * Begin dragging the focused window with the pointer.
 *
 * Records the pointer-to-frame offset and installs a periodic timeout
 * (POINTER_POLL_INTERVAL_MS) that follows the pointer. The drag is held: it
 * ends as soon as Super is released (mirroring center scaling), and also via
 * stopPointerDrag() on a left-button release. No-ops when a drag is already
 * active or the focused window cannot be moved. Errors are logged.
 *
 * @param {{timeoutId: ?number, window: ?Meta.Window, pointerX: number,
 *   pointerY: number, armed: boolean}} state Pointer drag state to populate.
 * @returns {void}
 */
function startPointerDrag(state) {
  if (!state) {
    return;
  }

  // Never stack a second drag on top of a live one. Re-entry (e.g. spamming
  // the chord) would orphan the previous timeout — it keeps running because
  // state.window is still set — and every leaked 8ms source calls move_frame()
  // + raiseWindow(), piling up until the shell is overwhelmed and crashes.
  if (state.timeoutId) {
    return;
  }

  const win = getFocusWindow();
  if (!canMoveWindow(win)) {
    return;
  }

  try {
    prepareWindowForMoveResize(win);
    state.window = win;
    const [pointerX, pointerY] = global.get_pointer();
    const frame = win.get_frame_rect();
    state.pointerX = pointerX - frame.x;
    state.pointerY = pointerY - frame.y;
    // Only auto-stop on Super release once Super has actually been seen held,
    // so the chord settling on the first poll cannot end the drag instantly.
    state.armed = false;

    // Start a timeout to handle the drag.
    state.timeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, POINTER_POLL_INTERVAL_MS, () => {
      if (!state || !state.window) {
        return GLib.SOURCE_REMOVE;
      }

      const win = state.window;
      const [pointerX, pointerY, mods] = global.get_pointer();

      // The drag is "while held": end the moment the Super key is let go (after
      // it has been seen held). Without this the window keeps tracking the
      // pointer forever, since the only other exit is a left-button release.
      const superHeld = (mods & SUPER_HELD_MASK) !== 0;
      if (superHeld) {
        state.armed = true;
      } else if (state.armed) {
        // Clear without source_remove(): returning SOURCE_REMOVE removes this
        // very source, so removing it here too would double-free.
        state.timeoutId = null;
        state.window = null;
        raiseWindow(win);
        return GLib.SOURCE_REMOVE;
      }

      let newX = pointerX - state.pointerX;
      let newY = pointerY - state.pointerY;

      // Clamp to work area.
      const workArea = getWindowWorkArea(win);
      if (!workArea) {
        return GLib.SOURCE_CONTINUE;
      }
      newX = Math.max(workArea.x, Math.min(newX, workArea.x + workArea.width - win.get_frame_rect().width));
      newY = Math.max(workArea.y, Math.min(newY, workArea.y + workArea.height - win.get_frame_rect().height));

      win.move_frame(true, newX, newY);
      raiseWindow(win);

      return GLib.SOURCE_CONTINUE;
    });
  } catch (error) {
    console.error(`window-move-resize: failed to start pointer drag: ${error}`);
  }
}

/**
 * Warp the pointer to an absolute screen position.
 *
 * Used to recenter the pointer on the window before center scaling so the
 * scale tracks the pointer's offset from that center. No-ops (logging only)
 * when the backend does not expose a warpable seat.
 *
 * @param {number} x Absolute X coordinate to move the pointer to.
 * @param {number} y Absolute Y coordinate to move the pointer to.
 * @returns {void}
 */
function warpPointer(x, y) {
  try {
    const seat = global.backend?.get_default_seat?.();
    if (seat && typeof seat.warp_pointer === 'function') {
      seat.warp_pointer(x, y);
    }
  } catch (error) {
    console.error(`window-move-resize: failed to warp pointer: ${error}`);
  }
}

/**
 * Stop an in-progress center scale and settle the window in place.
 *
 * Cancels the scale timeout, raises the window, and clears the scale state.
 * Safe to call when no scale is active.
 *
 * @param {{timeoutId: ?number, window: ?Meta.Window}} state Center scale state.
 * @returns {void}
 */
function stopCenterScale(state) {
  if (!state) {
    return;
  }

  if (state.timeoutId) {
    GLib.source_remove(state.timeoutId);
    state.timeoutId = null;
  }

  const win = state.window;
  if (win) {
    try {
      raiseWindow(win);
    } catch (error) {
      console.error(`window-move-resize: failed to stop center scale: ${error}`);
    }
  }

  state.window = null;
}

/**
 * Begin scaling the focused window about its center with the pointer.
 *
 * Pins the window's current center in place and warps the pointer to the
 * window's bottom-right corner, then installs a periodic timeout
 * (POINTER_POLL_INTERVAL_MS) that resizes the window to track the pointer's
 * offset from that center on both axes: the window's half width follows
 * |pointerX - centerX| and its half height follows |pointerY - centerY|.
 * Because the pointer starts half a frame away from the center on each axis,
 * the window keeps its current size when the resize begins and only changes
 * once the pointer moves — outward to enlarge, back toward the center to
 * shrink, on both axes independently and simultaneously. The size is clamped to
 * MIN_WINDOW_WIDTH/HEIGHT and to the largest extent that keeps the window
 * inside the work area around that fixed center.
 *
 * Scaling stays active only while Super is held (the chord is held down) and
 * ends as soon as Super is released; it also ends via stopCenterScale() on a
 * mouse-button press or Escape. No-ops when the focused window cannot be
 * move/resized. Errors are logged.
 *
 * @param {{timeoutId: ?number, window: ?Meta.Window, centerX: number,
 *   centerY: number, armed: boolean}} state Center scale state to populate.
 * @returns {void}
 */
function startCenterScale(state) {
  if (!state) {
    return;
  }

  const win = getFocusWindow();
  if (!canMoveResizeWindow(win)) {
    return;
  }

  try {
    prepareWindowForMoveResize(win);

    const frame = win.get_frame_rect();
    state.window = win;
    state.centerX = Math.round(frame.x + frame.width / 2);
    state.centerY = Math.round(frame.y + frame.height / 2);
    // Only stop on Super release once we have actually seen Super held, so the
    // chord settling on the first poll cannot end scaling immediately.
    state.armed = false;
    raiseWindow(win);
    // Warp the pointer to the window's bottom-right corner rather than its
    // center. Because the size tracks twice the pointer's offset from the
    // pinned center (width = 2 * |pointerX - centerX|), placing the pointer
    // half a frame away on each axis makes the initial computed size equal the
    // window's current size, so initiating a resize no longer snaps the window
    // down to the minimum — it stays put until the pointer actually moves.
    warpPointer(
      state.centerX + Math.round(frame.width / 2),
      state.centerY + Math.round(frame.height / 2),
    );

    state.timeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, POINTER_POLL_INTERVAL_MS, () => {
      if (!state || !state.window) {
        return GLib.SOURCE_REMOVE;
      }

      const win = state.window;
      const workArea = getWindowWorkArea(win);
      if (!workArea) {
        return GLib.SOURCE_CONTINUE;
      }

      const [pointerX, pointerY, mods] = global.get_pointer();

      // End the moment the held Super key is let go (after it has been seen).
      const superHeld = (mods & SUPER_HELD_MASK) !== 0;
      if (superHeld) {
        state.armed = true;
      } else if (state.armed) {
        // Clear without source_remove(): returning SOURCE_REMOVE removes this
        // very source, so removing it here too would double-free.
        state.timeoutId = null;
        state.window = null;
        raiseWindow(win);
        return GLib.SOURCE_REMOVE;
      }

      // The window spans twice the pointer's offset from the pinned center on
      // each axis, so moving the pointer outward grows it and moving it back
      // shrinks it, horizontally and vertically at once.
      let width = 2 * Math.abs(pointerX - state.centerX);
      let height = 2 * Math.abs(pointerY - state.centerY);

      // Largest half-size that keeps the window inside the work area while its
      // center stays fixed, so growing never nudges the pinned center.
      const maxHalfWidth = Math.min(state.centerX - workArea.x, workArea.x + workArea.width - state.centerX);
      const maxHalfHeight = Math.min(state.centerY - workArea.y, workArea.y + workArea.height - state.centerY);
      const maxWidth = Math.max(MIN_WINDOW_WIDTH, 2 * maxHalfWidth);
      const maxHeight = Math.max(MIN_WINDOW_HEIGHT, 2 * maxHalfHeight);

      width = Math.round(Math.max(MIN_WINDOW_WIDTH, Math.min(width, maxWidth)));
      height = Math.round(Math.max(MIN_WINDOW_HEIGHT, Math.min(height, maxHeight)));

      const x = Math.round(state.centerX - width / 2);
      const y = Math.round(state.centerY - height / 2);

      win.move_resize_frame(true, x, y, width, height);

      return GLib.SOURCE_CONTINUE;
    });
  } catch (error) {
    console.error(`window-move-resize: failed to start center scale: ${error}`);
  }
}

/**
 * GNOME Shell extension entry point for pointer-driven window move/resize.
 *
 * On enable() it registers the move (drag) and resize (center scale)
 * keybindings and listens for the pointer/keyboard events that end each
 * gesture. On disable() it tears all of that down so the extension can be
 * cleanly reloaded.
 */
export default class WindowMoveResizeExtension extends Extension {
  /**
   * Register the move/resize keybindings and the captured-event listener.
   *
   * @returns {void}
   */
  enable() {
    this._settings = this.getSettings();
    this._keybindings = [];
    this._pointerDragState = {
      timeoutId: null,
      window: null,
      pointerX: 0,
      pointerY: 0,
      armed: false,
    };
    this._centerScaleState = {
      timeoutId: null,
      window: null,
      centerX: 0,
      centerY: 0,
      armed: false,
    };

    this._capturedEventId = global.stage.connect('captured-event', (actor, event) => {
      if (this._pointerDragState?.timeoutId && pointerDragReleaseEvent(event)) {
        stopPointerDrag(this._pointerDragState);
      }

      if (this._centerScaleState?.timeoutId && centerScaleEndEvent(event)) {
        stopCenterScale(this._centerScaleState);
        return Clutter.EVENT_STOP;
      }

      return Clutter.EVENT_PROPAGATE;
    });

    Main.wm.addKeybinding(
      POINTER_DRAG_KEY,
      this._settings,
      Meta.KeyBindingFlags.NONE,
      Shell.ActionMode.NORMAL,
      () => {
        // Hold-to-drag: start on press; releasing Super (or a left-button
        // click) ends it. Ignore re-triggers while already active so spamming
        // the chord cannot stack timeouts and overwhelm the shell.
        if (!this._pointerDragState?.timeoutId) {
          startPointerDrag(this._pointerDragState);
        }
      },
    );
    this._keybindings.push(POINTER_DRAG_KEY);

    Main.wm.addKeybinding(
      CENTER_SCALE_KEY,
      this._settings,
      Meta.KeyBindingFlags.NONE,
      Shell.ActionMode.NORMAL,
      () => {
        // Hold-to-scale: start on press; releasing Super (or Escape / a mouse
        // click) ends it. Ignore re-triggers while already active.
        if (!this._centerScaleState?.timeoutId) {
          startCenterScale(this._centerScaleState);
        }
      },
    );
    this._keybindings.push(CENTER_SCALE_KEY);
  }

  /**
   * Unregister keybindings and listeners, releasing all resources acquired in
   * enable().
   *
   * @returns {void}
   */
  disable() {
    if (this._pointerDragState) {
      stopPointerDrag(this._pointerDragState);
      this._pointerDragState = null;
    }

    if (this._centerScaleState) {
      stopCenterScale(this._centerScaleState);
      this._centerScaleState = null;
    }

    if (this._capturedEventId) {
      global.stage.disconnect(this._capturedEventId);
      this._capturedEventId = null;
    }

    if (this._keybindings) {
      for (const bindingName of this._keybindings) {
        Main.wm.removeKeybinding(bindingName);
      }
      this._keybindings = null;
    }

    this._settings = null;
  }
}
