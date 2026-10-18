'use client';
import {useEffect, useState} from 'react';

const allowed = /^(system|theme-(forge|nebula|phosphor|neon|daylight|cyberpunk|monokai|obsidian|blueprint|solarized))$/;

export default function useAppearance() {
  const [preference, setPreference] = useState('system');
  const [systemDark, setSystemDark] = useState(false);
  useEffect(() => {
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const sync = () => setSystemDark(typeof window.__DECAD_DESKTOP__?.systemDark === 'boolean' ? window.__DECAD_DESKTOP__.systemDark : query.matches);
    sync();
    query.addEventListener('change', sync);
    window.addEventListener('decad-system-appearance', sync);
    try {
      const saved = localStorage.getItem('decad-theme');
      if (allowed.test(saved)) setPreference(saved);
    } catch {}
    return () => {query.removeEventListener('change', sync);window.removeEventListener('decad-system-appearance', sync);};
  }, []);
  const theme = preference === 'system' ? (systemDark ? 'theme-forge' : 'theme-daylight') : preference;
  useEffect(() => {
    const root = document.documentElement;
    [...root.classList].filter(name => name.startsWith('theme-')).forEach(name => root.classList.remove(name));
    root.classList.add(theme);
    root.style.colorScheme = theme === 'theme-daylight' ? 'light' : 'dark';
    root.dataset.appearance = preference;
  }, [theme, preference]);
  const changeTheme = value => {
    if (!allowed.test(value)) return;
    setPreference(value);
    try { localStorage.setItem('decad-theme', value); } catch {}
  };
  return {theme, preference, changeTheme};
}
