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
  append(...nodes) {
    for (const n of nodes) if (n && typeof n === 'object') n.parent = this;
    this.children.push(...nodes);
  }
  replaceChildren(...nodes) {
    for (const n of this.children) if (n && n.parent === this) n.parent = null;
    this.children = [];
    this.append(...nodes);
  }
  addEventListener(name, callback) { this.events[name] = callback; }
  getBoundingClientRect() { return { top:10,height:200,bottom:210 }; }
  remove() {
    this.hidden = true;
    if (this.parent) {
      this.parent.children = this.parent.children.filter(x => x !== this);
      this.parent = null;
    }
  }
  removeAttribute() {}
  setAttribute(name,value) { this.attributes[name] = value; }
  pause() { this.paused = true; }
  load() { this.loadCount = (this.loadCount || 0) + 1; this.paused = true; }
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
    window:{addEventListener(){},scrollTo(x,y){ctx.scrollY=y||0}},
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
    "date:'2026-11-04',origin:'daily_compilation',cover_url:'',audio_url:'',"+
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

// Muse iOS host chrome intercepts the top of the WebView; tabs must sit below it.
// This static guard does NOT replace real-device coordinate-based touch acceptance.
assert.match(html, /--muse-header-clearance:68px/);
assert.match(html, /padding:calc\(12px \+ var\(--muse-header-clearance\)\)/);
assert.match(html, /padding:calc\(10px \+ var\(--muse-header-clearance\)\)/);
assert.match(html, /header-clearance/);
assert.match(html, /display-mode:standalone[^}]*--muse-header-clearance:0px/);

// Touch screens should not inherit sticky hover-red article titles after tapping.
assert.match(html, /@media\s*\(hover:hover\)\s*and\s*\(pointer:fine\)/);
assert.match(html, /\.feedcard\[hidden\]\{display:none!important\}/);

