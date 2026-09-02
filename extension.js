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
 * The reusable, version-spanning window/pointer helpers live in
 * windowUtils.js and all logging goes through the centralized logger in
 * logger.js; this file owns the gesture state machines (the polled timeouts)
 * and the extension lifecycle.
 *
 * Components:
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

import { logger } from './logger.js';
import {
  getFocusWindow,
  canMoveWindow,
  canMoveResizeWindow,
  prepareWindowForMoveResize,
  raiseWindow,
  getWorkAreaAt,
  warpPointer,
  pointerDragReleaseEvent,
  centerScaleEndEvent,
} from './windowUtils.js';

const POINTER_POLL_INTERVAL_MS = 8;
const MIN_WINDOW_WIDTH = 160;
const MIN_WINDOW_HEIGHT = 120;

// Modifier bits that mean the Super key is held. X11 reports Super as Mod4;
// some layouts also set the dedicated Super bit, so accept either. Move/resize
// stay active only while Super is held (the <Super> in <Alt><Super>W / E).
const SUPER_HELD_MASK = Clutter.ModifierType.MOD4_MASK | Clutter.ModifierType.SUPER_MASK;

// Modifier bit global.get_pointer() reports while the left mouse button is
// held. Gesture ends are detected from this polled mask rather than from the
// stage's 'captured-event' signal alone, because Mutter delivers a click that
// lands on an application window straight to that client: the stage never sees
// the BUTTON_RELEASE (always on Wayland, and on X11 whenever the shell holds no
// pointer grab), so a click-to-drop exit built only on it never fires.
const DRAG_BUTTON_MASK = Clutter.ModifierType.BUTTON1_MASK;

// A held gesture must always keep a way out. Both exits are conditional — the
// Super exit needs Super to have been seen held, the click exit needs a button
// press to have been seen — so a gesture that observes neither has no exit at
// all and would follow the pointer until the Shell is restarted. Give every
// gesture this long to observe its hold, then end it instead of running on.
const GESTURE_ARM_GRACE_MS = 600;

const POINTER_DRAG_KEY = 'drag-active-window-with-pointer';
const CENTER_SCALE_KEY = 'scale-active-window-from-center';

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

  // Drop the reference up front: the settle below can bail out early (no usable
  // work area), and leaving state.window set past that return kept a stale
  // window on a gesture that had already ended.
  state.window = null;

  try {
    prepareWindowForMoveResize(win);
    const frame = win.get_frame_rect();

    // Settle against the monitor the window visually landed on, found from its
    // own center. win.get_monitor() can still report the monitor the drag
    // started on until the compositor settles the move, which would yank a
    // window dragged across screens back to where it came from on release.
    const workArea = getWorkAreaAt(
      win,
      frame.x + Math.round(frame.width / 2),
      frame.y + Math.round(frame.height / 2),
    );
    if (!workArea) {
      return;
    }

    // Clamp to work area, top-left aligning windows too large for it.
    const maxX = workArea.x + workArea.width - frame.width;
    const maxY = workArea.y + workArea.height - frame.height;
    const x = maxX < workArea.x ? workArea.x : Math.max(workArea.x, Math.min(frame.x, maxX));
    const y = maxY < workArea.y ? workArea.y : Math.max(workArea.y, Math.min(frame.y, maxY));

    win.move_frame(true, x, y);
    raiseWindow(win);
    logger.info(`pointer drag stopped; window settled at ${x},${y}`);
  } catch (error) {
    logger.error(`failed to stop pointer drag: ${error}`);
  }
}

/**
 * End an active pointer drag from inside its own poll callback.
 *
 * The poll is about to drop its GLib source by returning SOURCE_REMOVE, so the
 * source id is cleared before delegating to stopPointerDrag(): calling
 * GLib.source_remove() on the source that is currently dispatching would
 * double-free it. Routing through stopPointerDrag() means every gesture end
 * settles the window the same way — clamped into the work area of the monitor
 * it visually landed on, then raised.
 *
 * @param {{timeoutId: ?number, window: ?Meta.Window}} state Pointer drag state
 *   owning the running poll.
 * @param {string} reason Human-readable cause of the end, for the log.
 * @returns {number} GLib.SOURCE_REMOVE, for the poll callback to return.
 */
function finishPointerDragFromPoll(state, reason) {
  state.timeoutId = null;
  logger.info(`pointer drag ending (${reason})`);
  stopPointerDrag(state);
  return GLib.SOURCE_REMOVE;
}

