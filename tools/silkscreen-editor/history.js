/* Layout history: one drag or a burst of typing is one reversible edit. */
'use strict';
class LayoutHistory {
  constructor(layout,limit=50,budget=16_000_000) {this.limit=limit;this.budget=budget;this.reset(layout);}
  reset(layout) {this.entries=[JSON.stringify(layout)];this.index=0;this.key=null;this.time=0;}
  record(layout,key=null,now=Date.now()) {
    const value=JSON.stringify(layout);
    if(value===this.entries[this.index])return;
    const merge=key!==null&&key===this.key&&now-this.time<600&&this.index>0&&this.index===this.entries.length-1;
    this.entries.splice(this.index+1);
    if(merge)this.entries[this.index]=value;
    else {this.entries.push(value);this.index++;}
    this.key=key;this.time=now;
    while(this.entries.length>2&&(this.entries.length>this.limit||this.entries.reduce((n,s)=>n+s.length,0)>this.budget)){this.entries.shift();this.index--;}
  }
  undo() {if(!this.canUndo)return null;this.key=null;return JSON.parse(this.entries[--this.index]);}
  redo() {if(!this.canRedo)return null;this.key=null;return JSON.parse(this.entries[++this.index]);}
  get canUndo() {return this.index>0;}
  get canRedo() {return this.index<this.entries.length-1;}
}
if(typeof module!=='undefined')module.exports={LayoutHistory};
