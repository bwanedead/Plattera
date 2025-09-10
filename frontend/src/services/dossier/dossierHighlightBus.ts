// Simple event bus to share hovered dossier ID between panels

type Listener = (dossierId: string | null) => void;

class DossierHighlightBus {
  private listeners: Set<Listener> = new Set();

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit(dossierId: string | null): void {
    this.listeners.forEach((l) => {
      try { l(dossierId); } catch (_) { /* noop */ }
    });
  }
}

export const dossierHighlightBus = new DossierHighlightBus();


