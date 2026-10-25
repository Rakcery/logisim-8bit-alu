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
// The Mini CPU section: its programs and assembler must match programs/*.asm and *.hex,
// and running the ROM program must match the cpu circuit's vectors tick by tick.
const C=new Function(src+part("cpu")+";return {PROGRAMS,assemble,cpuStep,cpuReset,cpuHalted};")();
const dir=require("path").join(__dirname,"..","programs");
for(const f of fs.readdirSync(dir).filter((f)=>f.endsWith(".asm"))){
 const name=f.slice(0,-4),asmText=fs.readFileSync(require("path").join(dir,f),"utf8");
 const hex=fs.readFileSync(require("path").join(dir,name+".hex"),"utf8").split("\n").slice(1).join(" ").trim().split(/\s+/).map((w)=>parseInt(w,16));
 const ok=C.PROGRAMS[name]===asmText&&JSON.stringify(C.assemble(asmText).words)===JSON.stringify(hex);
 if(ok)pass++;else{fail++;console.log("program:",name)}}
const rom=C.assemble(C.PROGRAMS.fibonacci).words;let st=C.cpuReset();
const cpuRows=fs.readFileSync(require("path").join(__dirname,"vectors","cpu.txt"),"utf8").split("\n").filter(l=>l.trim()&&!l.startsWith("#")).slice(1);
for(const l of cpuRows){const v=l.trim().split(/\s+/),n=(i)=>parseInt(v[i],2);
 st=v[1]==="1"?C.cpuReset():C.cpuStep(rom,st).st;
 const got=[st.pc,...st.regs,st.out,st.z,st.c,C.cpuHalted(rom,st)?1:0],want=[2,3,4,5,6,7,8,9,10].map(n);
 if(JSON.stringify(got)===JSON.stringify(want))pass++;else{fail++;if(fail<5)console.log("cpu:",l,got)}}
console.log(`Passed: ${pass}, Failed: ${fail}`);
process.exit(fail ? 1 : 0);
