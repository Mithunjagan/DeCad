# DeCad Studio UI

The UI uses a graphite and copper default palette, a paper light palette, shared surface tokens, original SVG circuit artwork, and system fonts. The artwork on the welcome and empty screens is labelled as an illustration. Project previews continue to show the actual native schematic.

## Interaction model

- Desktop: project navigation, circuit workspace, and assistant appear together. Focus mode expands the canvas.
- At 900px and below: Projects, Workspace, and Assistant become separate full-height views. Each panel keeps its own scroll area.
- Ctrl+K or Cmd+K opens searchable commands, project switching, themes, export setup, and version-control actions. Arrow keys select; Enter runs; Escape closes.
- The assistant offers editable starter prompts and collapsible import settings. Requests retain existing review requirements.
- Project and preview loading have visible states and retry actions. Responses for a previously selected project cannot overwrite the newly selected project's details.
- Theme selection persists locally. Reduced-motion preferences disable decorative animation and smooth message scrolling.
- Dialogs trap keyboard focus, restore focus on close, and reject dismissal while busy. Phone component-review tables become stacked editable cards.
- Repository opens an existing linked repository. Git Push is the explicit publishing action.

## Verification

Run `npm run build` and `npm test` in this directory.

The optional browser suite is `npm run test:ui`. It requires Playwright, an installed browser, a running frontend, and the local backend. `PLAYWRIGHT_MODULE` can point to an existing Playwright package, `UI_BASE_URL` selects the frontend origin (default `http://127.0.0.1:3100`), and `UI_BROWSER_CHANNEL=chrome` selects installed Chrome.

The browser suite checks:

- Welcome layouts at 320, 360, 390, 768, 1024, and 1440px.
- Workspace layouts at 320, 360, 390, 768, 900, 1024, 1280, 1440, and 1920px.
- Header button bounds, assistant settings bounds, mobile navigation, command search, project dialog dismissal, focus mode, prompt presets, light-theme persistence, and view tabs.
- Circuit-review confirmation gating using an intercepted recognition response; no circuit is applied.
- PCB export setup against the live graph, without submitting an export.
- GitHub connection dialog presentation, without submitting credentials.
- An empty workspace using an intercepted empty project list.

Screenshots are saved to `../evidence/studio-ui/`. Browser checks open a local session and read existing projects; they do not validate live model inference, external GitHub publishing, native application launches, or exported circuit correctness. Those services retain their existing validation requirements.