/**
 * Begin dragging the focused window with the pointer.
 *
 * Records the pointer-to-frame offset and installs a periodic timeout
 * (POINTER_POLL_INTERVAL_MS) that follows the pointer. The drag is held: the
 * same poll watches the modifier mask and ends the drag as soon as Super is
 * released (mirroring center scaling) or a pressed left button is let go, and
 * gives up entirely when neither hold shows up within GESTURE_ARM_GRACE_MS, so
 * a drag can never outlive the gesture that started it. No-ops when a drag is
 * already active or the focused window cannot be moved. Errors are logged.
 *
 * @param {{timeoutId: ?number, window: ?Meta.Window, pointerX: number,
 *   pointerY: number, armed: boolean, buttonHeld: boolean, startedAt: number}}
 *   state Pointer drag state to populate.
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
    logger.debug('startPointerDrag: drag already active; ignoring re-trigger');
    return;
  }

  const win = getFocusWindow();
  if (!canMoveWindow(win)) {
    logger.debug('startPointerDrag: focused window cannot be moved; ignoring');
    return;
  }

  try {
    prepareWindowForMoveResize(win);
    state.window = win;
    const [pointerX, pointerY, startMods] = global.get_pointer();
    const frame = win.get_frame_rect();
    state.pointerX = pointerX - frame.x;
    state.pointerY = pointerY - frame.y;
    // Arm the Super-release exit from the modifier state at the instant the
    // chord fired, not from the first poll 8ms later. Waiting for the poll lost
    // the race whenever the chord was released inside that window: state.armed
    // stayed false, the Super exit never engaged, and the window followed the
    // pointer with no way to stop it.
    state.armed = (startMods & SUPER_HELD_MASK) !== 0;
    // A click ends the drag on the button's *release*, so a press has to be seen
    // first — including one already held when the drag started.
    state.buttonHeld = (startMods & DRAG_BUTTON_MASK) !== 0;
    // Reference point for the arming grace period below.
    state.startedAt = GLib.get_monotonic_time();
    logger.info('pointer drag started');

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
        return finishPointerDragFromPoll(state, 'Super released');
      }

      // Click-to-drop is decided here, from the polled button mask, and not by
      // the stage 'captured-event' handler alone: that handler never receives
      // the BUTTON_RELEASE of a click that lands on an application window, so
      // relying on it left the window glued to the pointer after the click was
      // already let go. Ending on release (not press) keeps the documented
      // gesture: press the button, then let go to drop the window.
      const buttonHeld = (mods & DRAG_BUTTON_MASK) !== 0;
      if (buttonHeld) {
        state.buttonHeld = true;
      } else if (state.buttonHeld) {
        return finishPointerDragFromPoll(state, 'left button released');
      }

      // Neither exit ever armed: no hold has been observed since the drag
      // started, so nothing that follows could ever end it. Stop rather than
      // drag the window around forever.
      const heldFor = GLib.get_monotonic_time() - state.startedAt;
      if (!state.armed && !state.buttonHeld && heldFor > GESTURE_ARM_GRACE_MS * 1000) {
        return finishPointerDragFromPoll(state, 'no hold detected');
      }

      let newX = pointerX - state.pointerX;
      let newY = pointerY - state.pointerY;

      // Clamp to the work area of the monitor under the *pointer*, not the one
      // the window currently sits on. Clamping against the window's own monitor
      // pins it at that monitor's edge and the drag can never cross to another
      // screen; following the pointer's monitor lets the window move across
      // monitors and still land fully inside the destination's work area.
      const workArea = getWorkAreaAt(win, pointerX, pointerY);
      if (!workArea) {
        return GLib.SOURCE_CONTINUE;
      }

      // A window larger than the destination work area has a negative clamp
      // range; align it to the top-left corner instead of letting the inverted
      // min/max push it off-screen on a smaller monitor.
      const frameRect = win.get_frame_rect();
      const maxX = workArea.x + workArea.width - frameRect.width;
      const maxY = workArea.y + workArea.height - frameRect.height;
      newX = maxX < workArea.x ? workArea.x : Math.max(workArea.x, Math.min(newX, maxX));
      newY = maxY < workArea.y ? workArea.y : Math.max(workArea.y, Math.min(newY, maxY));

      win.move_frame(true, newX, newY);
      raiseWindow(win);

      return GLib.SOURCE_CONTINUE;
    });
  } catch (error) {
    logger.error(`failed to start pointer drag: ${error}`);
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
      logger.info('center scale stopped');
    } catch (error) {
      logger.error(`failed to stop center scale: ${error}`);
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

  // Match pointer drag's re-entry behavior: a held or repeated chord must not
  // stack a second 8ms resize timeout on top of the active gesture.
  if (state.timeoutId) {
    logger.debug('startCenterScale: scale already active; ignoring re-trigger');
    return;
  }

  const win = getFocusWindow();
  if (!canMoveResizeWindow(win)) {
    logger.debug('startCenterScale: focused window cannot be resized; ignoring');
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
    logger.info(`center scale started; center pinned at ${state.centerX},${state.centerY}`);

    state.timeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, POINTER_POLL_INTERVAL_MS, () => {
      if (!state || !state.window) {
        return GLib.SOURCE_REMOVE;
      }

      const win = state.window;
      // Use the monitor holding the pinned center: the window may have been
      // dragged to another monitor moments ago, and win.get_monitor() only
      // updates once the compositor settles the move.
      const workArea = getWorkAreaAt(win, state.centerX, state.centerY);
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
        logger.info('center scale ended (Super released)');
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
    logger.error(`failed to start center scale: ${error}`);
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
      buttonHeld: false,
      startedAt: 0,
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

    logger.info('extension enabled (pointer move/center resize keybindings registered)');
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
    logger.info('extension disabled');
  }
}
