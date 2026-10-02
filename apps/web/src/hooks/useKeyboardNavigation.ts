'use client';

import { useEffect, useCallback } from 'react';
import { Hotspot } from '../types/api';

interface KeyboardNavigationProps {
  hotspots: Hotspot[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCloseDrawer: () => void;
  isDrawerOpen: boolean;
}

export function useKeyboardNavigation({
  hotspots,
  selectedId,
  onSelect,
  onCloseDrawer,
  isDrawerOpen,
}: KeyboardNavigationProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      // Escape closes drawer
      if (e.key === 'Escape') {
        if (isDrawerOpen) {
          e.preventDefault();
          onCloseDrawer();
          return;
        }
      }

      // Do not intercept if user is typing in an input or select
      const activeTag = document.activeElement?.tagName?.toLowerCase();
      if (activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select') {
        return;
      }

      // Arrow navigation across incident queue
      if (e.key === 'ArrowDown' || e.key === 'j') {
        if (hotspots.length === 0) return;
        e.preventDefault();
        const currentIndex = hotspots.findIndex((h) => h.id === selectedId);
        const nextIndex = currentIndex < hotspots.length - 1 ? currentIndex + 1 : 0;
        onSelect(hotspots[nextIndex].id);
      } else if (e.key === 'ArrowUp' || e.key === 'k') {
        if (hotspots.length === 0) return;
        e.preventDefault();
        const currentIndex = hotspots.findIndex((h) => h.id === selectedId);
        const prevIndex = currentIndex > 0 ? currentIndex - 1 : hotspots.length - 1;
        onSelect(hotspots[prevIndex].id);
      }
    },
    [hotspots, selectedId, onSelect, onCloseDrawer, isDrawerOpen]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}

export default useKeyboardNavigation;
