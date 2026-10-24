export function circuitSignature(circuit){
 if(!circuit)return '';
 return JSON.stringify({components:(circuit.components||[]).map(c=>[c.ref,c.value]).sort(),nets:(circuit.nets||[]).map(n=>[n.name,n.nodes.map(p=>[p.ref,String(p.pin)]).sort()]).sort()});
}
export function engineeringMetrics(circuit,design){
 const pins=new Set([...(circuit?.physical_pins||[]),...(circuit?.nets||[]).flatMap(n=>n.nodes)].map(p=>JSON.stringify([p.ref,String(p.pin)])));
 const routing=design?.routing,check=routing?.visible_wire_verification;
 const loose=routing?.endpoint_verification?.unlabelled_loose_ends??routing?.endpoint_verification?.free_end_count;
 return {components:circuit?.components?.length??design?.components??0,pins:circuit?pins.size:design?.checked_pins??0,
  multi:routing?.wired_nets,stubs:routing?.named_singleton_stubs,loose,
  shorts:check?.shorted_nets?.length,verified:design?.passed===true};
}
