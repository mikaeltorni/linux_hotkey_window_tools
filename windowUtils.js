/**
 * windowUtils.js — Pure window/pointer helpers for the Window Move & Resize
 * extension.
 *
 * These functions wrap the parts of the Meta/Clutter/Mutter API that differ
 * across GNOME Shell versions (45–50) and the monitor/work-area lookups that
 * can otherwise crash the shell. They hold no module state: every function
 * takes its inputs as arguments and reads only from the live `global` shell
 * objects, which keeps them individually testable and reusable from the gesture
 * code in extension.js.
 *
 * Components:
 *   - getFocusWindow(): Resolve the focused, user-manageable window.
 *   - canMoveWindow()/canMoveResizeWindow(): Capability checks for a window.
 *   - prepareWindowForMoveResize(): Clear states that block free positioning.
 *   - raiseWindow(): Raise + mark most-recently-used across API versions.
 *   - getWindowWorkArea(): Crash-safe work-area lookup for a window's monitor.
 *   - warpPointer(): Move the pointer to an absolute screen position.
 *   - pointerDragReleaseEvent()/centerScaleEndEvent(): Gesture-end predicates.
 *
 * Usage:
 *   import { getFocusWindow, canMoveWindow } from './windowUtils.js';
 *   const win = getFocusWindow();
 *   if (canMoveWindow(win)) { ... }
 */
import Meta from 'gi://Meta';
import Clutter from 'gi://Clutter';
import { logger } from './logger.js';

/**
 * Return the currently focused, user-manageable window.
 *
 * Windows that are absent or marked skip-taskbar (panels, docks, OSDs) are
 * ignored so hotkeys only ever act on real application windows.
 *
 * @returns {Meta.Window|null} The focused window, or null when none qualifies.
 */
export function getFocusWindow() {
  const win = global.display.focus_window;
  const skipTaskbar = typeof win?.is_skip_taskbar === 'function'
    ? win.is_skip_taskbar()
    : win?.skip_taskbar;

  if (!win || skipTaskbar) {
    logger.debug('getFocusWindow: no user-manageable window is focused');
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
export function canMoveResizeWindow(win) {
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
export function canMoveWindow(win) {
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
export function prepareWindowForMoveResize(win) {
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
export function raiseWindow(win) {
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
    logger.warn('resolveWindowMonitor: no monitors reported by the display');
    return -1;
  }

  let index = typeof win.get_monitor === 'function' ? win.get_monitor() : -1;
  if (index < 0 || index >= monitorCount) {
    index = global.display.get_current_monitor();
  }
  if (index < 0 || index >= monitorCount) {
    logger.warn('resolveWindowMonitor: window is not on any valid monitor');
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
export function getWindowWorkArea(win) {
  const monitorIndex = resolveWindowMonitor(win);
  if (monitorIndex < 0) {
    return null;
  }

  return win.get_work_area_for_monitor(monitorIndex);
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
export function warpPointer(x, y) {
  try {
    const seat = global.backend?.get_default_seat?.();
    if (seat && typeof seat.warp_pointer === 'function') {
      seat.warp_pointer(x, y);
    } else {
      logger.debug('warpPointer: backend exposes no warpable seat; skipping warp');
    }
  } catch (error) {
    logger.error(`failed to warp pointer: ${error}`);
  }
}

/**
 * Test whether an event signals the end of a pointer drag.
 *
 * @param {Clutter.Event} event Event received from the captured-event signal.
 * @returns {boolean} True for a primary (left) mouse button release.
 */
export function pointerDragReleaseEvent(event) {
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
export function centerScaleEndEvent(event) {
  if (event.type === Clutter.EventType.BUTTON_PRESS) {
    return true;
  }

  return event.type === Clutter.EventType.KEY_PRESS
    && event.get_key_symbol() === Clutter.KEY_Escape;
}
