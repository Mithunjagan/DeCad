export const measuredPercent=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=100?value:null;
export const percentText=value=>measuredPercent(value)===null?'—':`${Math.round(value)}%`;
export function memoryText(used,total){
  if(!Number.isFinite(used)||!Number.isFinite(total)||total<=0||used<0||used>total)return 'Unavailable';
  return `${(used/2**30).toFixed(1)} / ${(total/2**30).toFixed(1)} GiB`;
}
export function primaryGpu(gpus=[]){
  return [...gpus].sort((a,b)=>(measuredPercent(b.utilization_percent)??-1)-(measuredPercent(a.utilization_percent)??-1))[0]||null;
}
