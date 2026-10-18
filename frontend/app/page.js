'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {Brand, Icon, WelcomeScreen, EmptyCanvas} from './StudioElements';
import CommandPalette from './CommandPalette';
import WorkbenchDialog from './WorkbenchDialog';
import IntegrationsPanel from './IntegrationsPanel';
import CircuitReview from './CircuitReview';
import OrcadResult from './OrcadResult';
import BoardExport from './BoardExport';
import LibraryPanel from './LibraryPanel';
import KicadView from './KicadView';
import NativeKiCadPane from './NativeKiCadPane';
import useAppearance from './useAppearance';
import AssistantActivity from './AssistantActivity';
import SystemMonitor from './SystemMonitor';
import NetsView from './NetsView';
import {resolveChatRequest,requestErrorSummary} from './chat-request.mjs';
import {ocrRuntimeLabel} from './ocr-runtime.mjs';

const API = process.env.NEXT_PUBLIC_API_URL || '/api';
const KICAD_URL = process.env.NEXT_PUBLIC_KICAD_URL || 'http://localhost:6180/embedded.html';

const f = async (path, opts = {}) => {
  const response = await fetch(API + path, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: `Request failed (${response.status})` }));
    throw new Error(typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail));
  }
  return response;
};

export default function Page() {
  const [user, setUser] = useState(null);
  const [checked, setChecked] = useState(false);
  const [projects, setProjects] = useState([]);
  const [pid, setPid] = useState(null);
  const [projectData, setProjectData] = useState(null);
  const [projectError, setProjectError] = useState('');
  const [previewLoading, setPreviewLoading] = useState(true);
  const [previewError, setPreviewError] = useState(false);
  const currentProject = useRef(pid); currentProject.current = pid;
  const [files, setFiles] = useState([]);
  const [tab, setTab] = useState('schematic'); // 'schematic', 'source', 'bom', 'nets', 'checks', 'history'
  const [rev, setRev] = useState(0);
  const [sourceCode, setSourceCode] = useState('');
  const [sourceDirty, setSourceDirty] = useState(false);
  const [sourceHash, setSourceHash] = useState(null);
  const [git, setGit] = useState({ created: null, modified: null, dirty: false, repo: null });
  const [cfg, setCfg] = useState({ github: false });
  const [dlg, setDlg] = useState({ open: false, name: '', error: '', busy: false });
  const [deleteDlg, setDeleteDlg] = useState(null);
  const [deletedProject, setDeletedProject] = useState(null);
  const [restoring, setRestoring] = useState(false);
  const [status, setStatus] = useState('Ready');
  const [selectedFile, setSelectedFile] = useState(null);
  const [downloadMenu, setDownloadMenu] = useState(false);
  const [gitPushMenu, setGitPushMenu] = useState(false);
  const [userMenu, setUserMenu] = useState(false);
  const {theme, preference:themePreference, changeTheme} = useAppearance();
  const [pipelineStages, setPipelineStages] = useState(null);
  const [simData, setSimData] = useState(null);
  const [simError, setSimError] = useState('');
  const scopeScale=useMemo(()=>{const rows=simData?.data||[];const values=rows.flatMap(p=>[p.vin,p.vout]);const low=Math.min(0,...values);const high=Math.max(1e-9,...values);const start=rows[0]?.t_us||0;return {low,range:Math.max(1e-9,high-low),start,span:Math.max(1e-9,(rows.at(-1)?.t_us||0)-start)};},[simData]);
  const [health, setHealth] = useState(null);
  const [vision, setVision] = useState({ready:false});
  const [proposal, setProposal] = useState(null);
  const [proposalSource, setProposalSource] = useState(null);
  const [boardGraph, setBoardGraph] = useState(null);
  const [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState('design');
  const [simStep, setSimStep] = useState('10u');
  const [simStop, setSimStop] = useState('10m');
  const waveformInput=useRef(null);
  const importWaveform=async event=>{
    const file=event.target.files?.[0];if(!file||!pid)return;
    try {setStatus('Reading simulator waveform...');const r=await f(`/projects/${pid}/waveforms/import?name=${encodeURIComponent(file.name)}`,{method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'}});setSimData(await r.json());setSimError('');setStatus('External waveform imported');}
    catch(e){setSimError(e.message);setStatus(e.message);}finally{event.target.value='';}
  };
  useEffect(() => { f('/health').then(r => r.json()).then(setHealth).catch(e => setStatus(e.message)); f('/vision/status').then(r=>r.json()).then(setVision).catch(()=>{}); }, []);
  useEffect(()=>{
    if(!busy||activity!=='recognize')return;
    let stopped=false;
    const update=()=>f('/vision/status').then(r=>r.json()).then(data=>{if(!stopped)setVision(data);}).catch(()=>{});
    update();const timer=setInterval(update,4000);
    return ()=>{stopped=true;clearInterval(timer);};
  },[busy,activity]);

  const loadSimulation = async (engine = 'ngspice') => {
    if (!pid) return;
    setStatus('Running simulation...'); setSimError(''); setSimData(null);
    try {
      const route=engine==='qucs-s'?`/projects/${pid}/integrations/qucs-s/simulate`:`/projects/${pid}/simulate`;
      const res = await f(`${route}?step=${encodeURIComponent(simStep)}&stop=${encodeURIComponent(simStop)}`);
      setSimData(await res.json()); setStatus('Simulation completed');
    } catch (e) { setSimError(e.message); setStatus(e.message); }
  };
  const kicadControl = async (action) => {
    if (!pid) return;
    try {
    if(window.__DECAD_DESKTOP__&&editorMode==='native'){
      await window.__DECAD_DESKTOP__.request('control',{command:action});setStatus(`KiCad: ${action}`);return;
    }
    if(editorMode==='kicad'){
      if(action==='zoom_fit'||action==='redraw')await refresh();
      else if(action==='zoom_in'||action==='zoom_out')setStatus('KiCad view: Ctrl + scroll to zoom, scroll or drag to pan, click a part to inspect it');
      else if(action==='grid')setStatus('Grid controls are available in the KiCad editor');
      else if(action==='save')setStatus('Project is saved locally. Use Source to edit the schematic text.');
      else {await f(`/projects/${pid}/control?action=${action}`,{method:'POST'});await refresh();}
      return;
    }
    if(editorMode==='preview'){
      if(action==='zoom_in')setPreviewZoom(z=>Math.min(4,z*1.25));
      else if(action==='zoom_out')setPreviewZoom(z=>Math.max(.5,z/1.25));
      else if(action==='zoom_fit')setPreviewZoom(1);
      else if(action==='redraw')await refresh();
      else if(action==='save')setStatus('Schematic changes are saved automatically');
      else if(action==='grid')setStatus('Grid controls are available in the KiCad editor');
      else {await f(`/projects/${pid}/control?action=${action}`,{method:'POST'});await refresh();}
      return;
    }
    await f(`/projects/${pid}/control?action=${action}`, { method: 'POST' }); setStatus(`KiCad: ${action}`); await refresh(); }
    catch (e) { setStatus(e.message); }
  };
  const openNative = async () => {
    if (!pid) return;
    try {
      if(window.__DECAD_DESKTOP__){setEditorMode('native');setTab('schematic');setStatus('Native KiCad editor');return;}
      const r = await f(`/projects/${pid}/${health?.native_desktop&&!health?.embedded?'desktop':'open-native'}`, { method: 'POST' });
      setStatus((await r.json()).status); if(health?.embedded)setEditorMode('embedded');
    }
    catch (e) { setStatus(e.message); }
  };
  const saveSource = async () => {
    const name = selectedFile || files.find(n => n.endsWith('.kicad_sch'));
    try { await f(`/projects/${pid}/file?name=${encodeURIComponent(name)}`, {method: 'PUT', body: JSON.stringify({content: sourceCode,expected_sha256:sourceHash})}); setSourceDirty(false); await refresh(); setStatus('Source saved and parsed by KiCad'); }
    catch (e) { setStatus(e.message); }
  };
  const applyProposal = async (circuit) => {
    try { setActivity('apply');setBusy(true); const result=await (await f(`/projects/${pid}/import`, {method:'POST',body:JSON.stringify({circuit,output_tool:outputTool})})).json(); setProposal(null); setEditorMode('kicad'); await refresh(); setStatus('Reviewed import applied'); if(result.output?.ready)await downloadServer(result.output.url,result.output.filename); else if(result.output?.error)setStatus(result.output.error); }
    catch (e) { setStatus(e.message); throw e; } finally {setBusy(false);}
  };
  // Reviewed recognition -> native OrCAD design, verified by reopening it in Capture's database.
  const generateOrcad = async (circuit) => {
    try {
      setActivity('export');setBusy(true); setStatus('Generating the OrCAD design and verifying it in Capture…');
      const r=await f(`/projects/${pid}/export/orcad-dsn`,{method:'POST',body:JSON.stringify({circuit})});
      triggerDownload(await r.blob(),`${pid}-orcad-dsn.zip`,'application/zip');
      setStatus(`OrCAD .DSN verified (${r.headers.get('x-verification')||'connectivity checked'}) and saved in the project's orcad folder.`);
      setProposal(null); setOrcadResult(true);
      await refresh();
    } catch (e) { setStatus(e.message); throw e; } finally { setBusy(false); }
  };
  const commitLocal = async () => {
    if (!pid) return;
    try { const r = await f(`/projects/${pid}/git/commit`, {method:'POST',body:JSON.stringify({message:'Update circuit schematic'})}); const j=await r.json(); setStatus(j.committed ? `Committed ${j.hash}` : 'No changes to commit'); await refresh(); }
    catch (e) { setStatus(e.message); }
  };
  const planWithModel = async () => {
    if (!input.trim() || !pid || busy) return;
    setActivity('plan');setBusy(true);setStatus('Planning with the local model...');
    try {const j=await (await f('/ai/plan',{method:'POST',body:JSON.stringify({project:pid,message:input})})).json();setProposal(j.proposal);setProposalSource(null);setStatus(`Review ${j.inference.model} proposal`);}
    catch(e){setStatus(e.message);setMsgs(m=>[...m,{text:e.message,error:true}]);}finally{setBusy(false);}
  };

  const [commandOpen, setCommandOpen] = useState(false);
  const [mobileView, setMobileView] = useState('canvas');
  const [focusMode, setFocusMode] = useState(false);
  const [projectQuery, setProjectQuery] = useState('');
  const [openingWorkspace, setOpeningWorkspace] = useState(false);
  useEffect(() => {
    const key = event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {event.preventDefault(); setCommandOpen(open => !open);}
      if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('[role=button]') && !event.defaultPrevented) {event.preventDefault();event.target.click();}
      if (event.key === 'Escape') {setDownloadMenu(false);setUserMenu(false);setGitPushMenu(false);setModalImage(null);}
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, []);

  // Assistant & Real-time MCP Chat
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState('');
  const [attachedFiles, setAttachedFiles] = useState([]);
  const [recognitionMode,setRecognitionMode]=useState('auto');
  const [orcadResult,setOrcadResult]=useState(false);
  const recognitionChoiceMade=useRef(false);
  useEffect(()=>{if(!recognitionChoiceMade.current&&vision?.mode==='vision'&&vision?.ready)setRecognitionMode('vision');},[vision?.mode,vision?.ready]);
  const [outputTool,setOutputTool]=useState('kicad');
  const [uploading,setUploading]=useState(false);
  const submissionLock=useRef(false);
  const [editorMode,setEditorMode]=useState('kicad');
  const [desktopAvailable,setDesktopAvailable]=useState(false);
  useEffect(()=>{if(window.__DECAD_DESKTOP__){setDesktopAvailable(true);setEditorMode('native');}},[]);
  const [previewZoom,setPreviewZoom]=useState(1);
  const pendingMessage=useRef(null);
  const chatEnd = useRef(null);
  const assistantInputRef = useRef(null);
  const fileInputRef = useRef(null);
  const [showTokenModal, setShowTokenModal] = useState(false);
  const [githubTokenInput, setGithubTokenInput] = useState('');
  const [modalImage, setModalImage] = useState(null);

  // On mount check session
  useEffect(() => {
    f('/auth/config').then(r => r.json()).then(setCfg).catch(() => {});
    (async()=>{if(window.__DECAD_DESKTOP__?.local)await f('/auth/dev');return f('/auth/me');})().then(async r => {
      if (r.ok) {
        setUser(await r.json());
      }
      setChecked(true);
    }).catch(() => setChecked(true));
  }, []);

  const handleLogout = async () => {
    if(sourceDirty){setStatus('Save or discard source edits before signing out');return;}
    try {
      await releaseNative();
      await f('/auth/logout', { method: 'POST' });
    } catch (e) {
      setStatus(e.message);return;
    }
    setUser(null);
    setUserMenu(false);
    setPid(null);
    setProjects([]);
    setProjectData(null);
    setFiles([]);
    setMsgs([]);
    setAttachedFiles([]);
    setInput('');
    setStatus('Ready');
    // Ensure URL has no trailing query or hash
    if (typeof window !== 'undefined' && window.location.search) {
      window.history.replaceState({}, '', '/');
    }
  };

  const handleGitHubLogin = () => {
    if (cfg.github) {
      window.location.href = `${API}/auth/login`;
    } else {
      setShowTokenModal(true);
    }
  };

  const handleTokenSubmit = async (e) => {
    e?.preventDefault();
    const token = githubTokenInput.trim();
    if (!token) {
      setStatus('Please enter your GitHub Personal Access Token.');
      return;
    }
    setStatus('Verifying your GitHub credentials...');
    try {
      const res = await f('/auth/github-token', {
        method: 'POST',
        body: JSON.stringify({ token })
      });
      const data = await res.json();
      if (data.ok) {
        setUser(data.user);
        setShowTokenModal(false);
        setGithubTokenInput('');
        setStatus(`Successfully linked @${data.user.login}`);
      }
    } catch (err) {
      setStatus(err.message || 'Failed to authenticate token with GitHub');
    }
  };

  // Load projects list
  const loadProjects = useCallback(async () => {
    const r = await f('/projects');
    if (r.ok) {
      const list = await r.json();
      setProjects(list);
      setPid(active=>list.includes(active)?active:(list.includes(window.__DECAD_DESKTOP__?.project)?window.__DECAD_DESKTOP__.project:(list[0]||null)));
    }
  }, [pid]);

  useEffect(() => {
    if (user) loadProjects().catch(e => setStatus(e.message));
  }, [user, loadProjects]);

  // Refresh active project state
  const refresh = useCallback(async () => {
    if (!pid) return;
    setProjectError('');
    setRev(x => x + 1);
    try {
      const [nextFiles, nextGit, nextDetails] = await Promise.all([
        f(`/projects/${pid}/files`).then(r=>r.json()),
        f(`/projects/${pid}/git/status`).then(r=>r.json()),
        f(`/projects/${pid}/details`).then(r=>r.json())
      ]);
      if(currentProject.current!==pid)return;
      setFiles(nextFiles);setGit(nextGit);setProjectData(nextDetails);
    } catch (e) {
      if(currentProject.current===pid){setProjectError(e.message);setStatus(e.message);}
    }
  }, [pid]);

  // Real-time EventSource listener & KiCad container project activation
  useEffect(() => {
    if (pid) {
      setProjectData(null); setPreviewLoading(true); setPreviewError(false); setSimData(null); setProposal(null); setSelectedFile(null); setMsgs(pendingMessage.current?[pendingMessage.current]:[]);pendingMessage.current=null;setSourceDirty(false);setSourceHash(null);
      refresh();
      // Inform live KiCad container to open this specific project

      const es = new EventSource(`${API}/projects/${pid}/events`, { withCredentials: true });
      es.addEventListener('changed', () => {
        setStatus('Syncing changes...');
        refresh().then(() => setStatus('Synced'));
      });
      es.addEventListener('deleted',()=>{
        if(currentProject.current!==pid)return;
        currentProject.current=null;setPid(null);setProjectData(null);setFiles([]);setProposal(null);
        loadProjects().catch(e=>setStatus(e.message));setStatus('Project moved to trash in another window.');
      });
      return () => es.close();
    }
  }, [pid, refresh]);

  useEffect(() => {
    if(pid && health?.embedded && editorMode==='embedded')
      f(`/projects/${pid}/activate`,{method:'POST'}).catch(e=>{setStatus(e.message);setEditorMode('preview');});
  },[pid,health?.embedded,editorMode]);

  // Tab data fetchers
  useEffect(() => {
    if (!pid) return;
    if (tab === 'source' && !sourceDirty) {
      const schName = selectedFile || files.find(n => n.endsWith('.kicad_sch')) || `${pid}.kicad_sch`;
      f(`/projects/${pid}/file?name=${encodeURIComponent(schName)}`).then(async r => {setSourceHash(r.headers.get('x-content-sha256'));setSourceCode(await r.text());}).catch(e => setStatus(e.message));
    }
  }, [tab, pid, files, rev, selectedFile, sourceDirty]);

  useEffect(() => {
    if (msgs.length) chatEnd.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block:'nearest' });
    else chatEnd.current?.parentElement?.scrollTo({top:0});
  }, [msgs,busy,uploading,vision.runtime?.stage,vision.runtime?.state]);

  // Focus cursor into assistant input
  const focusAssistant = (prefill = '') => {
    setMobileView('assistant');
    setFocusMode(false);
    if (prefill) setInput(prefill);
    setTimeout(() => {
      assistantInputRef.current?.focus();
    }, 50);
  };

  // Upload canonical server filenames, then recognize actual attached bytes.
  const handleFileUpload = async (event) => {
    const element=event.currentTarget,files=Array.from(element.files||[]);element.value='';
    if(!files.length)return;
    if(files.length>10){setStatus('Choose at most 10 files per import.');return;}
    if(!pid){setStatus('Create or select a project before importing a file.');return;}
    if(submissionLock.current||uploading){setStatus('Wait for the current request to finish.');return;}
    setActivity('upload');setUploading(true);setStatus('Uploading schematic…');
    const names=[];
    try {
      for(const file of files.slice(0,10)) {
        try {
          const response=await f(`/projects/${pid}/attachments?name=${encodeURIComponent(file.name)}`,{method:'POST',body:file,headers:{'Content-Type':file.type||'application/octet-stream'}});
          const uploaded=await response.json();names.push(uploaded.path.replace(/^references\//,''));
        }catch(error){setStatus(error.message);setMsgs(m=>[...m,{text:`Upload failed for ${file.name}: ${error.message}`,error:true}]);}
      }
      if(names.length)await sendPrompt(input.trim()||'Analyze the attached schematic and create a design',names);
    }finally{setUploading(false);}
  };

  const sendPrompt = async (textToSend, overrideAttachments = null) => {
    let text,curAttached;
    try{const request=resolveChatRequest(textToSend||input,overrideAttachments||attachedFiles,files);text=request.text;curAttached=request.attachments;}
    catch(error){setStatus(error.message);setMsgs(m=>[...m,{text:error.message,error:true}]);return;}
    if(!text){setStatus('Enter a circuit request or attach a schematic.');return;}
    if(!pid){setStatus('Create or select a project first.');return;}
    if(submissionLock.current || (uploading && overrideAttachments===null)){setStatus('Your request is still running.');return;}
    submissionLock.current=true;setActivity(curAttached.length?'recognize':'design');setBusy(true);setInput('');setAttachedFiles([]);
    setMsgs(m=>[...m,{me:true,text,attachments:curAttached}]);
    setStatus(curAttached.length?'Recognizing schematic components and connections…':'Creating design…');
    try {
      const result=await (await f('/ai/chat',{method:'POST',body:JSON.stringify({project:pid,message:text,recognition_mode:recognitionMode,output_tool:outputTool,create_new_on_conflict:true,attachments:curAttached.map(name=>`references/${name}`)})})).json();
      if(result.proposal){setProposal(result.proposal);setProposalSource(curAttached.length?{name:curAttached[0],path:`/projects/${pid}/file?name=${encodeURIComponent('references/'+curAttached[0])}`}:null);}
      if(result.stages)setPipelineStages(result.stages);
      const message={text:result.reply,route:result.route,output:result.output,attachments:curAttached,proposal:result.proposal};
      if(result.project&&result.project!==pid){pendingMessage.current=message;await loadProjects();setPid(result.project);}
      else {setMsgs(m=>[...m,message]);await refresh();}
      setEditorMode('kicad');setStatus(result.proposal?'Review the recognized circuit to create the schematic':result.output?.error||(result.edits?.length?'Design ready':'Request completed'));
      if(result.output?.ready)await downloadServer(result.output.url,result.output.filename);
    }catch(error){setStatus(requestErrorSummary(error.message));setInput(text);setAttachedFiles(curAttached);setMsgs(m=>[...m,{text:error.message,error:true,retry:{text,attachments:curAttached,project:pid}}]);}
    finally{submissionLock.current=false;setBusy(false);}
  };

  const pushGit = async () => {
    if (!pid) return;
    setStatus('Pushing to GitHub...');
    try { const r = await f(`/projects/${pid}/git/push`, {method:'POST',body:JSON.stringify({message:'Update circuit schematic'})}); const j=await r.json(); setStatus(`Pushed to ${j.repo}`); await refresh(); }
    catch (e) { setStatus(e.message); }
  };

  // Generic file downloader helper
  const triggerDownload = (content, filename, mimeType = 'text/plain') => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setDownloadMenu(false);
  };

  const downloadServer = async (path, filename) => {
    try { const r=await f(path); triggerDownload(await r.blob(),filename,r.headers.get('content-type') || 'application/octet-stream'); setStatus(`Downloaded ${filename}`); }
    catch (e) {setStatus(e.message);}
  };
  const handleTabDownload = async (format) => {
    if (!pid) return;
    if (format === 'specctra') {
      try {setDownloadMenu(false);setBoardGraph(await (await f(`/projects/${pid}/graph`)).json());}
      catch(e){setStatus(e.message);}
      return;
    }
    if (format === 'circuit_json') return downloadServer(`/projects/${pid}/graph`,`${pid}-circuit.json`);
    if (format === 'spice') return downloadServer(`/projects/${pid}/export/spice`,`${pid}.cir`);
    if (format === 'orcad-handoff') return downloadServer(`/projects/${pid}/export/orcad-bundle`,`${pid}-orcad-handoff.zip`);
    if (format === 'orcad-dsn') return downloadServer(`/projects/${pid}/export/orcad-dsn`,`${pid}-orcad-dsn.zip`);
    if (format === 'edif') return downloadServer(`/projects/${pid}/export/edif`,`${pid}.edf`);
    if (format === 'svg') return downloadServer(`/projects/${pid}/preview.svg`,`${pid}.svg`);
    if (format === 'sch') return downloadServer(`/projects/${pid}/file?name=${encodeURIComponent(files.find(n=>n.endsWith('.kicad_sch')) || pid+'.kicad_sch')}`,`${pid}.kicad_sch`);
    if (format === 'project-zip') return downloadServer(`/projects/${pid}/export/project-zip`,`${pid}-complete-project.zip`);
    if (format === 'xml') return downloadServer(`/projects/${pid}/netlist`,`${pid}-netlist.xml`);
    if (tab === 'source') return triggerDownload(sourceCode,`${pid}.${format==='txt'?'txt':'kicad_sch'}`);
    if (tab === 'bom' && format === 'csv') {
      const rows=[['Reference','Value','Footprint','LCSC Part','Unit Price','Stock'],...componentsList.map(c=>[c.ref,c.value,c.footprint,c.lcsc,c.unitPrice,c.stock])];
      return triggerDownload(rows.map(row=>row.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n'),`${pid}-bom.csv`,'text/csv');
    }
    const data=tab==='bom'?componentsList:tab==='nets'?netsList:tab==='checks'?projectData?.validation:tab==='history'?revisionsList:simData;
    triggerDownload(JSON.stringify(data,null,2),`${pid}-${tab}.json`,'application/json');
  };
  const releaseNative = async () => {if(window.__DECAD_DESKTOP__)await window.__DECAD_DESKTOP__.request('release');};
  const changeTab = async next => {
    if(next===tab)return true;
    try{await releaseNative();setTab(next);return true;}catch(error){setStatus(error.message);return false;}
  };
  const changeEditorMode = async next => {
    if(next===editorMode)return;
    try{await releaseNative();setEditorMode(next);}catch(error){setStatus(error.message);}
  };
  const openNewProjectDialog = () => {if(busy||uploading)setStatus('Wait for the current request to finish before creating a project.');else if(sourceDirty)setStatus('Save or discard source edits before creating a project.');else setDlg({open:true,name:'',error:'',busy:false});};
  const submitProject = async (e) => {
    e.preventDefault(); const name=dlg.name.trim(); setDlg(d=>({...d,busy:true}));
    try { await releaseNative();await f('/projects',{method:'POST',body:JSON.stringify({name})}); setDlg({open:false,name:'',error:'',busy:false}); await loadProjects(); setPid(name); }
    catch (e) {setDlg(d=>({...d,busy:false,error:e.message}));}
  };
  const requestDeleteProject = name => {
    if(busy||uploading){setStatus('Wait for the current request to finish before deleting a project.');return;}
    if(name===pid&&sourceDirty){setStatus('Save or discard source edits before deleting this project.');return;}
    setDeleteDlg({name,busy:false,error:''});
  };
  const confirmDeleteProject = async (force=false) => {
    if(!deleteDlg||deleteDlg.busy)return;
    const name=deleteDlg.name;setDeleteDlg(d=>({...d,busy:true,error:''}));
    try {
      if(name===pid)await releaseNative();
      const result=await (await f(`/projects/${encodeURIComponent(name)}${force?'?force=true':''}`,{method:'DELETE'})).json();
      setDeletedProject({name,receipt:result.receipt,retained:result.retained_original});setDeleteDlg(null);
      if(name===currentProject.current){
        currentProject.current=null;setPid(null);setProjectData(null);setFiles([]);
        setSelectedFile(null);setSourceCode('');setSourceDirty(false);setSourceHash(null);setProjectError('');
      }
      await loadProjects();setStatus(result.retained_original?`${name} removed. A verified copy is in trash; Windows still holds the original folder.`:`${name} moved to project trash. You can undo this.`);
    }catch(e){setDeleteDlg(d=>d?({...d,busy:false,error:e.message}):d);}
  };
  const undoProjectDelete = async () => {
    if(!deletedProject||restoring)return;setRestoring(true);
    try {
      const {name,receipt}=deletedProject;
      await f(`/projects/${encodeURIComponent(name)}/restore`,{method:'POST',body:JSON.stringify({receipt})});
      await loadProjects();if(!sourceDirty){await releaseNative();setPid(name);}setDeletedProject(null);setStatus(`${name} restored`);
    }catch(e){setStatus(e.message);}finally{setRestoring(false);}
  };

  const activeRevisionHash = projectData?.activeRevision || 'No revision';
  const componentsList = projectData?.components || [];
  const netsList = projectData?.nets || [];
  const checksList = projectData?.checks || [];
  const activeViewLabel=tab!=='schematic'?({nets:'Electrical netlist',bom:'Bill of materials',checks:'Electrical rule checks',source:'Schematic source',history:'Project history',library:'Component libraries',scope:'Waveform scope',integrations:'Applications & models'}[tab]||'Design workspace'):editorMode==='native'||editorMode==='embedded'?'Native KiCad editor':editorMode==='kicad'?'KiCad view':'Generated schematic preview';
  const revisionsList = projectData?.revisions || [];
  const diskFiles = projectData?.files || files.map(n => ({ name: n, size: null }));

  const fmtBytes = (bytes) => {
    if (!bytes || bytes < 1024) return `${bytes || 0} B`;
    return `${(bytes / 1024).toFixed(1)} KB`;
  };

  const openLocalWorkspace = async () => {
    setOpeningWorkspace(true);
    try {await f('/auth/dev'); setUser(await (await f('/auth/me')).json()); setStatus('Ready');}
    catch (error) {setStatus(error.message);} finally {setOpeningWorkspace(false);}
  };
  const selectProject = async project => {
    if(busy||uploading){setStatus('Wait for the current request to finish before changing projects.');return;}
    if (sourceDirty) {setStatus('Save or discard source edits before changing projects.');return;}
    if(project===pid)return;
    try{await releaseNative();setPid(project);setMobileView('canvas');}catch(error){setStatus(error.message);}
  };
  const commands = [
    {label:'Create a new project', group:'Workspace', icon:'plus', run:openNewProjectDialog},
    {label:'Import a schematic', group:'Workspace', icon:'upload', run:()=>fileInputRef.current?.click()},
    {label:'Commit project locally',group:'Version control',run:commitLocal},
    {label:'Push project to GitHub',group:'Version control',run:pushGit},
    {label:'Open native KiCad editor',group:'Design tools',icon:'circuit',run:openNative},
    {label:'PCB and Specctra export',group:'Design tools',run:()=>handleTabDownload('specctra')},
    {label:'Focus the assistant', group:'Workspace', icon:'spark', run:()=>focusAssistant()},
    {label:focusMode?'Show side panels':'Focus canvas', group:'Workspace', icon:'panels', run:()=>setFocusMode(v=>!v)},
    ...['schematic','source','bom','nets','checks','history','scope','integrations'].map(view=>({label:({bom:'Bill of materials',scope:'Waveform scope',integrations:'Applications & models'})[view] || view[0].toUpperCase()+view.slice(1),group:'Views',run:async()=>{if(await changeTab(view)){setMobileView('canvas');if(view==='scope')loadSimulation();}}})),
    ...[['system','Follow system'],['theme-forge','Copper dark'],['theme-daylight','Paper light'],['theme-nebula','Nebula'],['theme-blueprint','Blueprint']].map(([value,label])=>({label:`Switch theme: ${label}`,group:'Appearance',run:()=>changeTheme(value)})),
    ...projects.map(project=>({label:project,group:'Projects',icon:'folder',run:()=>selectProject(project)}))
  ];
  if (!checked) return <div className="studio-loading"><Brand/><span className="loading-line"/><p>Preparing your studio…</p></div>;

  // HERO / LOGIN PAGE WHEN LOGGED OUT
  if (!user) {
    return (
      <div className="login-page">
        <WelcomeScreen localAvailable={cfg.local} onLocal={openLocalWorkspace} onGithub={handleGitHubLogin} busy={openingWorkspace} status={status}/>

        {/* Modal: Link User's Personal GitHub Account */}
        {showTokenModal && (
          <WorkbenchDialog title="Connect GitHub" onClose={()=>setShowTokenModal(false)}><div className="token-modal-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                    <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
                  </svg>
                  <span className="token-modal-title">Link Your GitHub Account</span>
                </div>
                <button 
                  onClick={() => setShowTokenModal(false)}
                  style={{ background: 'transparent', border: 'none', color: 'var(--muted)', cursor: 'pointer', padding: 4 }}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                </button>
              </div>

              <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.5, marginBottom: 16 }}>
                Paste your Personal Access Token (PAT). The app will verify it directly with GitHub and link to <strong>your personal username and repositories</strong>.
              </p>

              <form onSubmit={handleTokenSubmit}>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5, color: 'var(--muted)', marginBottom: 6 }}>
                    Personal Access Token (classic or fine-grained)
                  </label>
                  <input
                    type="password"
                    placeholder="ghp_... or github_pat_..."
                    value={githubTokenInput}
                    onChange={e => setGithubTokenInput(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      background: 'var(--panel2)',
                      border: '1px solid var(--line)',
                      borderRadius: 6,
                      color: 'var(--text)',
                      fontSize: 13,
                      fontFamily: 'var(--font-mono, monospace)',
                      outline: 'none',
                      boxSizing: 'border-box'
                    }}
                    autoFocus
                  />
                  <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 6, display: 'flex', justifyContent: 'space-between' }}>
                    <span>Requires <code>repo</code> scope for schematic sync.</span>
                    <a 
                      href="https://github.com/settings/tokens/new?scopes=repo&description=Schematic2SDN" 
                      target="_blank" 
                      rel="noreferrer"
                      style={{ color: 'var(--accent)', textDecoration: 'none' }}
                    >
                      Generate token ↗
                    </a>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                  <button
                    type="button"
                    onClick={() => setShowTokenModal(false)}
                    style={{
                      padding: '8px 16px',
                      background: 'transparent',
                      border: '1px solid var(--line)',
                      borderRadius: 6,
                      color: 'var(--muted)',
                      fontSize: 13,
                      cursor: 'pointer'
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    style={{
                      padding: '8px 18px',
                      background: '#238636',
                      border: '1px solid rgba(240, 246, 252, 0.1)',
                      borderRadius: 6,
                      color: '#fff',
                      fontSize: 13,
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                  >
                    Connect Account
                  </button>
                </div>
              </form>
            </div>
          </WorkbenchDialog>
        )}
      </div>
    );
  }

  // LOGGED-IN WORKBENCH VIEW
  return (
    <div className={`app ${theme} ${focusMode ? 'focus-mode' : ''}`} data-mobile-view={mobileView}>
      <a className="skip-link" href="#studio-canvas">Skip to workspace</a>
      {/* 1. TOP NAVBAR */}
      <header className="top-navbar">
        <div className="brand-section"><Brand/><span className="tag-label">STUDIO</span></div>

        <div className="project-breadcrumbs">
          <Icon name="folder" size={14}/><span>{pid || 'Your workspace'}</span>
          <span className="slash">/</span>
          <span className="rev-tag">rev {activeRevisionHash}</span>
        </div>

        {/* Workspace tools */}
        <div className="workspace-tools"><button className="command-trigger" onClick={()=>setCommandOpen(true)}><Icon name="search" size={15}/><span>Find anything…</span><kbd>Ctrl K</kbd></button>
          <div className="theme-pill-selector">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/><path d="M12 2a10 10 0 0 0 0 20v-20z"/>
            </svg>
            <span style={{ color: 'var(--muted)', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>Theme:</span>
            <select
              className="theme-select-dropdown" aria-label="Color theme"
              value={themePreference}
              onChange={(e) => changeTheme(e.target.value)}
              title="Follow your system appearance or choose a theme"
            >
              <option value="system">System · Auto</option>
              <option value="theme-forge">Copper · Dark</option>
              <option value="theme-nebula">Nebula (Deep Violet)</option>
              <option value="theme-phosphor">Phosphor (CRT Matrix)</option>
              <option value="theme-neon">Neon (Electric Cyber)</option>
              <option value="theme-daylight">Paper · Light</option>
              <option value="theme-cyberpunk">Cyberpunk (Yellow & Cyan)</option>
              <option value="theme-monokai">Monokai (Hacker Pro)</option>
              <option value="theme-obsidian">Obsidian (OLED Black)</option>
              <option value="theme-blueprint">Blueprint (Engineering)</option>
              <option value="theme-solarized">Solarized (Warm Slate)</option>
            </select>
          </div>
        </div>

        <div className="top-right-actions">
          <div className="engine-status-indicators">
            <div className="status-dot-label">
              <span className={health?.kicad ? "dot-green" : "dot-unavailable"} />
              <span>{health?.kicad ? 'KiCad ready' : 'KiCad unavailable'}</span>
            </div>
            <div className="status-dot-label">
              <span className={vision.ready ? "dot-accent" : "dot-unavailable"} />
              <span>{vision.mode==='auto'||vision.mode==='digital' ? `Automatic recognition · ${ocrRuntimeLabel(vision.runtime)}` : vision.mode==='circuit' ? (vision.ready?'CPU circuit recognition ready':'CPU recognition unavailable') : vision.mode==='ocr' ? (vision.ready?'OCR ready (text only)':'OCR unavailable') : (vision.ready?'Vision model installed':'Vision setup needed')}</span>
            </div>
          </div>

          {/* User Profile & Account Dropdown */}
          <div style={{ position: 'relative' }}>
            <button className="signin-btn-compact" aria-label="Account menu" aria-expanded={userMenu} onClick={() => setUserMenu(m => !m)}>
              <span className="dot-green" />
              <span>@{user?.login || user?.name || 'User'}</span>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M6 9l6 6 6-6"/>
              </svg>
            </button>

            {userMenu && (
              <div className="user-account-menu" onMouseLeave={() => setUserMenu(false)}>
                <div className="download-menu-header">Signed in as @{user?.login}</div>
                {user?.git_linked && (
                  <div role="button" tabIndex={0} className="user-menu-item" onClick={() => { setUserMenu(false); window.open(`https://github.com/${user.login}`, '_blank'); }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
                    </svg>
                    <span>View GitHub profile</span>
                  </div>
                )}
                <div role="button" tabIndex={0} className="user-menu-item" onClick={() => { setUserMenu(false); if(cfg.github) window.location.href = `${API}/auth/login?switch=true`; else setShowTokenModal(true); }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16"/>
                  </svg>
                  <span>{user?.git_linked ? 'Switch GitHub account' : 'Link GitHub account'}</span>
                </div>
                <div role="button" tabIndex={0} className="user-menu-item danger" onClick={handleLogout}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>
                  </svg>
                  <span>Log out session</span>
                </div>
              </div>
            )}
          </div>

          {/* Git Push & View Repo Split Menu */}
          <div style={{ position: 'relative' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {/* Open the linked repository */}
              <button
                className="signin-btn-compact"
                title={git.repo ? `Open GitHub repo: ${git.repo}` : 'View GitHub repository'}
                onClick={async () => {
                  if (git.repo) {
                    window.open(git.repo, '_blank');
                  } else if (user?.login && pid) {
                    setStatus('Use Git Push to publish this project and link a repository.');
                  } else {
                    setStatus('Sign in with GitHub to link repository');
                  }
                }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
                </svg>
                <span>Repository</span>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/>
                </svg>
              </button>

              <div style={{ display: 'flex', alignItems: 'center' }}>
                <button className="git-push-btn" onClick={pushGit} title="Push schematic commits to GitHub">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M12 19V5M5 12l7-7 7 7"/>
                  </svg>
                  <span>Git Push</span>
                </button>
                <button
                  className="git-push-btn"
                  style={{ borderLeft: '1px solid rgba(255,255,255,0.2)', paddingLeft: 6, paddingRight: 6 }}
                  onClick={() => setGitPushMenu(m => !m)}
                  title="Git options"
                >
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M6 9l6 6 6-6"/>
                  </svg>
                </button>
              </div>
            </div>

            {gitPushMenu && (
              <div className="user-account-menu" onMouseLeave={() => setGitPushMenu(false)}>
                <div className="download-menu-header">Git & GitHub Options</div>
                <div
                  role="button" tabIndex={0} className="user-menu-item"
                  onClick={() => {
                    setGitPushMenu(false);
                    if (git.repo) {
                      window.open(git.repo, '_blank');
                    } else if (user?.login && pid) {
                      window.open(`https://github.com/${user.login}/s2sdn-${pid}`, '_blank');
                    } else {
                      setStatus('Push to GitHub first to view repository');
                    }
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/>
                  </svg>
                  <span>View Repository {git.repo ? `(${git.repo.replace('https://github.com/', '')})` : '(open in GitHub)'}</span>
                </div>
                <div role="button" tabIndex={0} className="user-menu-item" onClick={() => { setGitPushMenu(false); pushGit(); }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 19V5M5 12l7-7 7 7"/>
                  </svg>
                  <span>Push latest changes</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      <nav className="mobile-workspace-nav" aria-label="Workspace panels">{[['projects','folder','Projects'],['canvas','circuit','Workspace'],['assistant','spark','Assistant']].map(([view,icon,label])=><button key={view} aria-pressed={mobileView===view} onClick={()=>{setMobileView(view);setFocusMode(false);}}><Icon name={icon} size={16}/>{label}</button>)}</nav>
      {/* 2. WORKBENCH 3-COLUMN BODY */}
      <div className="workbench-grid">
        {/* LEFT COLUMN: PROJECTS, REVISION FILES, LIBRARIES */}
        <aside className="left-nav-sidebar">
          <div className="sidebar-header-row">
            <span>Projects</span>
            <button className="sidebar-add-btn" onClick={openNewProjectDialog} title="New project">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 5v14M5 12h14"/>
              </svg>
            </button>
          </div>

          <label className="project-search"><Icon name="search" size={14}/><input aria-label="Filter projects" placeholder="Find a project…" value={projectQuery} onChange={e=>setProjectQuery(e.target.value)}/></label>
          <div className="projects-list">
            {projects.filter(p=>p.toLowerCase().includes(projectQuery.toLowerCase())).map(p => (
              <div key={p} className={`project-item-card ${p === pid ? 'active' : ''}`}>
                <button className="project-select" aria-current={p===pid ? 'true' : undefined}
                  onClick={()=>selectProject(p)} onDoubleClick={()=>{selectProject(p);setTab('schematic');}}
                  title={`Open ${p}`}>
                  <span className="project-title-name">{p}</span>
                  <span className="project-rev-label">rev {p === pid ? activeRevisionHash : 'origin'}</span>
                </button>
                <button className="project-delete" aria-label={`Delete project ${p}`} title={`Delete ${p}`}
                  disabled={busy||uploading||!!deleteDlg?.busy} onClick={()=>requestDeleteProject(p)}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/></svg>
                </button>
              </div>
            ))}
          </div>

          {!projects.length && <p className="sidebar-empty">Your ideas live here.<br/>Create a project to begin.</p>}
          {projects.length>0 && !projects.some(p=>p.toLowerCase().includes(projectQuery.toLowerCase())) && <p className="sidebar-empty">No matching projects.</p>}
          <div className="sidebar-subheading">
            <span>Project files</span>
            <span className="count-tag">{diskFiles.length}</span>
          </div>

          {/* Group 1: KICAD FILES */}
          <div className="file-group-label">KICAD</div>
          {diskFiles.filter(f => f.name.includes('.kicad_')).map(f => (
            <div key={f.name} role="button" tabIndex={0} className={`file-row ${selectedFile === f.name ? 'active' : ''}`} onClick={() => {if(sourceDirty)setStatus('Save or discard source edits before changing files.');else {setSelectedFile(f.name);changeTab('source');}}}>
              <span className="file-name-with-icon">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: 'var(--accent)' }}>
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6"/>
                </svg>
                {f.name}
              </span>
              <span className="file-size">{fmtBytes(f.size)}</span>
            </div>
          ))}

          {/* Group 2: ROUTING / SPECTRA DSN */}
          <div className="file-group-label">ROUTING / SPECTRA DSN</div>
          <div
            role="button" tabIndex={0} className="file-row"
            title="KiCad Specctra DSN autorouter file - click to download"
            onClick={async () => {
              if (!pid) return;
              try {
                setStatus('Exporting KiCad Specctra DSN...');
                const r = await f(`/projects/${pid}/export/specctra-dsn`);
                if (r.ok) {
                  const blob = await r.blob();
                  triggerDownload(blob, `${pid}.dsn`, 'text/plain');
                  setStatus(`Downloaded ${pid}.dsn (KiCad Specctra format)`);
                } else {
                  const err = await r.json().catch(() => ({ detail: 'Export error' }));
                  setStatus(err.detail || 'Failed to export DSN');
                }
              } catch (e) {
                setStatus(`DSN export failed: ${e.message}`);
              }
            }}
          >
            <span className="file-name-with-icon">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: '#3fb950' }}>
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6"/>
                <circle cx="10" cy="14" r="2"/>
                <path d="M12 14h4"/>
              </svg>
              {pid || 'board'}.dsn
            </span>
            <span className="file-size" style={{ color: '#3fb950', fontWeight: 600 }}>Specctra</span>
          </div>

          {/* Group 3: CHECKS */}
          <div className="file-group-label">CHECKS</div>
          <div role="button" tabIndex={0} className="file-row" onClick={() => changeTab('nets')}>
            <span className="file-name-with-icon">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: '#58a6ff' }}>
                <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
              </svg>
              netlist.xml
            </span>
            <span className="file-size">Export</span>
          </div>
          <div role="button" tabIndex={0} className="file-row" onClick={() => changeTab('checks')}>
            <span className="file-name-with-icon">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: '#58a6ff' }}>
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14M22 4L12 14.01l-3-3"/>
              </svg>
              validation.json
            </span>
            <span className="file-size">{projectData?.validation?.status !== 'completed' ? 'Not checked' : checksList.length ? `${checksList.length} items` : 'Clean'}</span>
          </div>

          {/* Group 4: DATA */}
          <div className="file-group-label">DATA</div>
          <div role="button" tabIndex={0} className="file-row" onClick={() => changeTab('bom')}>
            <span className="file-name-with-icon">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: '#bc8cff' }}>
                <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/>
              </svg>
              bom.csv
            </span>
            <span className="file-size">{componentsList.length} parts</span>
          </div>
          <div role="button" tabIndex={0} className="file-row" onClick={() => changeTab('source')}>
            <span className="file-name-with-icon">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: '#bc8cff' }}>
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6"/>
              </svg>
              circuit.json
            </span>
            <span className="file-size">schema</span>
          </div>

          {/* Group 4: LIBRARIES (Working Options) */}
          <div className="sidebar-subheading" style={{ marginTop: 'auto' }}>
            <span>Libraries</span>
          </div>
          
          {/* Option 1: Circuit Extraction from Text/Word/PDF/Image */}
          <button className="library-action-btn" title="Upload circuit from Text, Word (.docx), PDF, or Image" onClick={() => fileInputRef.current?.click()}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
            </svg>
            <span>Import circuit source (File/Text)</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".txt,.pdf,.docx,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.json,.csv,.cir,.spice,.net"
            style={{ display: 'none' }}
            onChange={handleFileUpload}
          />

          {/* Option 2: Place exact KiCad symbol - Places cursor in assistant */}
          <button className="library-action-btn" title="Place exact KiCad symbol & place cursor in assistant" onClick={() => focusAssistant('Place exact KiCad symbol with part number: ')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
            <span>Place exact KiCad symbol</span>
          </button>

          <button className="library-action-btn" onClick={() => window.open('https://www.lcsc.com', '_blank')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8"/>
            </svg>
            <span>Search supplier catalog</span>
          </button>
          <button className="library-action-btn" style={{ paddingBottom: 12 }} onClick={() => pushGit()}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/><path d="M18 15v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4"/>
            </svg>
            <span>Push project to GitHub</span>
          </button>
        </aside>

        {/* CENTER COLUMN: REAL WORKING KICAD WORKSPACE */}
        <section className="center-editor-container" id="studio-canvas" tabIndex={-1} aria-label="Circuit workspace">
          <div className="workspace-heading"><div><div className="eyebrow">DESIGN WORKSPACE</div><h1>{pid || 'Untitled possibilities'}{sourceDirty && <span className="unsaved-tag">Unsaved edits</span>}</h1><p>{componentsList.length} components <span>·</span> {netsList.length} nets <span>·</span> {projectData?.validation?.status==='completed' ? (checksList.length?`${checksList.length} ERC findings`:'ERC clear') : 'ERC not checked'}</p></div><button className="studio-secondary focus-toggle" aria-pressed={focusMode} onClick={()=>setFocusMode(v=>!v)} title="Toggle canvas focus"><Icon name="panels" size={16}/><span>{focusMode?'Show panels':'Focus'}</span></button></div>
          {/* Main Top Navigation Tabs */}
          <div className="editor-tabs-bar">
            <div className="tabs-group-left">
              <button className={`tab-btn ${tab === 'schematic' ? 'active' : ''}`} onClick={() => changeTab('schematic')}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
                <span>Schematic</span>
              </button>
              <button className={`tab-btn ${tab === 'source' ? 'active' : ''}`} onClick={() => changeTab('source')}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                <span>Source</span>
              </button>
              <button className={`tab-btn ${tab === 'bom' ? 'active' : ''}`} onClick={() => changeTab('bom')}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/></svg>
                <span>BOM</span> <span className="tab-badge">{componentsList.length}</span>
              </button>
              <button className={`tab-btn ${tab === 'nets' ? 'active' : ''}`} onClick={() => changeTab('nets')}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                <span>Nets</span> <span className="tab-badge">{netsList.length}</span>
              </button>
              <button className={`tab-btn ${tab === 'checks' ? 'active' : ''}`} onClick={() => changeTab('checks')}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14M22 4L12 14.01l-3-3"/></svg>
                <span>Checks</span> <span className={`tab-badge ${checksList.length ? 'badge-error' : ''}`}>{checksList.length}</span>
              </button>
              <button className={`tab-btn ${tab === 'history' ? 'active' : ''}`} onClick={() => changeTab('history')}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                <span>History</span> <span className="tab-badge">{revisionsList.length}</span>
              </button>
              <button className={`tab-btn ${tab === 'scope' ? 'active' : ''}`} onClick={async () => { if(await changeTab('scope'))loadSimulation(); }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                <span>Waveform Scope</span>
              </button>
              <button className={`tab-btn ${tab === 'library' ? 'active' : ''}`} onClick={() => changeTab('library')}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M4 19.5A2.5 2.5 0 0 0 6.5 22H20V2H6.5A2.5 2.5 0 0 0 4 4.5v15z"/></svg>
                <span>Libraries &amp; footprints</span>
              </button>
              <button className={`tab-btn ${tab === 'integrations' ? 'active' : ''}`} onClick={() => changeTab('integrations')}>Applications &amp; models</button>
            </div>

            <div className="tabs-actions-right">
              {/* DOWNLOAD DROPDOWN - Custom formats for the active tab */}
              <div style={{ position: 'relative' }}>
                <button
                  className="icon-action-btn" aria-expanded={downloadMenu}
                  title="Download in chosen format"
                  onClick={() => setDownloadMenu(m => !m)}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                  <span style={{ fontSize: 11 }}>Download</span>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 9l6 6 6-6"/></svg>
                </button>

                {downloadMenu && (
                  <div className="download-dropdown-menu" onMouseLeave={() => setDownloadMenu(false)}>
                    <div className="download-menu-header">Export {tab.toUpperCase()}</div>
                    {tab === 'schematic' && (
                      <>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('svg')}>
                          <span>Vector Graphic</span> <span className="download-ext-tag">.SVG</span>
                        </div>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('sch')}>
                          <span>KiCad Schematic</span> <span className="download-ext-tag">.KICAD_SCH</span>
                        </div>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('project-zip')}>
                          <span>Full Project Archive</span> <span className="download-ext-tag">.ZIP</span>
                        </div>
                      </>
                    )}
                    {tab === 'source' && (
                      <>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('kicad_sch')}>
                          <span>KiCad S-Expression</span> <span className="download-ext-tag">.KICAD_SCH</span>
                        </div>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('txt')}>
                          <span>Plain Text</span> <span className="download-ext-tag">.TXT</span>
                        </div>
                      </>
                    )}
                    {tab === 'bom' && (
                      <>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('csv')}>
                          <span>Spreadsheet / CSV</span> <span className="download-ext-tag">.CSV</span>
                        </div>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('json')}>
                          <span>JSON Structure</span> <span className="download-ext-tag">.JSON</span>
                        </div>
                      </>
                    )}
                    {tab === 'nets' && (
                      <>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('specctra')}>
                          <span>PCB autorouter Specctra DSN</span> <span className="download-ext-tag">.ZIP</span>
                        </div>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('orcad-dsn')}>
                          <span>OrCAD Capture native design (verified)</span> <span className="download-ext-tag">.DSN</span>
                        </div>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('orcad-handoff')}>
                          <span>OrCAD handoff (connectivity only)</span> <span className="download-ext-tag">.ZIP</span>
                        </div>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('edif')}>
                          <span>Connectivity EDIF (no schematic layout)</span> <span className="download-ext-tag">.EDF</span>
                        </div>

                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('spice')}>
                          <span>SPICE Simulation</span> <span className="download-ext-tag">.CIR</span>
                        </div>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('xml')}>
                          <span>KiCad XML Netlist</span> <span className="download-ext-tag">.XML</span>
                        </div>
                        <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('json')}>
                          <span>JSON Netlist</span> <span className="download-ext-tag">.JSON</span>
                        </div>
                      </>
                    )}
                    {tab === 'checks' && (
                      <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('json')}>
                        <span>ERC Violation Report</span> <span className="download-ext-tag">.JSON</span>
                      </div>
                    )}
                    {tab === 'history' && (
                      <div role="button" tabIndex={0} className="download-option-item" onClick={() => handleTabDownload('json')}>
                        <span>Git Log Timeline</span> <span className="download-ext-tag">.JSON</span>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <button className="icon-action-btn" title="Open KiCad editor" onClick={openNative}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
              </button>
            </div>
          </div>

          {/* Secondary schematic controls toolbar with SVG icons */}
          <div className={`schematic-secondary-toolbar ${editorMode==='native'?'has-native-editor':''}`} style={tab!=='schematic'?{display:'none'}:undefined}>
            <div className="toolbar-button-group">
              <button className="tool-btn" title="New file" onClick={openNewProjectDialog}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6"/></svg>
              </button>
              <button className="tool-btn" title="Save project" onClick={()=>sourceDirty?saveSource():kicadControl('save')}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2zM17 21v-8H7v8M7 3v5h8"/></svg>
              </button>
              <div className="toolbar-separator" />
              <button className="tool-btn" title="Refresh & Reload" onClick={() => { refresh(); kicadControl('redraw'); }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
              </button>
              <div className="toolbar-separator" />
              <button className="tool-btn" title="Zoom in (KiCad Canvas)" onClick={() => kicadControl('zoom_in')}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
              </button>
              <button className="tool-btn" title="Zoom out (KiCad Canvas)" onClick={() => kicadControl('zoom_out')}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
              </button>
              <button className="tool-btn" title="Zoom to fit schematic" onClick={() => kicadControl('zoom_fit')}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
              </button>
              <button className="tool-btn" title="Toggle grid" onClick={() => kicadControl('grid')}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
              </button>
              <div className="toolbar-separator" />
              <button
                className="tool-btn"
                title="Open KiCad editor"
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 8px', width: 'auto', background: 'var(--panel2)', border: '1px solid var(--accent-border)', color: 'var(--accent)', fontWeight: 600, fontSize: 11 }}
                onClick={openNative}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                <span>Edit in KiCad</span>
              </button>
            </div>

            <div className="toolbar-button-group">
              {desktopAvailable&&<button className={`tool-btn ${editorMode==='native'?'active':''}`} aria-pressed={editorMode==='native'} style={{width:'auto',padding:'0 8px'}} onClick={()=>changeEditorMode('native')}>KiCad editor</button>}
              <button className={`tool-btn ${editorMode==='kicad'?'active':''}`} aria-pressed={editorMode==='kicad'} style={{width:'auto',padding:'0 8px'}} onClick={()=>changeEditorMode('kicad')}>KiCad view</button>
              <button className={`tool-btn ${editorMode==='preview'?'active':''}`} aria-pressed={editorMode==='preview'} style={{width:'auto',padding:'0 8px'}} onClick={()=>changeEditorMode('preview')}>Preview</button>
              <span className="canvas-zoom-label">{Math.round(previewZoom*100)}% <span>·</span> Local workspace</span>
            </div>
          </div>

          {/* REAL KICAD EMBEDDED ENGINE (Live interactive components) */}
          {tab==='library'&&<LibraryPanel pid={pid} api={API} request={f} onStatus={setStatus} onProjectChanged={refresh} onOrcadReady={()=>{setOrcadResult(true);refresh();}}/>}
          {tab==='integrations'&&<IntegrationsPanel project={pid} request={f} download={downloadServer} onStatus={setStatus} onSimulate={engine=>{setTab('scope');loadSimulation(engine);}}/>}
          {tab === 'schematic' && (
            <div className="kicad-embed-wrapper">
              {pid && desktopAvailable && editorMode==='native' ? <NativeKiCadPane pid={pid} api={API} onError={setStatus}/> : pid && !projectData ? <div className="project-loading" role="status"><Icon name="circuit" size={30}/><span className="loading-line"/><p>{projectError || 'Opening your circuit…'}</p>{projectError && <button className="studio-secondary" onClick={refresh}>Retry loading</button>}</div> : (!pid || (projectData && componentsList.length===0 && editorMode!=='embedded')) ? <EmptyCanvas hasProject={!!pid} onCreate={openNewProjectDialog} onImport={()=>fileInputRef.current?.click()} onPrompt={focusAssistant}/> : pid ? (editorMode==='embedded'&&health?.embedded ? <iframe title="Native KiCad editor" src={KICAD_URL} style={{width:'100%',height:'100%',border:0}}/> : editorMode==='kicad' ? <KicadView pid={pid} name={files.find(n=>n.endsWith('.kicad_sch'))} api={API} rev={rev} onError={setStatus}/> : <div className="schematic-preview-scroll">{(previewLoading||previewError)&&<div className={`project-loading preview-loading ${previewError ? 'has-error' : ''}`} role="status"><Icon name="circuit" size={30}/><span className="loading-line"/><p>{previewError ? 'The schematic preview could not load.' : 'Rendering your schematic…'}</p>{previewError&&<button className="studio-secondary" onClick={()=>{setPreviewLoading(true);setPreviewError(false);setRev(v=>v+1);}}>Retry preview</button>}</div>}<img onLoad={()=>{setPreviewLoading(false);setPreviewError(false);}} alt={`${pid} generated schematic`} src={`${API}/projects/${pid}/preview.svg?v=${rev}`} style={{width:`${previewZoom*100}%`}} onError={()=>{setPreviewLoading(false);setPreviewError(true);setStatus('Schematic preview could not load. Check the project and retry.')}} /></div>) : <div style={{padding:40}}>Create or select a project to open its schematic.</div>}
            </div>
          )}

          {/* Option: Source Tab */}
          {tab === 'source' && (
            <div className="data-table-view">
              <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--muted)', fontSize: 12 }}>Exact KiCad S-Expression schematic source:</span>
                <div><button className="signin-btn-compact" onClick={() => navigator.clipboard.writeText(sourceCode).catch(e=>setStatus(e.message))}>Copy Code</button> <button className="signin-btn-compact" onClick={saveSource} disabled={!(selectedFile || files.find(n=>n.endsWith('.kicad_sch')) || '').endsWith('.kicad_sch')}>Save Source</button> <button className="signin-btn-compact" disabled={!sourceDirty} onClick={()=>setSourceDirty(false)}>Discard source edits</button></div>
              </div>
              {sourceDirty&&<p>Unsaved source edits — automatic refresh is paused for this buffer.</p>}
              <textarea aria-label="KiCad source" className="mono" value={sourceCode} onChange={e=>{setSourceCode(e.target.value);setSourceDirty(true);}} style={{width:'100%',minHeight:500,background:'var(--panel2)',color:'var(--text)',fontSize:12,border:'1px solid var(--line)',padding:16}} />
            </div>
          )}

          {/* Option: BOM Tab with Rupees (₹) and live source link */}
          {tab === 'bom' && (
            <div className="data-table-view">
              <div style={{ marginBottom: 14, color: 'var(--muted)', fontSize: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Bill of materials from the schematic. Use supplier search for current pricing and stock.</span>
                <button className="signin-btn-compact" onClick={() => handleTabDownload('csv')}>Export .CSV</button>
              </div>
              <table className="cf-table">
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Value</th>
                    <th>Footprint</th>
                    <th>LCSC Part</th>
                    <th>Unit Price (₹)</th>
                    <th>Availability</th>
                    <th>Supplier Source</th>
                  </tr>
                </thead>
                <tbody>
                  {componentsList.length === 0 ? (
                    <tr>
                      <td
                        colSpan="7"
                        style={{ textAlign: 'center', color: 'var(--muted)', padding: 36, cursor: 'pointer' }}
                        onClick={() => focusAssistant('Add resistor R1 with value 4.7k and resistor R2 with value 10k')}
                      >
                        <div>No components laid in schematic yet.</div>
                        <div style={{ color: 'var(--accent)', marginTop: 8, fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          <span>Click here to place components via Assistant</span>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    componentsList.map(c => (
                      <tr key={c.ref}>
                        <td className="mono" style={{ color: 'var(--accent)', fontWeight: 600 }}>{c.ref}</td>
                        <td>{c.value}</td>
                        <td className="mono">{c.footprint || 'Not assigned'}</td>
                        <td className="mono">{c.lcsc}</td>
                        <td style={{ fontWeight: 600, color: '#3fb950' }}>{c.unitPrice}</td>
                        <td>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                            <svg width="8" height="8" viewBox="0 0 24 24" fill="#3fb950"><circle cx="12" cy="12" r="10"/></svg>
                            <span>{c.stock}</span>
                          </span>
                        </td>
                        <td>
                          <a
                            href={c.supplierUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="external-link-btn"
                          >
                            <span>Check on {c.supplier}</span>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
                          </a>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 'nets' && <NetsView nets={netsList} onPrompt={focusAssistant}/>}

          {/* Option: Checks Tab - Real KiCad ERC checks */}
          {tab === 'checks' && (
            <div className="data-table-view">
              <div style={{ marginBottom: 14, color: 'var(--muted)', fontSize: 12 }}>
                KiCad Electrical Rules Check (ERC) violations run on the active schematic:
              </div>
              {checksList.length === 0 ? (
                <div style={{ padding: 32, textAlign: 'center', color: '#3fb950', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3fb950" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                  <span>{projectData?.validation?.status === 'completed' ? 'ERC completed: no reported violations.' : projectData?.validation?.error || 'ERC has not completed.'}</span>
                </div>
              ) : (
                checksList.map((v, i) => (
                  <div key={i} style={{ padding: '12px 14px', borderBottom: '1px solid var(--line)', background: 'var(--panel2)', marginBottom: 8, borderRadius: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <b style={{ color: v.severity === 'error' ? 'var(--err)' : 'var(--warn)', textTransform: 'uppercase', fontSize: 11 }}>
                        [{v.severity}]
                      </b>
                      <span className="mono" style={{ color: 'var(--muted)', fontSize: 11 }}>{v.type}</span>
                    </div>
                    <div style={{ color: '#f0f6fc', fontSize: 12 }}>{v.description}</div>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Option: History Tab */}
          {tab === 'history' && (
            <div className="data-table-view">
              <table className="cf-table">
                <thead>
                  <tr>
                    <th>Revision</th>
                    <th>Commit Message</th>
                    <th>Timestamp</th>
                    <th>Author</th>
                  </tr>
                </thead>
                <tbody>
                  {revisionsList.map((r, i) => (
                    <tr key={i}>
                      <td className="mono" style={{ color: 'var(--accent)' }}>{r.hash}</td>
                      <td>{r.msg}</td>
                      <td style={{ color: 'var(--muted)' }}>{r.time}</td>
                      <td>{r.author || 'User'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Option: Waveform Scope Tab - Real-time SPICE transient scope */}
          {tab === 'scope' && (
            <div className="data-table-view" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h4 style={{ margin: '0 0 4px 0', fontSize: 14, color: 'var(--text)' }}>
                    Circuit Transient Simulation
                  </h4>
                  <span style={{ color: 'var(--muted)', fontSize: 11 }}>
                    {simData ? `Solver: ${simData.solver} · ${simData.data.length} samples` : simError || 'Run a powered circuit to see measured node voltages.'}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input aria-label="Simulation step" value={simStep} onChange={e=>setSimStep(e.target.value)} style={{width:65}} /><input aria-label="Simulation stop" value={simStop} onChange={e=>setSimStop(e.target.value)} style={{width:65}} /><button className="signin-btn-compact" onClick={()=>loadSimulation()}>Run</button>
                  <button className="signin-btn-compact" onClick={() => handleTabDownload('spice')}>Export .CIR</button>
                  <input type="file" accept=".raw,.csv" ref={waveformInput} hidden onChange={importWaveform}/><button className="signin-btn-compact" onClick={()=>waveformInput.current?.click()}>Import simulator waveform</button>
                </div>
              </div>

              {/* Oscilloscope Screen */}
              <div style={{ background: '#05070a', border: '1px solid var(--line)', borderRadius: 8, padding: 16, height: 320, position: 'relative' }}>
                <svg width="100%" height="100%" viewBox="0 0 800 280" preserveAspectRatio="none">
                  {/* Grid Lines */}
                  {[50, 100, 150, 200, 250].map(y => (
                    <line key={y} x1="0" y1={y} x2="800" y2={y} stroke="rgba(255,255,255,0.08)" strokeDasharray="4 4" />
                  ))}
                  {[100, 200, 300, 400, 500, 600, 700].map(x => (
                    <line key={x} x1={x} y1="0" x2={x} y2="280" stroke="rgba(255,255,255,0.08)" strokeDasharray="4 4" />
                  ))}

                  {/* Vin trace (Yellow Square/Pulse) */}
                  {simData?.data && (
                    <path
                      d={simData.data.map((pt, i) => `${i === 0 ? 'M' : 'L'} ${((pt.t_us-scopeScale.start)/scopeScale.span)*780+10} ${250 - ((pt.vin-scopeScale.low)/scopeScale.range) * 180}`).join(' ')}
                      fill="none"
                      stroke="#fcee0a"
                      strokeWidth="2"
                    />
                  )}

                  {/* Vout trace (Cyan Exponential Response) */}
                  {simData?.data && (
                    <path
                      d={simData.data.map((pt, i) => `${i === 0 ? 'M' : 'L'} ${((pt.t_us-scopeScale.start)/scopeScale.span)*780+10} ${250 - ((pt.vout-scopeScale.low)/scopeScale.range) * 180}`).join(' ')}
                      fill="none"
                      stroke="#00f0ff"
                      strokeWidth="2.5"
                    />
                  )}
                </svg>

                {/* Legend */}
                <div style={{ position: 'absolute', top: 12, right: 16, display: 'flex', gap: 16, fontSize: 11, background: 'rgba(0,0,0,0.6)', padding: '4px 10px', borderRadius: 4 }}>
                  <span style={{ color: '#fcee0a' }}>● {simData?.display_signals?.vin || 'VIN / first node'}</span>
                  <span style={{ color: '#00f0ff' }}>● {simData?.display_signals?.vout || 'VOUT / last node'}</span>
                </div>
              </div>

              {/* Data Table Preview */}
              <div style={{ maxHeight: 180, overflow: 'auto', border: '1px solid var(--line)', borderRadius: 6 }}>
                <table className="cf-table">
                  <thead>
                    <tr>
                      <th>Time (µs)</th>
                      <th>Vin (V)</th>
                      <th>Vout (V)</th>
                      <th>Solver</th>
                    </tr>
                  </thead>
                  <tbody>
                    {simData?.data?.slice(0, 10).map((pt, i) => (
                      <tr key={i}>
                        <td className="mono">{pt.t_us}</td>
                        <td className="mono" style={{ color: '#fcee0a' }}>{pt.vin} V</td>
                        <td className="mono" style={{ color: '#00f0ff' }}>{pt.vout} V</td>
                        <td style={{ color: 'var(--muted)' }}>{simData?.solver}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>

        {/* RIGHT COLUMN: ASSISTANT WITH REAL-TIME MCP EXECUTION */}
        <aside className="right-assistant-sidebar">
          <div className="assistant-header-bar">
            <div className="assistant-title-row">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
              </svg>
              <span>Design assistant</span><button className="signin-btn-compact" onClick={commitLocal}>Commit</button><button className="signin-btn-compact" onClick={()=>kicadControl("undo")}>Undo</button><button className="signin-btn-compact" onClick={()=>kicadControl("redo")}>Redo</button>
            </div>
            <SystemMonitor/>
            <details className="assistant-settings"><summary>Tools & import settings <span>Configure</span></summary>
            <label className="recognition-choice">Output software
              <select aria-label="Output software" value={outputTool} disabled={busy||uploading} onChange={e=>setOutputTool(e.target.value)}>
                <option value="kicad">KiCad — editable schematic</option><option value="ngspice">ngspice — simulation netlist</option><option value="ltspice">LTspice — simulation netlist</option><option value="qucs-s">Qucs-S — schematic and circuit library</option>
              </select><small>Successful generation downloads a project for this application.</small>
            </label>
            <label className="recognition-choice">Image/PDF recognition
              <select aria-label="Image recognition mode" value={recognitionMode} onChange={e=>{recognitionChoiceMade.current=true;setRecognitionMode(e.target.value);}}>
                <option value="auto">Automatic: detects clear, scanned or blurry input (recommended)</option>
                <option value="digital">Digital schematic: ICs, pins, buses, connectors (OCR)</option>
                <option value="circuit">CPU components and wire connections</option>
                <option value="ocr">Labels only</option>
                <option value="vision">Vision: components and connections</option>
              </select>
              <small>{recognitionMode==='auto'?'Measures resolution, blur and skew, enhances low-quality scans and PDFs automatically, then picks the right recognizer. No manual settings.':recognitionMode==='digital'?'Scans and PDFs of printed logic schematics; about 1–2 minutes per page. Review flagged connections, then generate the OrCAD design.':recognitionMode==='vision'?'Requires a configured vision server; review extracted wiring.':recognitionMode==='circuit'?'No model required; clean R/C/V diagrams. Review every connection.':'Label text only; add connections during review.'}</small>
            </label>
            </details>
            <div className="model-selector-pill" title="Native KiCad operations">
              <span className="dot-green" />
              <span>{activeViewLabel}</span>
            </div>
          </div>

          <div className="assistant-workflow"><span>01 Describe</span><span>→</span><span>02 Review</span><span>→</span><span>03 Build</span></div>

          <div className="assistant-chat-stream">
            {msgs.length===0 && <div className="assistant-welcome-card"><span className="assistant-spark"><Icon name="spark" size={24}/></span><div className="welcome-cf-subtitle">A LITTLE LESS FRICTION</div><div className="welcome-main-headline">Bring your circuit<br/>to life.</div><div className="welcome-explainer">Start from an idea, refine a connection, or import a schematic for review.</div><div className="assistant-syntax-cheatsheet">{[['create a voltage divider','Start with a voltage divider','A simple circuit to build on','circuit'],['create RC lowpass','Explore an RC filter','Shape your next signal','wave'],['R1 = 4.7k','Refine a component','Change a value with a command','spark']].map(([prompt,title,description,icon])=><button className="starter-prompt" key={prompt} onClick={()=>focusAssistant(prompt)}><Icon name={icon}/><span>{title}<small>{description}</small></span><Icon name="arrow" size={14}/></button>)}</div></div>}

            {/* Conversation stream */}
            {msgs.map((m, i) => (
              <div key={i} role={m.error?'alert':undefined} className={`chat-message-bubble ${m.me ? 'user' : 'assistant'}`}>
                {/* AI Agent File-on-top layout */}
                {m.me && m.attachments?.length > 0 && (
                  <div className="agent-upload-header-preview">
                    {m.attachments.map((att, aIdx) => {
                      const ext = att.split('.').pop().toLowerCase();
                      const isImg = ['jpg', 'jpeg', 'png', 'webp', 'bmp', 'svg'].includes(ext);
                      return (
                        <div key={aIdx} className="agent-preview-card">
                          <div className="agent-preview-media">
                            {isImg ? (
                              <img
                                src={`${API}/projects/${pid}/file?name=${encodeURIComponent('references/' + att)}`}
                                alt={att}
                                title="Double-click to view image in full modal box"
                                style={{ cursor: 'pointer' }}
                                onDoubleClick={(e) => {
                                  e.stopPropagation();
                                  setModalImage(`${API}/projects/${pid}/file?name=${encodeURIComponent('references/' + att)}`);
                                }}
                              />
                            ) : (
                              <div className="agent-preview-doc">
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                                </svg>
                                <span>.{ext}</span>
                              </div>
                            )}
                          </div>
                          <div className="agent-preview-meta">
                            <span className="agent-preview-name">{att}</span>
                            <span className="agent-preview-badge">Uploaded Source</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
                
                <div className="agent-prompt-body">
                  {m.error?<><strong>Request not applied</strong><p>{requestErrorSummary(m.text).replace(/^Request not applied\.\s*/,'')}</p>{m.text.length>220&&<details className="chat-error-details"><summary>Details and supported commands</summary><p>{m.text}</p></details>}{m.retry&&<button className="studio-secondary" disabled={busy||uploading||m.retry.project!==pid} onClick={()=>sendPrompt(m.retry.text,m.retry.attachments)}>Retry request</button>}</>:m.text}
                </div>
                
                {m.proposal && (
                  <div style={{ marginTop: 8 }}>
                    <button className="signin-btn-compact" onClick={() => { setProposal(m.proposal); setProposalSource(m.attachments?.length ? { name: m.attachments[0], path: `/projects/${pid}/file?name=${encodeURIComponent('references/' + m.attachments[0])}` } : null); }}>
                      Open Circuit Inspector ({m.proposal.components?.length || 0} parts)
                    </button>
                  </div>
                )}
                
                {m.route && <div className="route-badge">route: {m.route}</div>}
                {m.output?.ready && (
                  <button className="signin-btn-compact" onClick={() => downloadServer(m.output.url, m.output.filename)}>
                    Download {m.output.tool} design
                  </button>
                )}
              </div>
            ))}
            {(busy||uploading)&&<AssistantActivity phase={activity} runtime={vision.runtime}/>}
            <div ref={chatEnd} />
          </div>


          {/* Composer */}
          <div className="assistant-composer-box">
            <button className="composer-quick-preset-chip" onClick={() => focusAssistant('R1 should be 4.7k')}>
              R1 should be 4.7k
            </button>

            {attachedFiles.length > 0 && (
              <div className="chips-list">
                {attachedFiles.map(fn => (
                  <div key={fn} className="file-chip">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                    <span>{fn}</span>
                    <button onClick={() => setAttachedFiles(a => a.filter(x => x !== fn))} title="Remove file" style={{ display: 'inline-flex', alignItems: 'center', background: 'transparent', border: 'none', cursor: 'pointer', padding: 0 }}>
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="composer-input-area">
              <textarea
                ref={assistantInputRef}
                className="composer-textarea" aria-label="Circuit command"
                placeholder="Describe your next circuit or change…"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    sendPrompt();
                  }
                }}
              />

              <div className="composer-toolbar-bottom">
                <div className="composer-mode-label" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                  <span>{pid || 'project'}</span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button
                    className="icon-action-btn"
                    disabled={busy||uploading} title="Attach Word, PDF, image, or text file"
                    style={{ padding: '3px 6px', fontSize: 11 }}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                  </button>

                  

                  <button className="signin-btn-compact" disabled={busy || uploading || !pid || !input.trim()} onClick={planWithModel}>Plan with model</button>
                  <button className="send-arrow-btn" disabled={busy || uploading || !pid || (!input.trim() && !attachedFiles.length)} onClick={() => sendPrompt()} title="Send command">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
                  </button>
                </div>
              </div>
            </div>

            <div className="composer-footnote">
              Enter sends · Shift+Enter adds a line. Image imports require review.
            </div>
          </div>
        </aside>
      </div>

      {/* 3. BOTTOM FOOTER BAR */}
      <footer className="bottom-status-strip">
        <div className="status-left-coordinates">
          <span>KiCad {health?.kicad ? 'ready' : 'unavailable'}</span>
          <span>{activeViewLabel}</span>
        </div>

        <div className="status-right-warnings">
          <span role="status" aria-live="polite" title={status}>{requestErrorSummary(status)}</span>
          <span>ERC: {projectData?.validation?.status==='completed' ? checksList.length ? `${checksList.length} findings` : 'Clear' : 'Not checked'}</span>
        </div>
      </footer>

      {commandOpen && <CommandPalette actions={commands} onClose={()=>setCommandOpen(false)}/>}
      {orcadResult && pid && <OrcadResult pid={pid} api={API} request={f} onDownload={()=>downloadServer(`/projects/${pid}/orcad/download`,`${pid}-orcad-dsn.zip`)} onClose={()=>setOrcadResult(false)}/>}
      {proposal && <CircuitReview initial={proposal} source={proposalSource} request={f} onApply={applyProposal} onOrcad={generateOrcad} onClose={()=>setProposal(null)} busy={busy}/>}
      {boardGraph && <BoardExport graph={boardGraph} request={f} onClose={()=>setBoardGraph(null)} onExport={async plan=>{
        const r=await f(`/projects/${pid}/export/specctra`,{method:'POST',body:JSON.stringify(plan)});
        triggerDownload(await r.blob(),`${pid}-specctra.zip`,'application/zip');setStatus('Downloaded Specctra DSN and editable PCB. Open the PCB to review placement and DRC.');
      }}/>}

      {/* Modal: Link User's Personal GitHub Account */}
      {showTokenModal && (
        <WorkbenchDialog title="Connect GitHub" onClose={()=>setShowTokenModal(false)}><div className="token-modal-card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                  <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
                </svg>
                <span className="token-modal-title">Link Your GitHub Account</span>
              </div>
              <button 
                onClick={() => setShowTokenModal(false)}
                style={{ background: 'transparent', border: 'none', color: 'var(--muted)', cursor: 'pointer', padding: 4 }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>

            <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.5, marginBottom: 16 }}>
              Paste your Personal Access Token (PAT). The app will verify it directly with GitHub and link to <strong>your personal username and repositories</strong>.
            </p>

            <form onSubmit={handleTokenSubmit}>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5, color: 'var(--muted)', marginBottom: 6 }}>
                  Personal Access Token (classic or fine-grained)
                </label>
                <input
                  type="password"
                  placeholder="ghp_... or github_pat_..."
                  value={githubTokenInput}
                  onChange={e => setGithubTokenInput(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    background: 'var(--panel2)',
                    border: '1px solid var(--line)',
                    borderRadius: 6,
                    color: 'var(--text)',
                    fontSize: 13,
                    fontFamily: 'var(--font-mono, monospace)',
                    outline: 'none',
                    boxSizing: 'border-box'
                  }}
                  autoFocus
                />
                <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 6, display: 'flex', justifyContent: 'space-between' }}>
                  <span>Requires <code>repo</code> scope for schematic sync.</span>
                  <a 
                    href="https://github.com/settings/tokens/new?scopes=repo&description=Schematic2SDN" 
                    target="_blank" 
                    rel="noreferrer"
                    style={{ color: 'var(--accent)', textDecoration: 'none' }}
                  >
                    Generate token ↗
                  </a>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                <button
                  type="button"
                  onClick={() => setShowTokenModal(false)}
                  style={{
                    padding: '8px 16px',
                    background: 'transparent',
                    border: '1px solid var(--line)',
                    borderRadius: 6,
                    color: 'var(--muted)',
                    fontSize: 13,
                    cursor: 'pointer'
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  style={{
                    padding: '8px 18px',
                    background: '#238636',
                    border: '1px solid rgba(240, 246, 252, 0.1)',
                    borderRadius: 6,
                    color: '#fff',
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                >
                  Connect Account
                </button>
              </div>
            </form>
          </div>
        </WorkbenchDialog>
      )}

      {/* IMAGE LIGHTBOX MODAL */}
      {modalImage && (
        <div 
          className="token-modal-overlay" 
          onClick={() => setModalImage(null)}
          style={{ zIndex: 9999, background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}
        >
          <div 
            onClick={e => e.stopPropagation()} 
            style={{ position: 'relative', maxWidth: '90vw', maxHeight: '90vh', background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 10, padding: 12, boxShadow: '0 20px 50px rgba(0,0,0,0.6)', display: 'flex', flexDirection: 'column', alignItems: 'center' }}
          >
            <div style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, padding: '0 4px' }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--muted)' }}>Uploaded Image Inspection</span>
              <button 
                onClick={() => setModalImage(null)}
                style={{ background: 'transparent', border: 'none', color: 'var(--text)', cursor: 'pointer', padding: 4 }}
                title="Close"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <img 
              src={modalImage} 
              alt="Uploaded schematic source" 
              style={{ maxWidth: '85vw', maxHeight: '80vh', objectFit: 'contain', borderRadius: 6, border: '1px solid var(--line)' }} 
            />
          </div>
        </div>
      )}

      {deletedProject && <div className="project-undo-toast" role="status">
        <span><strong>{deletedProject.name}</strong> {deletedProject.retained?'removed · recovery copy in trash':'moved to trash'}</span>
        <button className="btn-secondary" disabled={restoring} onClick={undoProjectDelete}>{restoring?'Restoring…':'Undo'}</button>
        <button className="toast-dismiss" aria-label="Dismiss recovery notification" onClick={()=>setDeletedProject(null)}><Icon name="close" size={16}/></button>
      </div>}
      {deleteDlg && <WorkbenchDialog title="Delete project?" busy={deleteDlg.busy} onClose={()=>setDeleteDlg(null)}>
        <p>Move <strong>{deleteDlg.name}</strong> and its files to the local project trash?</p>
        <p>You can restore it using Undo. The app saves and closes its own editor first.</p>
        {deleteDlg.error && <p>Force moving checks stale KiCad locks. If Windows holds a folder open, it verifies a recovery copy before removing the project from DeCad. The original stays on disk while locked.</p>}
        {deleteDlg.error && <p role="alert" className="delete-error">{deleteDlg.error}</p>}
        <div className="modal-actions">
          <button className="btn-secondary" disabled={deleteDlg.busy} onClick={()=>setDeleteDlg(null)} autoFocus>Keep project</button>
          {deleteDlg.error && <button className="btn-danger" disabled={deleteDlg.busy} onClick={()=>confirmDeleteProject(true)}>Force move to trash</button>}
          <button className="btn-danger" disabled={deleteDlg.busy} onClick={()=>confirmDeleteProject()}>{deleteDlg.busy?'Moving…':'Move to trash'}</button>
        </div>
      </WorkbenchDialog>}
      {/* NEW PROJECT MODAL */}
      {dlg.open && (
        <WorkbenchDialog title="New circuit project" busy={dlg.busy} onClose={()=>setDlg(d=>({...d,open:false}))}>
          <form onSubmit={submitProject}>
            <p>Create a KiCad project with native validation and local Git history.</p>
            <label htmlFor="np-name">Project Name</label>
            <input
              id="np-name"
              autoFocus
              value={dlg.name}
              placeholder="e.g. buck-converter"
              onChange={e => setDlg(d => ({ ...d, name: e.target.value, error: '' }))}
            />
            <div className={`modal-hint ${dlg.error ? 'err' : ''}`}>
              {dlg.error || 'Use alphanumeric characters, hyphens, and underscores.'}
            </div>
            <div className="modal-actions">
              <button type="button" className="btn-secondary" disabled={dlg.busy} onClick={() => setDlg({ open: false, name: '', error: '', busy: false })}>Cancel</button>
              <button type="submit" className="btn-primary" disabled={dlg.busy || !dlg.name.trim()}>Create</button>
            </div>
          </form>
        </WorkbenchDialog>
      )}
    </div>
  );
}
