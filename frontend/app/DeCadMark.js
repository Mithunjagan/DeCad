/** DeCad's open D: a return trace, an inner signal path and two terminal nodes. */
export default function DeCadMark({size=32,...props}){
 return <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true" {...props}>
  <path d="M12 9h13l12 10v10L25 39H12V25" stroke="currentColor" strokeWidth="4" strokeLinecap="square" strokeLinejoin="round"/>
  <path d="M12 18h10l7 6-7 6h-3" stroke="currentColor" strokeWidth="3" strokeLinecap="square" strokeLinejoin="round"/>
  <circle cx="12" cy="18" r="3.5" fill="currentColor"/><circle cx="12" cy="9" r="2" fill="currentColor"/>
 </svg>;
}
