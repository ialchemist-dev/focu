// DOM-independent tests for Focu's inline WebView reader. Node built-ins only.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const source = html.split('<script>\n')[1].split('</script>')[0];

class FakeElement {
  constructor(name = 'div') {
    this.name = name; this.textContent = ''; this.children = [];
    this.hidden = false; this.events = {}; this.attributes = {};
    this.classList = { toggle() {} };
    this.src = ''; this.currentTime = 0; this.duration = 100;
    this.paused = true; this.seeking = false;
    this.played = { length:1,start:()=>0,end:()=>0 };
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = [...nodes]; }
  addEventListener(name, callback) { this.events[name] = callback; }
  getBoundingClientRect() { return { top:10,height:200,bottom:210 }; }
  remove() {}
  removeAttribute() {}
  setAttribute(name,value) { this.attributes[name] = value; }
  pause() { this.paused = true; }
  play() { this.paused = false; return Promise.resolve(); }
}
function makeEnvironment(saved = {}) {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id,new FakeElement(id));
    return elements.get(id);
  };
  const storage = { ...saved };
  const speech = {
    spoken:[],
    speak(utterance) {
      this.spoken.push(utterance.text);
      if (typeof utterance.onend === 'function') utterance.onend();
    },
    cancel() {}, pause() {}, resume() {},
  };
  const document = {
    getElementById:get,
    createElement:tag=>new FakeElement(tag),
    createTextNode:value=>({textContent:value}),
    addEventListener() {},
    hidden:false,
  };
  const ctx = {
    console,URL,URLSearchParams,Date,document,
    window:{addEventListener(){},scrollTo(){}},
    innerHeight:650,scrollY:0,location:{search:''},
    localStorage:{
      getItem(k){return storage[k] || null},
      setItem(k,v){storage[k]=v},
    },
    speechSynthesis:speech,
    SpeechSynthesisUtterance:function(t){this.text=t},
    setInterval(){},
    fetch:async()=>{throw new Error('Muse embedded snapshot fallback')},
  };
  vm.createContext(ctx);
  vm.runInContext(source,ctx,{filename:'index.html'});
  return {run:expression=>vm.runInContext(expression,ctx),get,storage,speech};
}
function article(id){
  return "{id:'"+id+"',title:'A grounded research story',summary:'Short context',source:'Your research',"+
    "date:'2026-11-04',cover_url:'',audio_url:'',"+
    "blocks:[{type:'heading',level:1,text:'A grounded research story'},"+
    "{type:'paragraph',text:'The source provides evidence about the tradeoff.'}],reading_minutes:1}";
}
{
  const e=makeEnvironment();
  e.run('render(['+article('read-story')+'],"")');
  e.run("openItem('read-story')");
  assert.equal(e.run("isDone('read-story')"),false);
  e.run("tickAt=Date.now()-2000;readingTick()");
  assert.equal(e.run("isDone('read-story')"),false);
  e.run("playingId='read-story';player.paused=false");
  for(let i=0;i<6;i++) e.run("tickAt=Date.now()-2000;readingTick()");
  assert.equal(e.run("isDone('read-story')"),false,'listening cannot count as article reading');
  e.run("player.paused=true;playingId=null");
  for(let i=0;i<4;i++)e.run("tickAt=Date.now()-2000;readingTick()");
  assert.equal(e.run("isDone('read-story')"),true);
  const state=JSON.parse(e.storage['focu:content-consumption:v1']);
  assert.equal(state['read-story'].via,'article');
  assert.equal(makeEnvironment(e.storage).run("isDone('read-story')"),true);
}
{
  const e=makeEnvironment();
  e.run('render(['+article('voice-story')+'],"")');
  e.run("openItem('voice-story')");
  e.run("readAloud(allItems[0])");
  assert.ok(e.speech.spoken.length>=1);
  assert.equal(e.run("isDone('voice-story')"),true);
  assert.equal(JSON.parse(e.storage['focu:content-consumption:v1'])['voice-story'].via,'device_voice');
}
{
  const e=makeEnvironment();
  e.run("render([{id:'mp3-story',title:'Audio report',summary:'',date:'',source:'Focu',cover_url:'',audio_url:'assets/audio/example.mp3',audio_duration:100,blocks:[],reading_minutes:1}],'')");
  e.run("playingId='mp3-story'");
  const player=e.get('player');
  player.duration=100;
  player.played={length:1,start:()=>0,end:()=>100};
  player.currentTime=35;
  player.events.ended();
  assert.equal(e.run("isDone('mp3-story')"),false,'premature end must not archive');
  player.currentTime=100;
  player.events.ended();
  assert.equal(e.run("isDone('mp3-story')"),true,'completed MP3 should archive');
}

