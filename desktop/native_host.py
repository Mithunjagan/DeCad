"""Windows desktop shell: WebView2 workbench and the real, owned eeschema HWND.

Only this host's editor process is docked/closed. WM_CLOSE keeps KiCad's own
unsaved-work prompts; no force termination. Backend mutations suspend the editor
before writing and reopen it afterwards through a local request/ack mailbox.
"""
import argparse
import ctypes as ct
from ctypes import wintypes as wt
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

user32=ct.WinDLL('user32',use_last_error=True)
try:
    user32.SetProcessDpiAwarenessContext.argtypes=[ct.c_void_p]
    user32.SetProcessDpiAwarenessContext(ct.c_void_p(-4))
except AttributeError:pass
HWND=wt.HWND
CALLBACK=ct.WINFUNCTYPE(wt.BOOL,HWND,wt.LPARAM)
for name,args,restype in [
    ('EnumWindows',[CALLBACK,wt.LPARAM],wt.BOOL),
    ('GetWindowThreadProcessId',[HWND,ct.POINTER(wt.DWORD)],wt.DWORD),
    ('GetWindowTextW',[HWND,wt.LPWSTR,ct.c_int],ct.c_int),
    ('GetClassNameW',[HWND,wt.LPWSTR,ct.c_int],ct.c_int),
    ('IsWindow',[HWND],wt.BOOL),('IsWindowVisible',[HWND],wt.BOOL),
    ('GetParent',[HWND],HWND),('SetParent',[HWND,HWND],HWND),
    ('GetWindowLongPtrW',[HWND,ct.c_int],ct.c_ssize_t),
    ('SetWindowLongPtrW',[HWND,ct.c_int,ct.c_ssize_t],ct.c_ssize_t),
    ('SetWindowPos',[HWND,HWND,ct.c_int,ct.c_int,ct.c_int,ct.c_int,wt.UINT],wt.BOOL),
    ('ShowWindow',[HWND,ct.c_int],wt.BOOL),
    ('PostMessageW',[HWND,wt.UINT,wt.WPARAM,wt.LPARAM],wt.BOOL),
    ('GetMenu',[HWND],wt.HMENU),('GetSubMenu',[wt.HMENU,ct.c_int],wt.HMENU),
    ('GetMenuItemCount',[wt.HMENU],ct.c_int),('GetMenuItemID',[wt.HMENU,ct.c_int],wt.UINT),
    ('GetMenuStringW',[wt.HMENU,wt.UINT,wt.LPWSTR,ct.c_int,wt.UINT],ct.c_int),
    ('SetWindowRgn',[HWND,wt.HANDLE,wt.BOOL],ct.c_int),
]:
    fn=getattr(user32,name);fn.argtypes=args;fn.restype=restype

import wx
import wx.html2
gdi32=ct.WinDLL('gdi32',use_last_error=True)
gdi32.CreateRectRgn.argtypes=[ct.c_int]*4;gdi32.CreateRectRgn.restype=wt.HANDLE
gdi32.CombineRgn.argtypes=[wt.HANDLE,wt.HANDLE,wt.HANDLE,ct.c_int];gdi32.CombineRgn.restype=ct.c_int
gdi32.DeleteObject.argtypes=[wt.HANDLE];gdi32.DeleteObject.restype=wt.BOOL


def title(hwnd):
    buf=ct.create_unicode_buffer(1024);user32.GetWindowTextW(hwnd,buf,len(buf));return buf.value


def windows(pid):
    found=[]
    @CALLBACK
    def enum(hwnd,_):
        owner=wt.DWORD();user32.GetWindowThreadProcessId(hwnd,ct.byref(owner))
        if owner.value==pid:found.append((hwnd,title(hwnd)))
        return True
    user32.EnumWindows(enum,0);return found


def menu_command(hwnd, wanted, root=None):
    def walk(menu):
        for i in range(user32.GetMenuItemCount(menu)):
            buf=ct.create_unicode_buffer(512);user32.GetMenuStringW(menu,i,buf,len(buf),0x400)
            label=buf.value.replace('&','').split('\t')[0].strip().rstrip('.').lower()
            if label==wanted:
                value=user32.GetMenuItemID(menu,i)
                if value!=0xffffffff:return value
            sub=user32.GetSubMenu(menu,i)
            if sub:
                value=walk(sub)
                if value is not None:return value
    return walk(root or user32.GetMenu(hwnd))


