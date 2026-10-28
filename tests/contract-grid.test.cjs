const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
class Element {constructor(){this.style={};this.children=[];this.isConnected=true;this.hidden=false}setAttribute(){}append(...nodes){this.children.push(...nodes)}after(node){this.next=node}}
const context=vm.createContext({document:{createElement:()=>new Element()},window:{},console});
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../contract-details.js'),'utf8'),context);
const container=new Element();let current=0,total=3,refresh;
const grid={paginationGetCurrentPage:()=>current,paginationGetTotalPages:()=>total,addEventListener:(name,fn)=>refresh=fn,paginationGoToNextPage:()=>{current++;refresh()},paginationGoToPreviousPage:()=>{current--;refresh()}};
const nav=context.addContractPager(container,grid);const [previous,label,next]=nav.children;
assert.equal(previous.hidden,true);assert.equal(next.hidden,false);assert.equal(label.textContent,'Page 1 of 3');
next.onclick();assert.equal(previous.hidden,false);assert.equal(next.hidden,false);
next.onclick();assert.equal(next.hidden,true);assert.equal(label.textContent,'Page 3 of 3');
previous.onclick();assert.equal(next.hidden,false);
total=1;current=0;refresh();assert.equal(nav.hidden,true);
total=0;refresh();assert.equal(nav.hidden,true);
const rows=JSON.parse(JSON.stringify(context.contractRows({city:{name:'Lagos'},phones:['123','456']},'Office')));
assert.equal(rows[0].field,'Office · city · name');assert.equal(rows[0].value,'Lagos');assert.equal(rows.length,3);
console.log('Grid paging boundaries and nested detail rows passed');
