type Handler = () => void;
const subs: Record<string, Set<Handler>> = {};

export function emit(event: string) {
  subs[event]?.forEach(h => h());
}

export function on(event: string, handler: Handler): () => void {
  if (!subs[event]) subs[event] = new Set();
  subs[event].add(handler);
  return () => subs[event].delete(handler);
}