def menu_snapshot(menu):
    result=[]
    for i in range(user32.GetMenuItemCount(menu)):
        text=ct.create_unicode_buffer(512);user32.GetMenuStringW(menu,i,text,len(text),0x400)
        sub=user32.GetSubMenu(menu,i)
        result.append({'label':text.value.split('\t')[0],'id':user32.GetMenuItemID(menu,i),
                       'children':menu_snapshot(sub) if sub else []})
    return result


def write_json(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data),encoding='utf-8')
    for attempt in range(4):
        try:temp.replace(path);return
        except PermissionError:
            if attempt==3:raise
            time.sleep(.01)


class Desktop(wx.Frame):
    def __init__(self,args):
        area=wx.GetClientDisplayRect()
        super().__init__(None,title='DeCad — Native KiCad Workbench',size=(min(1600,area.width),min(1000,area.height)))
        self.SetIcons(wx.IconBundle(str(Path(__file__).resolve().parents[1]/'frontend/public/decad.ico')))
        self.args=args;self.root=Path(args.root).resolve();self.project=None;self.path=None
        self.editor=None;self.hwnd=None;self.opening=None;self.closing=None
        self.menu=None
        self.commands={}
        self.menu_bindings=[]
        self.baseline_locks=set();self.owned_locks={}
        self.bounds=None;self.visible=False;self.suspended=False;self.quitting=False
        self.folder=Path(args.state)/'native-desktop'/uuid.uuid4().hex;self.folder.mkdir(parents=True)
        if args.verify:os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS']='--remote-debugging-port=9227 --remote-debugging-address=127.0.0.1'
        self.web=wx.html2.WebView.New(self,backend=wx.html2.WebViewBackendEdge)
        self.panel=wx.Panel(self);self.panel.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW));self.panel.Hide()
        self.web.AddScriptMessageHandler('decad')
        config=json.dumps({'project':args.project,'local':args.local_login,
                           'systemDark':wx.SystemSettings.GetAppearance().AreAppsDark()})
        self.web.AddUserScript('''(()=>{
          const pending=new Map();let next=0;
          window.__DECAD_DESKTOP__=Object.assign(CONFIG,{
            request(action,payload={}){return new Promise((resolve,reject)=>{
              const id=String(++next);const timeout=setTimeout(()=>{pending.delete(id);reject(Error('KiCad did not respond. Finish its dialog and retry.'));},30000);
              pending.set(id,{resolve,reject,timeout});window.decad.postMessage(JSON.stringify({id,action,...payload}));
            });},
            notify(action,payload={}){window.decad.postMessage(JSON.stringify({action,...payload}));},
            _reply(id,result){const p=pending.get(id);if(!p)return;clearTimeout(p.timeout);pending.delete(id);result.ok?p.resolve(result):p.reject(Error(result.error));}
          });
        })();'''.replace('CONFIG',config))
        self.web.Bind(wx.html2.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED,self.message)
        self.web.Bind(wx.html2.EVT_WEBVIEW_NAVIGATING,self.navigate)
        self.Bind(wx.EVT_SIZE,self.resize);self.Bind(wx.EVT_CLOSE,self.close_frame)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED,self.system_colours)
        self.timer=wx.Timer(self);self.Bind(wx.EVT_TIMER,self.tick,self.timer);self.timer.Start(200)
        if args.verify:self.SetPosition((-2800,0))
        else:self.CentreOnScreen()
        self.web.LoadURL('http://localhost:3100');self.Show();self.status()

    def navigate(self,event):
        from urllib.parse import urlsplit
        url=urlsplit(event.GetURL())
        if url.scheme in ('http','https') and url.netloc!='localhost:3100':
            event.Veto();wx.LaunchDefaultBrowser(event.GetURL())

    def system_colours(self,event):
        dark=wx.SystemSettings.GetAppearance().AreAppsDark()
        self.panel.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
        # Edge WebView2's media preference can differ from Windows app mode.
        # Report Windows' actual app appearance, including subsequent changes.
        self.web.RunScriptAsync('if(window.__DECAD_DESKTOP__){window.__DECAD_DESKTOP__.systemDark='+json.dumps(dark)+';window.dispatchEvent(new Event("decad-system-appearance"));}')
        event.Skip()

    def reply(self,key,result):
        if key is not None:
            self.web.RunScriptAsync('window.__DECAD_DESKTOP__?._reply('+json.dumps(key)+','+json.dumps(result)+')')

    def install_menus(self,items):
        # Recreate labels as host menus, dispatching each command to the real
        # editor. Native HMENU objects cannot be displayed on a child HWND.
        for item_id in self.menu_bindings:self.Unbind(wx.EVT_MENU,id=item_id)
        self.menu_bindings=[]
        def build(entries):
            menu=wx.Menu()
            for entry in entries:
                label=entry['label'];code=entry['id']
                if not label:
                    if menu.GetMenuItemCount():menu.AppendSeparator()
                elif entry['children']:menu.AppendSubMenu(build(entry['children']),label)
                elif code not in (0,0xffffffff,65534):
                    item=menu.Append(wx.ID_ANY,label);key=item.GetId();self.menu_bindings.append(key)
                    self.Bind(wx.EVT_MENU,lambda event,value=code:self.dispatch(value),id=key)
            return menu
        bar=wx.MenuBar()
        for entry in items:
            if entry['children']:bar.Append(build(entry['children']),entry['label'])
        self.SetMenuBar(bar);self.web.SetSize(self.GetClientSize());self.layout_editor()

    def dispatch(self,code):
        if self.hwnd and user32.IsWindow(self.hwnd):user32.PostMessageW(self.hwnd,0x111,code,0)

    def remember_locks(self):
        if not self.project:return
        for path in self.project.glob('*.lck'):
            if path.name in self.baseline_locks or path in self.owned_locks:continue
            try:
                stat=path.stat();self.owned_locks[path]=(stat.st_ino,stat.st_ctime_ns,path.read_bytes())
            except OSError:pass

    def clear_owned_locks(self):
        # KiCad can leave its project-settings lock after a standalone editor
        # exits. Remove only files created during OUR session, with unchanged
        # file identity/content, and only after the owned process has exited.
        if self.editor and self.editor.poll() is None:return
        for path,identity in self.owned_locks.items():
            try:
                stat=path.stat()
                if (stat.st_ino,stat.st_ctime_ns,path.read_bytes())==identity:path.unlink()
            except OSError:pass
        self.owned_locks={}

    def message(self,event):
        if not self.web.GetCurrentURL().startswith('http://localhost:3100/'):return
        key=None
        try:
            data=json.loads(event.GetString());key=data.get('id');action=data.get('action')
            if action=='bounds':
                self.bounds=data;self.visible=bool(data.get('visible'));self.layout_editor();return
            if action=='open':
                path=Path(data['path']).resolve()
                if not path.is_relative_to(self.root) or path.suffix!='.kicad_sch' or not path.is_file():raise ValueError('Invalid project schematic path.')
                self.open_editor(path,lambda r:self.reply(key,r));return
            if action=='release':
                self.release(lambda r:self.reply(key,r),clear=True);return
            if action=='control':
                if not self.hwnd:raise ValueError('Open the native KiCad editor first.')
                command=data.get('command');code=self.commands.get(command)
                if code is None:raise ValueError('Use KiCad’s own toolbar for this action.')
                self.dispatch(code);self.reply(key,{'ok':True});return
            raise ValueError('Unknown desktop action.')
        except Exception as exc:self.reply(key,{'ok':False,'error':str(exc)})

    def open_editor(self,path,callback):
        path=Path(path).resolve()
        if self.closing or self.opening:callback({'ok':False,'error':'KiCad is opening or closing. Finish its dialog and retry.'});return
        if self.editor and self.editor.poll() is None:
            if self.path==path:self.suspended=False;self.layout_editor();callback({'ok':True});return
            callback({'ok':False,'error':'Close the current KiCad project before opening another.'});return
        if (path.parent/('~'+path.name+'.lck')).exists():
            callback({'ok':False,'error':'This project is already open in another KiCad window. Close it first.'});return
        self.path=path;self.project=path.parent;self.suspended=False;self.hwnd=None
        self.baseline_locks={p.name for p in self.project.glob('*.lck')};self.owned_locks={}
        startup=subprocess.STARTUPINFO();startup.dwFlags=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
        self.editor=subprocess.Popen([self.args.eeschema,str(path)],cwd=str(path.parent),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,startupinfo=startup)
        self.opening=(time.monotonic()+28,callback);self.status()

    def release(self,callback,clear=False):
        if self.closing or self.opening:callback({'ok':False,'error':'Finish opening or closing KiCad, then retry.'});return
        if not self.editor or self.editor.poll() is not None:
            self.clear_owned_locks()
            self.hwnd=None;self.suspended=not clear
            if clear:self.project=None;self.path=None
            self.panel.Hide();self.status();callback({'ok':True});return
        if not self.hwnd:callback({'ok':False,'error':'KiCad is not ready. Finish its dialog first.'});return
        if not clear and self.path.stem not in title(self.hwnd):
            callback({'ok':False,'error':'KiCad is showing another schematic. Save and close it before editing this project.'});return
        # Save through the actual File > Save command, then request a graceful close.
        save=self.commands.get('save')
        if save is not None:user32.PostMessageW(self.hwnd,0x111,save,0)
        self.closing={'deadline':time.monotonic()+20,'callback':callback,'clear':clear,'post_at':time.monotonic()+.35,'posted':False}

    def layout_editor(self):
        if not self.bounds or not self.visible or not self.hwnd or self.suspended:
            self.panel.Hide();user32.SetWindowRgn(self.web.GetHandle(),None,True);return
        b=self.bounds;size=self.web.GetClientSize();scale=size.width/max(1,b.get('viewport',size.width))
        x=max(0,round(b['x']*scale));y=max(0,round(b['y']*scale))
        w=max(1,min(size.width-x,round(b['width']*scale)));h=max(1,min(size.height-y,round(b['height']*scale)))
        self.panel.SetSize(x,y,w,h);self.panel.Show();self.panel.Raise()
        # WebView2 owns a separate compositor surface. Cut its native window region
        # around the editor so its surface cannot obscure KiCad's GDI toolbars.
        region=gdi32.CreateRectRgn(0,0,size.width,size.height);hole=gdi32.CreateRectRgn(x,y,x+w,y+h)
        gdi32.CombineRgn(region,region,hole,4);gdi32.DeleteObject(hole)
        if not user32.SetWindowRgn(self.web.GetHandle(),region,True):gdi32.DeleteObject(region)
        user32.SetWindowPos(self.hwnd,None,0,0,w,h,0x34);user32.ShowWindow(self.hwnd,5)

    def resize(self,event):
        self.web.SetSize(self.GetClientSize());self.layout_editor();event.Skip()

    def status(self,closed=False):
        write_json(self.folder/'status.json',{'pid':os.getpid(),'updated':time.time(),'project':str(self.project) if self.project else None,
            'path':str(self.path) if self.path else None,'editor_pid':self.editor.pid if self.editor and self.editor.poll() is None else None,
            'hwnd':self.hwnd,'panel_hwnd':self.panel.GetHandle(),'commands':self.commands,'suspended':self.suspended,'closed':closed})

    def tick(self,event):
        try:
            if self.editor and self.editor.poll() is not None and self.owned_locks:self.clear_owned_locks()
            if self.opening:
                deadline,callback=self.opening
                if self.editor.poll() is not None:
                    self.opening=None;callback({'ok':False,'error':'KiCad exited before its editor opened.'})
                else:
                    for hwnd,name in windows(self.editor.pid):
                        if 'Schematic Editor' in name and user32.GetMenu(hwnd):
                            self.hwnd=hwnd
                            self.menu=user32.GetMenu(hwnd)
                            snapshot=menu_snapshot(self.menu)
                            if self.args.verify:write_json(self.folder/'native-menu.json',snapshot)
                            # Windows detaches the frame's HMENU during reparenting.
                            # Capture real command IDs before that; dispatch remains
                            # within KiCad's event table, never fabricated keystrokes.
                            self.commands={key:menu_command(hwnd,label,self.menu) for key,label in {
                                'save':'save','undo':'undo','redo':'redo','zoom_fit':'zoom to all objects',
                                'zoom_in':'zoom in','zoom_out':'zoom out','redraw':'refresh','grid':'grid',
                                'select_all':'select all','move':'move'}.items()}
                            style=user32.GetWindowLongPtrW(hwnd,-16)
                            user32.SetWindowLongPtrW(hwnd,-16,(style&~0x80c40000)|0x40000000)
                            ct.set_last_error(0);user32.SetParent(hwnd,self.panel.GetHandle())
                            if ct.get_last_error():raise OSError(ct.get_last_error(),'Cannot dock KiCad')
                            self.opening=None;self.install_menus(snapshot);self.layout_editor();callback({'ok':True})
                            self.remember_locks()
                            if self.commands.get('zoom_fit'):wx.CallLater(400,self.dispatch,self.commands['zoom_fit'])
                            break
                    if self.opening and time.monotonic()>deadline:
                        self.opening=None;callback({'ok':False,'error':'Finish the KiCad startup dialog, then reopen the native editor.'})
            if self.closing:
                job=self.closing
                if not job['posted'] and time.monotonic()>job['post_at']:
                    if self.hwnd:user32.PostMessageW(self.hwnd,0x10,0,0)
                    job['posted']=True
                if self.editor.poll() is not None:
                    self.clear_owned_locks()
                    self.closing=None;self.hwnd=None;self.panel.Hide();self.suspended=not job['clear'];self.layout_editor()
                    if job['clear']:self.project=None;self.path=None
                    job['callback']({'ok':True})
                elif time.monotonic()>job['deadline']:
                    self.closing=None;job['callback']({'ok':False,'error':'Finish or cancel KiCad’s dialog, then retry. Your edits have been preserved.'})
            if self.hwnd and not user32.IsWindow(self.hwnd):
                self.clear_owned_locks();self.hwnd=None;self.layout_editor()
                self.web.RunScriptAsync('window.dispatchEvent(new Event("decad-native-closed"))')
            if self.hwnd and self.editor and self.editor.poll() is None:self.remember_locks()
            for file in self.folder.glob('*.request.json'):
                data=json.loads(file.read_text());file.unlink(missing_ok=True)
                reply=self.folder/(data['id']+'.reply.json')
                respond=lambda r,p=reply:write_json(p,r)
                if time.time()-data.get('created',0)>25:continue
                if data.get('project')!=str(self.project):respond({'ok':False,'error':'The active project changed. Retry the operation.'});continue
                if data['action']=='suspend':self.release(respond)
                elif data['action']=='release':self.release(respond,clear=True)
                elif data['action']=='resume' and self.path:self.open_editor(self.path,respond)
                else:respond({'ok':False,'error':'Unsupported desktop request.'})
            if not self.quitting:self.status()
        except Exception as exc:
            with (self.folder/'errors.log').open('a') as log:log.write(str(exc)+'\n')

    def close_frame(self,event):
        if self.quitting:event.Skip();return
        event.Veto()
        def closed(result):
            if result.get('ok'):
                self.quitting=True;self.timer.Stop();self.status(closed=True);self.Destroy()
            else:wx.MessageBox(result['error'],'Close KiCad first',wx.OK|wx.ICON_INFORMATION,self)
        self.release(closed,clear=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--state',required=True)
    parser.add_argument('--eeschema',required=True);parser.add_argument('--project',default='');parser.add_argument('--local-login',action='store_true');parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    # Give this window its own taskbar identity instead of pythonw.exe's icon.
    shell32=ct.WinDLL('shell32',use_last_error=True)
    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes=[wt.LPCWSTR]
    shell32.SetCurrentProcessExplicitAppUserModelID.restype=ct.c_long
    shell32.SetCurrentProcessExplicitAppUserModelID('DeCad.Workbench')
    app=wx.App(False);app.SetAppName('DeCad')
    # wxMSW must opt in before creating any HWNDs. System also follows later
    # Windows appearance changes; no global Windows or KiCad preferences change.
    app.SetAppearance(wx.App.Appearance.System)
    if not wx.html2.WebView.IsBackendAvailable(wx.html2.WebViewBackendEdge):raise SystemExit('Microsoft WebView2 is unavailable.')
    Desktop(args);app.MainLoop()
