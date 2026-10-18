// Web app manifest: lets Edge/Chrome install DeCad as its own window (Install app / Apps menu).
export default function manifest() {
  return {
    name: 'DeCad — Circuit Workbench',
    short_name: 'DeCad',
    description: 'Schematic image or PDF to verified native OrCAD Capture design.',
    id: '/',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    background_color: '#090c10',
    theme_color: '#090c10',
    icons: [
      { src: '/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
    ],
  };
}
