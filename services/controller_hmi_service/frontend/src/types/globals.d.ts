// Transitional Window declarations for the inline on*= handlers and the
// runtime config script. Deleted in Phase 3 when inline handlers are
// replaced by addEventListener wiring (epic #59).

import type { HmiConfig } from './api';

declare global {
  interface Window {
    HMI_CONFIG?: HmiConfig;

    App: {
      showWelcome(): void;
      showLogin(): void;
      showRegister(): void;
      showSession(): void;
      showAsr(): Promise<void>;
      submitLogin(e: Event): Promise<void>;
      submitRegister(e: Event): Promise<void>;
      submitStartSession(): Promise<void>;
    };

    Asr: {
      initScreen(): Promise<void>;
      teardown(): void;
      saveConfig(): Promise<void>;
      switchBackend(val: string): void;
      capturePtt(): void;
      reloadOllamaModels(): Promise<void>;
      onInputDeviceChange(): Promise<void>;
    };

    AtisModal: {
      open(): void;
      close(): void;
      onOverlayClick(e: MouseEvent): void;
      send(): void;
    };

    Ptt: {
      init(): Promise<void>;
      addAgentMessage(callsign: string, text: string): void;
      toggleConfig(): Promise<void>;
      capturePttKey(): void;
      saveQuickConfig(): void;
      getSessionId(): string;
    };

    Debrief: {
      openAndGenerate(sessionId: string, icao: string): Promise<void>;
      waitClose(): Promise<void>;
    };
  }
}

export {};
