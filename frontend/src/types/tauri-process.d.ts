declare module '@tauri-apps/plugin-process' {
  /**
   * Relaunch the current Tauri application. In release builds this will
   * restart the installed EXE so that a just-applied update can take
   * effect cleanly.
   */
  export function relaunch(): Promise<void>;
}

