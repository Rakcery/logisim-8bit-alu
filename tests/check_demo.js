// Checks that the playground's JavaScript ALU model (docs/index.html) and its
// step-by-step walk-through match the ALUCore8 test vectors. Usage: node tests/check_demo.js
const fs=require("fs");
const html=fs.readFileSync(require("path").join(__dirname, "..", "docs", "index.html"),"utf8");
const src=html.split('<script id="alu-model">')[1].split("</script>")[0];
const {alu}=new Function(src+";return {alu};")();
let pass=0,fail=0;
const lines=fs.readFileSync(require("path").join(__dirname, "vectors", "ALUCore8.txt"),"utf8").split("\n").filter(l=>l.trim()&&!l.startsWith("#"));
for(const l of lines.slice(1)){const [A,B,Op,R,Z,C,S,V]=l.trim().split(/\s+/);
 const o=alu(parseInt(Op,2),parseInt(A,2),parseInt(B,2));
 if(o.r===parseInt(R,2)&&o.z==Z&&o.c==C&&o.s==S&&o.v==V)pass++;else{fail++; if(fail<5)console.log(l,o)}}
// The walk-through computes each answer its own way (full adders, barrel stages,
// long multiplication and division); it must land on the same R, C and V.
// The simple walk-through (dial, lamps, fitting B into A) must land on the same R.
const part=(id)=>html.split(`<script id="${id}">`)[1].split("</script>")[0];
const main=html.split('<script>\nconst $ =')[1];
const consts=["BLOCK","HEX_SEGMENTS","hex2","sgn"].map((n)=>main.match(new RegExp(`const ${n} = [\\s\\S]*?;\\n`))[0]).join("")+
 ["sumText","flagLines"].map((n)=>main.match(new RegExp(`function ${n}\\([\\s\\S]*?\\n}\\n`))[0]).join("");
const env=(lang)=>new Function(src+`let LANG="${lang}";const L=(en,tr)=>LANG==="tr"?tr:en;`+part("diagrams")+consts+part("trace")+";return [traceSteps, simpleSteps];")();
const trace={en:env("en"),tr:env("tr")};
lines.slice(1).forEach((l,n)=>{const [A,B,Op,R,Z,C,S,V]=l.trim().split(/\s+/);
 trace[n%2?"tr":"en"].forEach((walk)=>{
  const steps=walk(parseInt(Op,2),parseInt(A,2),parseInt(B,2)),k=steps.check;
  const ok=k.r===parseInt(R,2)&&(k.c===undefined||k.c==C)&&(k.v===undefined||k.v==V)&&!steps.some((st)=>/undefined|NaN/.test(st.svg+st.text));
  if(ok)pass++;else{fail++; if(fail<5)console.log(walk.name+":",l,k)}})});
console.log(`Passed: ${pass}, Failed: ${fail}`);
process.exit(fail ? 1 : 0);
