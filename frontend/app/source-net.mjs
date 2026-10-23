// Convert working geometry to the original page without assuming image scale.
export function netGeometry(circuit,net,page=1){
 if(!net||net.metadata?.evidence_stale)return {pins:[],segments:[]};
 const root=circuit.image_metadata||{},entry=root.pages?.find(p=>p.page===page),meta=entry?.metadata||root;
 if(root.pages&&!entry)return {pins:[],segments:[]};
 const size=meta.source_size||[meta.width,meta.height];
 if(!size?.every(v=>Number.isFinite(v)&&v>0))return {pins:[],segments:[]};
 const matrix=meta.source_affine||[[1,0,0],[0,1,0]];
 if(!Array.isArray(matrix)||matrix.length!==2||matrix.some(row=>!Array.isArray(row)||row.length!==3||!row.every(Number.isFinite)))return {pins:[],segments:[]};
 const [[a,b,c],[d,e,f]]=matrix,det=a*e-b*d;
 if(!Number.isFinite(det)||Math.abs(det)<1e-12)return {pins:[],segments:[]};
 const point=([x,y])=>[((e*(x-c)-b*(y-f))/det)/size[0]*100,((-d*(x-c)+a*(y-f))/det)/size[1]*100];
 const valid=p=>p.every(v=>Number.isFinite(v)&&v>=0&&v<=100);
 const wanted=new Set(net.nodes.map(p=>JSON.stringify([p.ref,p.pin]))),roots=new Set(),pins=[];
 for(const anchor of meta.pin_anchors||[]){
  const ref=entry?.references?.[anchor.ref]||anchor.ref,key=JSON.stringify([ref,String(anchor.pin)]);
  if(!wanted.has(key))continue;const at=point([anchor.x,anchor.y]);
  if(valid(at)){pins.push({ref,pin:String(anchor.pin),at});if(anchor.physical_net!=null)roots.add(anchor.physical_net);}
 }
 const segments=(meta.wires||[]).filter(w=>!w.bus&&w.traced_physical_net!=null&&roots.has(w.traced_physical_net)&&Array.isArray(w.p0)&&w.p0.length===2&&Array.isArray(w.p1)&&w.p1.length===2)
  .map(w=>({id:w.id,a:point(w.p0),b:point(w.p1)})).filter(w=>valid(w.a)&&valid(w.b));
 return {pins,segments};
}
