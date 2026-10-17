// Checks that the playground's JavaScript ALU model (docs/index.html) matches the
// ALUCore8 test vectors. Usage: node tests/check_demo.js
const fs=require("fs");
const html=fs.readFileSync(require("path").join(__dirname, "..", "docs", "index.html"),"utf8");
const src=html.split('<script id="alu-model">')[1].split("</script>")[0];
const {alu}=new Function(src+";return {alu};")();
let pass=0,fail=0;
const lines=fs.readFileSync(require("path").join(__dirname, "vectors", "ALUCore8.txt"),"utf8").split("\n").filter(l=>l.trim()&&!l.startsWith("#"));
for(const l of lines.slice(1)){const [A,B,Op,R,Z,C,S,V]=l.trim().split(/\s+/);
 const o=alu(parseInt(Op,2),parseInt(A,2),parseInt(B,2));
 if(o.r===parseInt(R,2)&&o.z==Z&&o.c==C&&o.s==S&&o.v==V)pass++;else{fail++; if(fail<5)console.log(l,o)}}
console.log(`Passed: ${pass}, Failed: ${fail}`);
process.exit(fail ? 1 : 0);