// Manually archived from a list card: a separate action, not a tap to read.
{
  const e=makeEnvironment();
  e.run('render(['+article('card-story')+'],"")');
  const card=e.get('grid').children[0];
  assert.equal(card.name,'div');
  assert.equal(card.children[0].name,'button','separate reader action');
  const button=card.children[1].children[0];
  assert.equal(button.textContent,'Archive');
  button.onclick();
  assert.equal(e.run("isDone('card-story')"),true);
  assert.equal(JSON.parse(e.storage['focu:content-consumption:v1'])['card-story'].via,'manual');
  assert.equal(e.get('grid').children.length,1,'Inbox now empty');
  e.run("render(allItems,'')");
  assert.equal(e.get('grid').children.length,1,'re-render does not resurrect the card');
  assert.equal(makeEnvironment(e.storage).run("isDone('card-story')"),true,'reload retains archived state');
  e.run("setView('archive')");
  const restore=e.get('grid').children[0].children[1].children[0];
  assert.equal(restore.textContent,'Restore');
  restore.onclick();
  assert.equal(e.run("isDone('card-story')"),false);
  assert.equal(e.get('grid').children.length,1,'Archive empties after restore');
  e.run("setView('inbox')");
  assert.equal(e.get('grid').children[0].children[1].children[0].textContent,'Archive');
}
{
  const e=makeEnvironment();
  e.run('render(['+article('reader-story')+'],"")');
  e.run("openItem('reader-story')");
  assert.equal(e.get('readerarchive').hidden,false);
  e.get('readerarchive').onclick();
  assert.equal(e.run("isDone('reader-story')"),true);
  assert.equal(JSON.parse(e.storage['focu:content-consumption:v1'])['reader-story'].via,'manual');
  assert.equal(e.get('reader').hidden,true,'manual archive closes reader');
  e.run("setView('archive')");
  e.run("openItem('reader-story')");
  assert.equal(e.get('readerarchive').hidden,true,'archived reader does not show Archive');
  e.get('restore').onclick();
  assert.equal(e.run("isDone('reader-story')"),false,'reader Restore works');
  assert.equal(e.get('readerarchive').hidden,false);
}
// An automatic completion must remain independent of the manual action.
{
  // The stored policy never invents an MP3 or displays a phantom Listen control.
  const e=makeEnvironment();
  e.run("render([{id:'idea',title:'Idea report',summary:'',date:'',source:'Your research',podcast_mode:'single',cover_url:'',audio_url:'',blocks:[{type:'paragraph',text:'Peer-level evidence'}],reading_minutes:1}],'')");
  e.run("openItem('idea')");
  assert.equal(e.get('listen').hidden,true,'podcast_mode alone does not show MP3 player');
  assert.equal(e.get('readaloud').hidden,false,'device speech remains a separate action');
  assert.equal(e.get('coveredby').hidden,true);
}
{
  const e=makeEnvironment();
  e.run("render([{id:'source-1',title:'Source report',summary:'',date:'2026-11-05',source:'Source A',podcast_mode:'daily_compilation',audio_url:'',blocks:[{type:'paragraph',text:'A report'}],reading_minutes:1},{id:'daily-1',title:'Daily briefing',summary:'',date:'2026-11-05',source:'Focu',podcast_mode:'daily_compilation',audio_url:'assets/audio/daily.mp3',covered_content_ids:['source-1'],blocks:[],reading_minutes:1}],'')");
  e.run("openItem('source-1')");
  assert.equal(e.get('listen').hidden,true);
  assert.equal(e.get('coveredby').hidden,false,'linked source shows daily briefing');
  assert.match(e.get('coveredby').textContent,/2026-11-05/);
  e.get('coveredby').onclick();
  assert.equal(e.run('currentId'),'daily-1');
  assert.equal(e.get('listen').hidden,false,'compiled episode has real audio');
  assert.equal(e.get('readaloud').hidden,true);
}
console.log('Focu reader behavior: article, local read-aloud, persistence and audio end passed');
