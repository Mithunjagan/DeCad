import './globals.css';
import './studio.css';
import './appearance.css';

export const metadata = {
  title: 'DeCad — Circuit Workbench',
  description: 'AI-assisted schematic capture & circuit workbench with native KiCad validation and Specctra DSN routing.',
  authors: [{ name: 'Raghav Krishna', url: 'https://github.com/JRK14' }],
  creator: 'Raghav Krishna (JRK)',
  applicationName: 'DeCad',
};

export const viewport = {themeColor:[{media:'(prefers-color-scheme: light)',color:'#faf9f6'},{media:'(prefers-color-scheme: dark)',color:'#171819'}]};

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{__html:`(()=>{try{let p=localStorage.getItem('decad-theme');if(!/^(system|theme-(forge|nebula|phosphor|neon|daylight|cyberpunk|monokai|obsidian|blueprint|solarized))$/.test(p))p='system';const t=p==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'theme-forge':'theme-daylight'):p;document.documentElement.classList.add(t);document.documentElement.style.colorScheme=t==='theme-daylight'?'light':'dark';}catch{}})();`}}/></head>
      <body>{children}</body>
    </html>
  );
}