// Manually archived from a list card: a separate action, not a tap to read.
{
  const e=makeEnvironment();
  e.run('render(['+article('card-story')+'],"")');
  const card=e.get('grid').children[0];
  assert.equal(card.name,'div');
  assert.equal(card.children[0].name,'button','separate reader action');
  const button=card.children[1].children[0];
  assert.equal(button.textContent,'Archive');
  let prevented=false,stopped=false;
  button.onclick({preventDefault(){prevented=true},stopPropagation(){stopped=true}});
  assert.equal(prevented,true,'tap should not bubble into the story opener');
  assert.equal(stopped,true,'archive tap should not activate the reader');
  assert.equal(card.hidden,true,'card must hide synchronously on tap');
  assert.equal(e.get('grid').children.includes(card),false,'tapped card removed before full list reconciliation');
  assert.equal(e.run("isDone('card-story')"),true);
  assert.equal(JSON.parse(e.storage['focu:content-consumption:v1'])['card-story'].via,'manual');
  assert.equal(e.get('grid').children.length,1,'Inbox now empty');
  e.run("render(allItems,'')");
  assert.equal(e.get('grid').children.length,1,'re-render does not resurrect the card');
  assert.equal(makeEnvironment(e.storage).run("isDone('card-story')"),true,'reload retains archived state');
  e.run("setView('archive')");
  const restore=e.get('grid').children[0].children[1].children[0];
  assert.equal(restore.textContent,'Restore');
  const archivedCard=e.get('grid').children[0];
  restore.onclick();
  assert.equal(archivedCard.hidden,true,'restored card hides immediately in Archive');
  assert.equal(e.get('grid').children.includes(archivedCard),false,'restored card is removed synchronously');
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

// Daily Briefing contains compiled reports; completed on-demand articles live
// under Research. Source articles remain linked from the compilation.
{
  const e=makeEnvironment();
  e.run("render(["+
    "{id:'daily-8',origin:'daily_compilation',title:'Earlier briefing',date:'2026-11-08',source:'Focu',blocks:[{type:'paragraph',text:'Earlier'}],covered_content_ids:[]},"+
    "{id:'source-1',origin:'registered_source',title:'Original experiment',date:'2026-11-09',source:'Anthropic',blocks:[{type:'paragraph',text:'Evidence'}]},"+
    "{id:'daily-9',origin:'daily_compilation',title:'Latest briefing',date:'2026-11-09',source:'Focu',audio_url:'media/briefing.mp3',blocks:[{type:'paragraph',text:'Daily report'}],covered_content_ids:['source-1','research-1']},"+
    "{id:'research-1',origin:'user_initiated',title:'New METR research',date:'2026-11-09',source:'Your research',blocks:[{type:'paragraph',text:'Evidence-backed analysis'}]},"+
    "{id:'research-2',origin:'user_initiated',title:'Earlier research',date:'2026-11-06',source:'Your research',blocks:[{type:'paragraph',text:'Prior analysis'}]}"+
  "],'')");
  assert.equal(e.run('view'),'briefing');
  assert.equal(e.get('grid').children.length,2,'daily home lists compilations, not covered sources or research');
  assert.match(e.get('grid').children[0].children[0].children[0].children[1].textContent,/Latest briefing/);
  e.run("openItem('daily-9')");
  assert.equal(e.get('coveredsection').hidden,false);
  assert.equal(e.get('coveredarticles').children.length,2,'daily briefing links all covered original articles');
  e.get('coveredarticles').children[0].onclick();
  assert.equal(e.run('currentId'),'source-1');
  assert.equal(e.get('coveredby').hidden,false);
  e.get('back').onclick();
  assert.equal(e.run('currentId'),'daily-9','Back from source returns to briefing');
  e.get('listen').onclick();
  assert.equal(e.get('playerbar').hidden,false,'briefing playback controls active');
  assert.equal(e.run('playingId'),'daily-9');
  e.run("setView('research')");
  assert.equal(e.get('playerbar').hidden,false,'tab switching must not interrupt playback');
  assert.equal(e.get('player').paused,false);
  assert.equal(e.get('grid').children.length,2,'research lists published commissioned research only');
  assert.match(e.get('grid').children[0].children[0].children[0].children[1].textContent,/New METR research/);
  e.run("openItem('research-1')");
  e.run('scrollY=280');
  e.run("setView('briefing')");
  e.run("setView('research')");
  e.run("openItem('research-1')");
  assert.equal(e.run('scrollY'),280,'per-article reading position is restored after tab switch');
  e.get('readerarchive').onclick();
  e.run("setView('archive')");
  assert.equal(e.get('grid').children.length,1,'archived research stays reachable in Archive');
  e.get('grid').children[0].children[1].children[0].onclick();
  e.run("setView('research')");
  assert.equal(e.get('grid').children.length,2,'Restore returns research to its own category');
}
// #34: an explicit decoder restart can rescue audible output when the iOS
// webview's clock advances but sound has stopped. It does not fabricate time
// listened or invent an automatic audible-output detector.
{
  assert.match(html, /id="recoveraudio"/);
  const e=makeEnvironment();
  e.run("render([{id:'long-audio',origin:'daily_compilation',title:'24 minute briefing',date:'2026-11-09',audio_url:'assets/long.mp3',blocks:[{type:'paragraph',text:'Long evidence-backed report'}]}],'')");
  e.run("openItem('long-audio')");
  e.get('listen').onclick();
  const audio=e.get('player');
  audio.duration=1442.077;
  audio.currentTime=275;
  e.get('recoveraudio').onclick();
  assert.equal(audio.loadCount,2,'recovery resets WebKit media resource twice');
  assert.equal(audio.src,'assets/long.mp3','recovery never changes canonical content');
  assert.match(e.get('nowplaying').textContent,/Reconnecting audio/);
  audio.currentTime=0; // reset by the new decoder
  audio.events.loadedmetadata();
  assert.equal(audio.currentTime,275,'seek returns to interrupted timestamp');
  assert.equal(audio.paused,false,'recovered media resumes after metadata');
  assert.equal(e.run('lastAudioPosition'),null,'seek does not count as listening');
  assert.equal(e.run("isDone('long-audio')"),false,'recovery must not archive a partial listen');
}

// The Research tab also displays pending requests without replacing finished reports.
{
  const e=makeEnvironment();
  e.run("allRequests=[{intent_id:'int_123',title:'Queued investigation',status:'queued'}]");
  e.run("render([{id:'research-complete',title:'Finished research',origin:'user_initiated',source:'Your research',date:'2026-11-09',blocks:[{type:'paragraph',text:'Research'}]}],'')");
  e.run("setView('research')");
  assert.equal(e.get('grid').children.length,3,'report plus queue heading and queued request');
}
// Muse-safe player must be above the host bottom chrome; finger hit targets are
// touch-sized instead of relying on the iOS native tiny audio seek thumb.
{
  assert.match(html, /--muse-chrome-clearance:68px/);
  assert.match(html, /env\(safe-area-inset-bottom,0px\)/);
  assert.match(html, /#seekbar\{[^}]*height:44px/);
  const e=makeEnvironment();
  e.run("render([{id:'mp3',origin:'daily_compilation',title:'Audio briefing',date:'2026-11-09',audio_url:'assets/brief.mp3',blocks:[{type:'paragraph',text:'Brief'}]}],'')");
  e.run("openItem('mp3')");
  e.get('listen').onclick();
  const audio=e.get('player');
  audio.duration=240;
  audio.events.loadedmetadata();
  const slider=e.get('seekbar');
  assert.equal(slider.disabled,false);
  slider.value='500';
  slider.events.input();
  assert.equal(audio.currentTime,120,'touch scrubbing reaches the requested half-way position');
  assert.equal(e.get('elapsed').textContent,'2:00');
  assert.equal(e.get('remaining').textContent,'−2:00');
  e.get('playpause').onclick();
  assert.equal(audio.paused,true,'custom Play/Pause button controls the HTMLAudioElement');
}


// Financial Markdown tables stay semantic and horizontally scrollable on iOS.
{
  assert.match(html, /\.table-scroll\{[^}]*overflow-x:auto/);
  assert.match(html, /aria-label','Scrollable article data table'/);
  const e=makeEnvironment();
  const blocks=[
    {
      type:'table',
      headers:['Item (Q3 2026)','Figure','Notes / comparatives'],
      align:['left','right','left'],
      rows:[
        ['Revenue','**$116k** ($116 thousand)','vs $55k Q3 2025 (+110%; Seeking Alpha calculates +140%)'],
        ['Net loss attributable','**−$20.8M**','vs −$19.527M in the income statement']
      ]
    },
    {type:'paragraph',text:'Figures must remain precisely attributed.'}
  ];
  e.run('renderArticle('+JSON.stringify(blocks)+',"")');
  const wrapper=e.get('articlebody').children[0];
  assert.equal(wrapper.name,'div');
  assert.equal(wrapper.className,'table-scroll');
  assert.equal(wrapper.attributes.role,'region');
  assert.equal(wrapper.attributes['aria-label'],'Scrollable article data table');
  const table=wrapper.children[0];
  assert.equal(table.name,'table');
  const head=table.children[0].children[0];
  assert.equal(head.children[1].name,'th');
  assert.equal(head.children[1].attributes.scope,'col');
  assert.equal(head.children[1].attributes['data-align'],'right');
  const rows=table.children[1].children;
  assert.equal(rows.length,2);
  assert.equal(rows[0].children[1].children.find(n=>n.name==='strong').textContent,'$116k');
  assert.ok(rows[0].children[1].children.some(n=>n.textContent===' ($116 thousand)'));
  assert.equal(rows[1].children[1].children.find(n=>n.name==='strong').textContent,'−$20.8M');
  assert.match(rows[1].children[2].children[0].textContent,/−\$19\.527M/);
  e.run('render([{id:"financial",origin:"user_initiated",source:"Your research",title:"Finance",date:"2026-11-09",blocks:'+JSON.stringify(blocks)+'}],"")');
  const spoken=e.run('readableText(allItems[0])');
  assert.match(spoken,/Item \(Q3 2026\): Revenue; Figure: \$116k/);
  assert.match(spoken,/Notes \/ comparatives: vs \$55k/);
  assert.match(spoken,/Net loss attributable; Figure: −\$20.8M/);
}

console.log('Focu reader behavior: article, local read-aloud, persistence and audio end passed');
