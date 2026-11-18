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

// P2-3 (owner-reported): article tables must never force page-level
// horizontal scrolling at phone widths. The table may be wider than the
// screen, but the overshoot stays inside .table-scroll: the wrapper is a
// full-width block with its own scroll + overscroll containment, the
// layout chain down to it can shrink (min-width:0), the page itself is
// guarded with overflow-x:clip (hidden as the pre-clip fallback), and at
// <=480px cells step down so ordinary tables need less scrolling. A wide
// 8-column table still renders as exactly one wrapped table — never a
// bare <table> directly under #articlebody.
{
  assert.match(html, /html,body\{overflow-x:hidden;overflow-x:clip\}/);
  assert.match(html, /main,#reader,#articlebody\{min-width:0;max-width:100%\}/);
  assert.match(html, /\.table-scroll\{[^}]*display:block/);
  assert.match(html, /\.table-scroll\{[^}]*width:100%/);
  assert.match(html, /\.table-scroll\{[^}]*overscroll-behavior-x:contain/);
  assert.match(html, /\.readeractions\{[^}]*flex-wrap:wrap/);
  const mobileCss=html.slice(html.lastIndexOf('@media(max-width:480px)'));
  assert.match(mobileCss, /#articlebody \.article-table\{font-size:13px\}/);
  assert.match(mobileCss, /article-table th,#articlebody \.article-table td\{min-width:104px/);
  const e=makeEnvironment();
  const wide={
    type:'table',
    headers:['Metric','Q1','Q2','Q3','Change','Notes','Source','Token'],
    align:['left','right','right','right','right','left','left','left'],
    rows:[
      ['Revenue','$116,000','$128,500','$141,250','+21.8%','Consolidated reconciliation','SRC-2026-Q3-0001','abcdefghijklmnopqrstuvwxyz0123456789'],
      ['Net loss','-$20.8M','-$19.5M','-$18.1M','improvement','Income statement appendix','SRC-2026-Q3-0002','abcdefghijklmnopqrstuvwxyz0123456789']
    ]
  };
  e.run('renderArticle('+JSON.stringify([wide])+',\"\")');
  const kids=e.get('articlebody').children;
  assert.equal(kids.length,1,'wide table renders as a single wrapped block');
  assert.equal(kids[0].className,'table-scroll');
  assert.ok(kids.every(n=>n.name!=='table'),'no bare table directly under #articlebody');
  const table=kids[0].children[0];
  assert.equal(table.name,'table');
  assert.equal(table.children[0].children[0].children.length,8,'all 8 columns preserved inside the wrapper');
  assert.equal(table.children[1].children.length,2);
  console.log('Focu reader P2-3: wide tables stay inside .table-scroll; page cannot scroll sideways passed');
}

// P2-4: every article gets a cover. The publisher's procedural PNG
// (origin 'procedural_art') is a real cover and must show in the feed
// card and at the top of the article — unlike the retired 'offline_art'
// typographic SVG placeholders, which existing bundles carry and which
// must keep their previous hidden behaviour.
{
  const findImg=(node)=>{
    if(!node||typeof node!=='object')return null;
    if(node.name==='img'&&node.className==='cover')return node;
    for(const child of node.children||[]){const hit=findImg(child);if(hit)return hit}
    return null;
  };
  const e=makeEnvironment();
  e.run("render(["+
    "{id:'proc-1',origin:'daily_compilation',title:'Procedural story',summary:'',date:'2026-11-18',source:'Focu',cover_url:'assets/covers/proc.png',cover_origin:'procedural_art',covered_content_ids:[],blocks:[{type:'paragraph',text:'Body'}],reading_minutes:1},"+
    "{id:'legacy-1',origin:'daily_compilation',title:'Legacy story',summary:'',date:'2026-11-17',source:'Focu',cover_url:'assets/covers/legacy.svg',cover_origin:'offline_art',covered_content_ids:[],blocks:[{type:'paragraph',text:'Body'}],reading_minutes:1}"+
  "],'')");
  const cards=e.get('grid').children;
  assert.equal(cards.length,2);
  const procImg=findImg(cards[0]);
  assert.ok(procImg,'procedural cover renders on the feed card');
  assert.equal(procImg.src,'assets/covers/proc.png');
  assert.equal(findImg(cards[1]),null,'legacy offline_art placeholder stays hidden on the card');
  e.run("openItem('proc-1')");
  assert.equal(e.get('readercover').hidden,false,'procedural cover shows at the top of the article');
  assert.equal(e.get('readercover').src,'assets/covers/proc.png');
  e.run("openItem('legacy-1')");
  assert.equal(e.get('readercover').hidden,true,'legacy offline_art placeholder stays hidden in the article');
  console.log('Focu reader P2-4: procedural covers show; legacy offline_art stays hidden passed');
}

// Wave-2 (#1): one-tap Play on the card itself plus a duration chip — the
// daily briefing must start without opening the article or scrolling.
{
  assert.match(html, /function playItem\(item\)/);
  const e=makeEnvironment();
  e.run("render([{id:'daily-1',origin:'daily_compilation',title:'Daily briefing',summary:'',date:'2026-11-09',source:'Focu',audio_url:'media/briefing.mp3',audio_duration:1442,covered_content_ids:[],blocks:[{type:'paragraph',text:'Daily report'}],reading_minutes:5}],'')");
  const card=e.get('grid').children[0];
  const body=card.children[0].children[0];
  const chip=body.children.find(n=>n.className==='cardmeta costchip');
  assert.ok(chip,'audio card carries a cost chip');
  assert.equal(chip.textContent,'▶ 24 min');
  const play=card.children[1].children[0];
  assert.equal(play.textContent,'▶ Play','first control on an audio card is Play');
  assert.equal(card.children[1].children[1].textContent,'Archive');
  play.onclick({preventDefault(){},stopPropagation(){}});
  assert.equal(e.run('playingId'),'daily-1');
  assert.equal(e.run('currentId'),null,'card Play does not open the reader');
  assert.equal(e.get('playerbar').hidden,false,'player bar appears on card Play');
  assert.equal(e.get('player').src,'media/briefing.mp3');
  assert.equal(e.get('player').paused,false);
}
// Wave-2 (#2): a text-only card prices itself in reading minutes and offers
// no phantom Play control.
{
  const e=makeEnvironment();
  e.run("render([{id:'text-1',origin:'user_initiated',title:'Text report',summary:'',date:'2026-11-09',source:'Your research',audio_url:'',blocks:[{type:'paragraph',text:'Evidence'}],reading_minutes:4}],'')");
  e.run("setView('research')");
  const card=e.get('grid').children[0];
  const body=card.children[0].children[0];
  const chip=body.children.find(n=>n.className==='cardmeta costchip');
  assert.ok(chip,'text card carries a cost chip');
  assert.equal(chip.textContent,'4 min read');
  assert.equal(card.children[1].children.some(n=>String(n.className).includes('play-action')),false,'no Play control without audio');
  assert.equal(card.children[1].children.length,3,'Archive plus the quiet Not for me and Useful actions (waves 5 and 6)');
  assert.equal(card.children[1].children[0].textContent,'Archive');
  assert.equal(card.children[1].children[1].textContent,'Not for me');
  assert.equal(card.children[1].children[2].textContent,'Useful');
}
// Wave-2 (#3): a saved position turns the card button into Continue with the
// remaining time, and playback resumes at that position after a reload.
{
  const saved={'focu:content-consumption:v1':JSON.stringify({'long-audio':{audio_pos:275}})};
  const e=makeEnvironment(saved);
  e.run("render([{id:'long-audio',origin:'daily_compilation',title:'24 minute briefing',date:'2026-11-09',source:'Focu',audio_url:'assets/long.mp3',audio_duration:1442,covered_content_ids:[],blocks:[{type:'paragraph',text:'Long report'}]}],'')");
  const play=e.get('grid').children[0].children[1].children[0];
  assert.equal(play.textContent,'▸ Continue · 19:27 left');
  play.onclick({preventDefault(){},stopPropagation(){}});
  const audio=e.get('player');
  audio.duration=1442.077;
  audio.events.loadedmetadata();
  assert.equal(audio.currentTime,275,'playback resumes at the saved position');
  assert.match(e.get('nowplaying').textContent,/Resumed at 4:35/);
}
// Wave-2 (#3): pausing persists the position into the same consumption store,
// and a fresh environment (reload) offers Continue from it.
{
  const e=makeEnvironment();
  e.run("render([{id:'ep',origin:'daily_compilation',title:'Episode',date:'2026-11-09',source:'Focu',audio_url:'assets/ep.mp3',audio_duration:1442,covered_content_ids:[],blocks:[{type:'paragraph',text:'Report'}]}],'')");
  e.get('grid').children[0].children[1].children[0].onclick({preventDefault(){},stopPropagation(){}});
  const audio=e.get('player');
  audio.duration=1442.077;
  audio.currentTime=120;
  audio.events.pause();
  assert.equal(JSON.parse(e.storage['focu:content-consumption:v1'])['ep'].audio_pos,120,'pause persists position');
  const reloaded=makeEnvironment(e.storage);
  reloaded.run("render([{id:'ep',origin:'daily_compilation',title:'Episode',date:'2026-11-09',source:'Focu',audio_url:'assets/ep.mp3',audio_duration:1442,covered_content_ids:[],blocks:[{type:'paragraph',text:'Report'}]}],'')");
  assert.match(reloaded.get('grid').children[0].children[1].children[0].textContent,/Continue · 22:02 left/);
  // A position at the very end is finished, not a resume point.
  audio.currentTime=1441.5;
  e.run('saveAudioPosition(true)');
  assert.equal(JSON.parse(e.storage['focu:content-consumption:v1'])['ep'].audio_pos,undefined,'near-end position clears instead of saving');
}
// Wave-2 (#3): article scroll position persists across a reload, not only
// across in-session tab switches.
{
  const e=makeEnvironment();
  e.run('render(['+article('scroll-story')+'],"")');
  e.run("openItem('scroll-story')");
  e.run('scrollY=280');
  e.run("setView('briefing')");
  assert.equal(JSON.parse(e.storage['focu:content-consumption:v1'])['scroll-story'].article_pos,280,'article position persisted');
  const reloaded=makeEnvironment(e.storage);
  reloaded.run('render(['+article('scroll-story')+'],"")');
  reloaded.run("openItem('scroll-story')");
  assert.equal(reloaded.run('scrollY'),280,'article position restored after reload');
}

// Wave-3 (#6): the Recover control is not part of the resting player bar,
// and the standard podcast skip controls exist.
{
  assert.match(html, /id="recoveraudio"[^>]*hidden/);
  assert.match(html, /#recoveraudio\[hidden\]\{display:none!important\}/);
  assert.match(html, /id="skipback"/);
  assert.match(html, /id="skipfwd"/);
  assert.doesNotMatch(html, /Please report this playback problem/);
  assert.doesNotMatch(html, /Player duration differs from verified audio/);
}
// Wave-3 (#6): skip buttons move in coarse 15s / 30s steps and clamp at the
// ends, replacing fine-motor slider scrubbing while listening.
{
  const e=makeEnvironment();
  e.run("render([{id:'skip-ep',origin:'daily_compilation',title:'Episode',date:'2026-11-09',source:'Focu',audio_url:'assets/ep.mp3',audio_duration:300,covered_content_ids:[],blocks:[{type:'paragraph',text:'Report'}]}],'')");
  e.get('grid').children[0].children[1].children[0].onclick({preventDefault(){},stopPropagation(){}});
  const audio=e.get('player');
  audio.duration=300;audio.currentTime=100;
  e.get('skipfwd').onclick();
  assert.equal(audio.currentTime,130,'forward skip adds 30 seconds');
  e.get('skipback').onclick();
  assert.equal(audio.currentTime,115,'back skip subtracts 15 seconds');
  audio.currentTime=290;
  e.get('skipfwd').onclick();
  assert.equal(audio.currentTime,300,'forward skip clamps at the end');
  audio.currentTime=10;
  e.get('skipback').onclick();
  assert.equal(audio.currentTime,0,'back skip clamps at the start');
}
// Wave-3 (#6): a stall triggers one automatic decoder recovery; only a
// second stall without progress reveals the manual Recover button.
{
  const e=makeEnvironment();
  e.run("render([{id:'stall-ep',origin:'daily_compilation',title:'Episode',date:'2026-11-09',source:'Focu',audio_url:'assets/ep.mp3',audio_duration:1442,covered_content_ids:[],blocks:[{type:'paragraph',text:'Report'}]}],'')");
  e.get('grid').children[0].children[1].children[0].onclick({preventDefault(){},stopPropagation(){}});
  const audio=e.get('player');
  audio.duration=1442.077;audio.currentTime=275;
  assert.equal(e.get('recoveraudio').hidden,true,'recover hidden while playback is healthy');
  audio.events.stalled();
  assert.equal(audio.loadCount,2,'first stall auto-recovers the decoder');
  assert.match(e.get('nowplaying').textContent,/Audio glitch/);
  assert.equal(e.get('recoveraudio').hidden,true,'auto-recovery does not surface the repair button');
  audio.events.loadedmetadata(); // recovery completes and resumes at 275
  audio.events.stalled();
  assert.equal(audio.loadCount,2,'second stall does not loop the decoder reset');
  assert.equal(e.get('recoveraudio').hidden,false,'second stall reveals the manual control');
  e.get('recoveraudio').onclick();
  assert.equal(audio.loadCount,4,'manual recovery resets the decoder again');
  assert.equal(e.get('recoveraudio').hidden,true,'manual recovery hides the button again');
}

// Wave-3 (#4): no manual refresh control exists and the status line rests
// hidden — freshness is automated, plumbing is not UI.
{
  assert.doesNotMatch(html, /id="refresh"/);
  assert.match(html, /id="status"[^>]*hidden/);
  assert.match(html, /#status\[hidden\]\{display:none!important\}/);
  const e=makeEnvironment();
  assert.equal(e.run("noteContentChange(new Set(['a','b']),[{id:'a'}])"),false,'no new item, no announcement');
  assert.equal(e.run("noteContentChange(new Set(['a']),[{id:'a'},{id:'c'}])"),true,'a new item is a change worth one line');
}
// Wave-3 (#4): a successful load leaves the status line hidden; new content
// on a later load announces itself once; stale data reloads on visibility.
(async()=>{
  const e=makeEnvironment();
  e.get('embedded-episodes').textContent='{"episodes":[]}';
  await e.run('load()');
  assert.equal(e.get('status').hidden,true,'status rests hidden after a successful load');
  assert.equal(e.run('reloadIfStale()'),false,'fresh data does not reload when the app becomes visible');
  e.get('embedded-episodes').textContent=JSON.stringify({episodes:[{id:'fresh-1',title:'Fresh briefing',origin:'daily_compilation',date:'2026-11-10',source:'Focu',blocks:[{type:'paragraph',text:'New'}]}]});
  await e.run('load()');
  assert.equal(e.get('status').hidden,false,'new content surfaces the one-line announcement');
  assert.equal(e.get('status').textContent,'New briefing ready');
  e.run('lastLoadAt=Date.now()-6*60*1000');
  const triggered=e.run('reloadIfStale()');
  assert.notEqual(triggered,false,'stale data triggers a reload when the app becomes visible');
  await triggered;
  assert.ok(e.run('Date.now()-lastLoadAt<10000'),'the reload refreshes the freshness stamp');
  console.log('Focu reader wave-3 (#4): auto-refresh and quiet status passed');
})().catch(err=>{console.error(err);process.exit(1)});

// Wave-3 (#7): inside an opened article, understanding starts immediately —
// title, summary and the Listen toolbar all precede the cover, and the cover
// is demoted to a 160px band instead of a 340px first screen.
{
  const titleAt=html.indexOf('id="readertitle"'),summaryAt=html.indexOf('id="readersummary"'),toolbarAt=html.indexOf('id="toolbar"'),coverAt=html.indexOf('id="readercover"');
  assert.ok(titleAt>-1&&summaryAt>titleAt&&toolbarAt>summaryAt&&coverAt>toolbarAt,'reader order is title, summary, Listen, then cover');
  assert.match(html, /\.readercover\{[^}]*max-height:160px/);
  const e=makeEnvironment();
  e.run('render(['+article('order-story')+'],"")');
  e.run("openItem('order-story')");
  assert.equal(e.get('readertitle').textContent,'A grounded research story','reader still opens normally after the reorder');
  assert.equal(e.get('reader').hidden,false);
}

// Wave-3 (#8): un-compiled sources rest behind one collapsed row in the
// Daily Briefing tab — reachable in one tap, never at full card weight.
{
  const e=makeEnvironment();
  e.run("render(["+
    "{id:'daily-1',origin:'daily_compilation',title:'Today briefing',date:'2026-11-10',source:'Focu',covered_content_ids:[],blocks:[{type:'paragraph',text:'Compiled'}]},"+
    "{id:'src-1',origin:'registered_source',title:'Raw source one',date:'2026-11-10',source:'Anthropic',blocks:[{type:'paragraph',text:'Raw'}]},"+
    "{id:'src-2',origin:'registered_source',title:'Raw source two',date:'2026-11-09',source:'OpenAI',blocks:[{type:'paragraph',text:'Raw'}]}"+
  "],'')");
  const kids=e.get('grid').children;
  assert.equal(kids.length,2,'briefing card plus one collapsed row, no full-weight source cards');
  const toggle=kids[1];
  assert.equal(toggle.name,'button');
  assert.match(toggle.textContent,/2 source updates not yet in a briefing/);
  assert.equal(toggle.attributes['aria-expanded'],'false');
  toggle.onclick();
  const open=e.get('grid').children;
  assert.equal(open.length,4,'expanding reveals both source cards in place');
  assert.equal(open[1].attributes['aria-expanded'],'true');
  e.run("render(allItems,'')");
  assert.equal(e.get('grid').children.length,4,'expansion survives a re-render');
  e.get('grid').children[1].onclick();
  assert.equal(e.get('grid').children.length,2,'collapsing returns the tab to one line');
}

// Wave-4 (#5): the glance layer. A card whose payload carries a pipeline
// gist shows the gist as its single text line — never the clamped summary —
// while the summary stays available at scan level in the reader.
{
  assert.match(html, /gist:typeof x\.gist==='string'\?x\.gist:''/);
  assert.match(html, /\.feedgist\{[^}]*\}/);
  assert.doesNotMatch(html, /\.feedgist\{[^}]*line-clamp/);
  const e=makeEnvironment();
  e.run("render([{id:'gist-1',origin:'user_initiated',title:'Gisted report',summary:'A long scan summary that the card used to clamp at two lines mid-thought, hiding most of its meaning behind a silent cut.',gist:'Pando ships persistent memory for agents.',date:'2026-11-10',source:'Your research',audio_url:'',blocks:[{type:'paragraph',text:'Evidence'}],reading_minutes:3}],'')");
  e.run("setView('research')");
  const body=e.get('grid').children[0].children[0].children[0];
  const gist=body.children.find(n=>n.className==='feedgist');
  assert.ok(gist,'card renders the gist line');
  assert.equal(gist.textContent,'Pando ships persistent memory for agents.');
  assert.equal(body.children.find(n=>n.className==='feedsummary'),undefined,'clamped summary is not rendered next to a gist');
  e.run("openItem('gist-1')");
  assert.match(e.get('readersummary').textContent,/clamp at two lines/,'the summary remains the reader scan layer');
}
// Wave-4 (#5): legacy payloads without a gist render exactly as before —
// the clamped summary, and no empty glance line.
{
  const e=makeEnvironment();
  e.run("render([{id:'legacy-1',origin:'user_initiated',title:'Legacy report',summary:'The only text a legacy bundle carries for the card.',date:'2026-11-09',source:'Your research',audio_url:'',blocks:[{type:'paragraph',text:'Evidence'}],reading_minutes:2}],'')");
  e.run("setView('research')");
  const body=e.get('grid').children[0].children[0].children[0];
  assert.equal(body.children.find(n=>n.className==='feedgist'),undefined,'no gist element for a legacy item');
  const summary=body.children.find(n=>n.className==='feedsummary');
  assert.ok(summary,'legacy card keeps its summary');
  assert.equal(summary.textContent,'The only text a legacy bundle carries for the card.');
}
// Wave-4 (#5): normalize carries gist through from a published payload and
// defaults it to empty for gist-less (pre-change) bundles, so old bundles
// keep rendering their summaries and new ones lead with the gist.
(async()=>{
  const e=makeEnvironment();
  e.get('embedded-episodes').textContent=JSON.stringify({items:[
    {content_id:'new-1',title:'New bundle item',origin:'daily_compilation',date:'2026-11-10',source:'Focu',gist:'A complete glance line.',summary:'Scan text',article_blocks:[{type:'paragraph',text:'Body'}]},
    {content_id:'old-1',title:'Old bundle item',origin:'daily_compilation',date:'2026-11-09',source:'Focu',summary:'Legacy scan text',article_blocks:[{type:'paragraph',text:'Body'}]}
  ]});
  await e.run('load()');
  assert.equal(e.run("allItems.find(x=>x.id==='new-1').gist"),'A complete glance line.');
  assert.equal(e.run("allItems.find(x=>x.id==='old-1').gist"),'','legacy payload normalizes to an empty gist');
  const bodies=e.get('grid').children.map(c=>c.children[0].children[0]);
  assert.ok(bodies[0].children.find(n=>n.className==='feedgist'),'new item card leads with its gist');
  assert.ok(bodies[1].children.find(n=>n.className==='feedsummary'),'old item card falls back to its summary');
  console.log('Focu reader wave-4 (#5): glance gist layer passed');
})().catch(err=>{console.error(err);process.exit(1)});

// Wave-5 (Learning Phase 2): "Not for me" is a distinct negative act, not
// a flavor of Archive. From a card it removes the item from the feed
// WITHOUT a consumed status, records the mark with the item's source and
// a timestamp in the same consumption store, rests in Archive, and is
// fully reversed by Restore (which deletes the store entry, wave-2
// semantics — positions and marks alike).
{
  assert.match(html, /id="readernotforme"/);
  assert.match(html, /function markNotForMe\(id\)/);
  const e=makeEnvironment();
  e.run('render(['+article('nfm-card')+'],"")');
  const card=e.get('grid').children[0];
  const controls=card.children[1].children;
  assert.equal(controls[0].textContent,'Archive');
  const nfm=controls.find(n=>n.textContent==='Not for me');
  assert.ok(nfm,'card carries the quiet Not for me action beside Archive');
  assert.equal(nfm.className,'quiet-action','the action is visually quiet, not a gamified button');
  let prevented=false,stopped=false;
  nfm.onclick({preventDefault(){prevented=true},stopPropagation(){stopped=true}});
  assert.equal(prevented,true,'tap should not bubble into the story opener');
  assert.equal(stopped,true);
  assert.equal(card.hidden,true,'card hides synchronously on tap');
  assert.equal(e.run("isDone('nfm-card')"),false,'not for me is not consumption');
  assert.equal(e.run("isNotForMe('nfm-card')"),true);
  const entry=JSON.parse(e.storage['focu:content-consumption:v1'])['nfm-card'];
  assert.equal(entry.status,undefined,'no consumed status is written');
  assert.equal(entry.not_for_me.source,'Your research','the mark records the item source');
  assert.ok(Number.isFinite(Date.parse(entry.not_for_me.at)),'the mark records a timestamp');
  assert.equal(e.get('grid').children.length,1,'feed now shows only the empty state');
  assert.equal(makeEnvironment(e.storage).run("isNotForMe('nfm-card')"),true,'the mark survives a reload');
  e.run("setView('archive')");
  assert.equal(e.get('grid').children.length,1,'the dismissed item rests in Archive');
  const restore=e.get('grid').children[0].children[1].children[0];
  assert.equal(restore.textContent,'Restore');
  restore.onclick();
  assert.equal(e.run("isNotForMe('nfm-card')"),false,'Restore clears the not-for-me mark');
  assert.equal(JSON.parse(e.storage['focu:content-consumption:v1'])['nfm-card'],undefined,'Restore removes the whole store entry');
  e.run("setView('briefing')");
  assert.equal(e.get('grid').children[0].children[0].children[0].children[1].textContent,'A grounded research story','restored item returns to the feed');
}
// Wave-5 (Learning Phase 2): the same act inside the article view — it
// closes the reader like Archive does, and a marked item opened from
// Archive offers Restore instead of a second Archive / Not for me.
{
  const e=makeEnvironment();
  e.run('render(['+article('nfm-reader')+'],"")');
  e.run("openItem('nfm-reader')");
  assert.equal(e.get('readernotforme').hidden,false,'article view offers Not for me');
  assert.equal(e.get('readerarchive').hidden,false);
  e.get('readernotforme').onclick();
  assert.equal(e.run("isDone('nfm-reader')"),false,'reader Not for me does not consume');
  assert.equal(e.run("isNotForMe('nfm-reader')"),true);
  assert.equal(e.get('reader').hidden,true,'not for me closes the reader');
  e.run("setView('archive')");
  e.run("openItem('nfm-reader')");
  assert.equal(e.get('restore').hidden,false,'a not-for-me item in the reader offers Restore');
  assert.equal(e.get('readerarchive').hidden,true,'no Archive on a dismissed item');
  assert.equal(e.get('readernotforme').hidden,true,'no second Not for me on a marked item');
  assert.equal(e.get('readerstate').textContent,'Not for me · Saved in Archive');
  e.get('restore').onclick();
  assert.equal(e.run("isNotForMe('nfm-reader')"),false,'reader Restore clears the mark');
  assert.equal(e.get('readerarchive').hidden,false,'unmarked item offers Archive again');
}
// Wave-5 (Learning Phase 2): the Archive view carries the one deliberate
// export control, and only there — Today and Research gain no chrome.
{
  const e=makeEnvironment();
  e.run('render(['+article('foot-1')+'],"")');
  assert.equal(e.get('archivefoot').hidden,true,'no export control in the briefing view');
  e.run("setView('research')");
  assert.equal(e.get('archivefoot').hidden,true,'no export control in the research view');
  e.run("setView('archive')");
  assert.equal(e.get('archivefoot').hidden,false,'the export control rests in the Archive view');
  assert.match(html, /id="exportsummary"[^>]*>Share reading summary</,'the control carries the design name for the action');
}
// Wave-5 (Learning Phase 2): the export itself. buildReadingSummary is a
// pure shaping of the consumption store (plus each item's source from the
// reader's item data); it runs in this environment whose fetch throws on
// any call, and neither export function's source touches the network.
{
  assert.match(html, /id="exportsummary"/);
  assert.match(html, /focu-reading-summary/);
  const e=makeEnvironment();
  e.run("render(["+
    "{id:'exp-audio',origin:'daily_compilation',title:'Listened briefing',date:'2026-11-10',source:'Focu',audio_url:'assets/a.mp3',audio_duration:600,covered_content_ids:[],blocks:[{type:'paragraph',text:'A'}]},"+
    "{id:'exp-manual',origin:'user_initiated',title:'Archived by hand',date:'2026-11-10',source:'Your research',blocks:[{type:'paragraph',text:'B'}]},"+
    "{id:'exp-nfm',origin:'registered_source',title:'Dismissed source piece',date:'2026-11-10',source:'Anthropic',blocks:[{type:'paragraph',text:'C'}]},"+
    "{id:'exp-partial',origin:'daily_compilation',title:'Half heard',date:'2026-11-10',source:'Focu',audio_url:'assets/d.mp3',audio_duration:900,covered_content_ids:[],blocks:[{type:'paragraph',text:'D'}]}"+
  "],'')");
  e.run("markDone('exp-audio','audio')");
  e.run("markDone('exp-manual','manual')");
  e.run("markNotForMe('exp-nfm')");
  e.run("writePos('exp-partial',{audio_pos:275})");
  const summary=JSON.parse(e.run('JSON.stringify(buildReadingSummary())'));
  assert.equal(summary.format,'focu-reading-summary');
  assert.equal(summary.version,1);
  assert.ok(Number.isFinite(Date.parse(summary.exported_at)),'export carries its own timestamp');
  assert.deepEqual(summary.items.map(x=>x.content_id),['exp-audio','exp-manual','exp-nfm','exp-partial'],'items sorted by content_id');
  const byId={};for(const item of summary.items)byId[item.content_id]=item;
  assert.deepEqual(Object.keys(byId['exp-audio']).sort(),['archived','article_pos_px','audio','audio_pos_seconds','content_id','not_for_me','source','status','updated_at','useful','via'],'the per-item key set is exactly the documented format (useful added in wave 6, additively within version 1)');
  assert.equal(byId['exp-audio'].status,'consumed');
  assert.equal(byId['exp-audio'].via,'audio');
  assert.equal(byId['exp-audio'].audio,'completed','a finished listen summarizes as completed');
  assert.equal(byId['exp-audio'].audio_pos_seconds,null,'a completed entry carries no stale position');
  assert.equal(byId['exp-audio'].archived,true);
  assert.equal(byId['exp-audio'].source,'Focu');
  assert.equal(byId['exp-audio'].not_for_me,null);
  assert.equal(byId['exp-audio'].useful,null,'an unendorsed item exports useful as null');
  assert.ok(Number.isFinite(Date.parse(byId['exp-audio'].updated_at)));
  assert.equal(byId['exp-manual'].status,'consumed');
  assert.equal(byId['exp-manual'].via,'manual','manual archive stays distinguishable from real consumption');
  assert.equal(byId['exp-nfm'].status,'not_for_me');
  assert.equal(byId['exp-nfm'].via,null,'a dismissal claims no consumption route');
  assert.equal(byId['exp-nfm'].not_for_me.source,'Anthropic','the dismissal keeps its source attribution');
  assert.ok(Number.isFinite(Date.parse(byId['exp-nfm'].not_for_me.at)));
  assert.equal(byId['exp-nfm'].archived,true,'a dismissed item rests in Archive');
  assert.equal(byId['exp-partial'].status,'in_progress','a positions-only entry is in progress, not consumed');
  assert.equal(byId['exp-partial'].audio,'partial','a saved position summarizes as partial');
  assert.equal(byId['exp-partial'].audio_pos_seconds,275);
  assert.equal(byId['exp-partial'].archived,false);
  assert.doesNotMatch(e.run('buildReadingSummary.toString()'),/fetch\(|XMLHttpRequest/,'the builder performs no network I/O');
  assert.doesNotMatch(e.run('exportReadingSummary.toString()'),/fetch\(|XMLHttpRequest/,'the export trigger performs no network I/O');
  console.log('Focu reader wave-5 (Learning Phase 2): not-for-me act and reading summary export passed');
}

// Wave-6 (Learning Phase 2): "Useful" completes the signal pair — the
// only mark that may ever support promoting a source (promotion requires
// the owner's own useful marks; completion can never promote). From a
// card it is a pure signal: the item is NOT consumed and NOT hidden, the
// mark is recorded with the item's source and a timestamp in the same
// consumption store, the action re-renders as a muted "Useful ✓", and
// re-tapping is a strict no-op — the first mark's timestamp stands, so
// exactly one mark per item ever reaches the export.
{
  assert.match(html, /id="readeruseful"/);
  assert.match(html, /function markUseful\(id\)/);
  const e=makeEnvironment();
  e.run('render(['+article('use-card')+'],"")');
  const controls=e.get('grid').children[0].children[1].children;
  const use=controls.find(n=>n.textContent==='Useful');
  assert.ok(use,'card carries the quiet Useful action beside Archive and Not for me');
  assert.equal(use.className,'quiet-action','the positive act is as quiet as the negative one');
  let prevented=false,stopped=false;
  use.onclick({preventDefault(){prevented=true},stopPropagation(){stopped=true}});
  assert.equal(prevented,true,'tap should not bubble into the story opener');
  assert.equal(stopped,true);
  assert.equal(e.run("isUseful('use-card')"),true);
  assert.equal(e.run("isDone('use-card')"),false,'useful is not consumption');
  assert.equal(e.run("isNotForMe('use-card')"),false);
  const entry=JSON.parse(e.storage['focu:content-consumption:v1'])['use-card'];
  assert.equal(entry.status,undefined,'no consumed status is written');
  assert.equal(entry.useful.source,'Your research','the mark records the item source');
  assert.ok(Number.isFinite(Date.parse(entry.useful.at)),'the mark records a timestamp');
  assert.equal(e.get('grid').children.length,1,'the marked item remains in the feed');
  assert.equal(e.get('grid').children[0].hidden,false,'the card was never hidden');
  const marked=e.get('grid').children[0].children[1].children.find(n=>n.textContent==='Useful ✓');
  assert.ok(marked,'the action shows the registered mark, muted and without fanfare');
  const firstAt=entry.useful.at;
  marked.onclick({preventDefault(){},stopPropagation(){}});
  const again=JSON.parse(e.storage['focu:content-consumption:v1'])['use-card'];
  assert.equal(again.useful.at,firstAt,'re-marking is a no-op: the first timestamp stands');
  assert.equal(makeEnvironment(e.storage).run("isUseful('use-card')"),true,'the mark survives a reload');
}
// Wave-6 (Learning Phase 2): the same act inside the article view — it
// neither closes the reader nor consumes, it stays offered after the
// item is finished (endorsement after reading is the signal's strongest
// form), finishing an endorsed item does not erase the mark, and a
// dismissed item cannot be endorsed (Restore is its only way back).
{
  const e=makeEnvironment();
  e.run('render(['+article('use-reader')+'],"")');
  e.run("openItem('use-reader')");
  assert.equal(e.get('readeruseful').hidden,false,'article view offers Useful');
  assert.equal(e.get('readeruseful').textContent,'Useful');
  e.get('readeruseful').onclick();
  assert.equal(e.run("isUseful('use-reader')"),true);
  assert.equal(e.run("isDone('use-reader')"),false,'reader Useful does not consume');
  assert.equal(e.get('reader').hidden,false,'Useful does not close the reader');
  assert.equal(e.get('readeruseful').textContent,'Useful ✓','the toolbar shows the registered mark');
  e.run("markDone('use-reader','article')");
  const entry=JSON.parse(e.storage['focu:content-consumption:v1'])['use-reader'];
  assert.equal(entry.status,'consumed');
  assert.ok(entry.useful&&entry.useful.source==='Your research','consumption preserves the useful mark');
  assert.equal(e.get('readeruseful').hidden,false,'a finished item still offers Useful');
  const e2=makeEnvironment();
  e2.run('render(['+article('use-after')+'],"")');
  e2.run("markDone('use-after','manual')");
  e2.run("openItem('use-after')");
  assert.equal(e2.get('readeruseful').hidden,false,'Useful is offered on a finished item');
  e2.get('readeruseful').onclick();
  const after=JSON.parse(e2.storage['focu:content-consumption:v1'])['use-after'];
  assert.equal(after.status,'consumed','endorsing a finished item keeps its consumed status');
  assert.equal(after.via,'manual');
  assert.ok(after.useful,'the endorsement lands on the consumed entry');
  const e3=makeEnvironment();
  e3.run('render(['+article('use-nfm')+'],"")');
  e3.run("markNotForMe('use-nfm')");
  e3.run("setView('archive')");
  e3.run("openItem('use-nfm')");
  assert.equal(e3.get('readeruseful').hidden,true,'no Useful on a dismissed item');
  e3.run("markUseful('use-nfm')");
  assert.equal(e3.run("isUseful('use-nfm')"),false,'a dismissed item refuses the mark');
}
// Wave-6 (Learning Phase 2): the export carries the useful mark as an
// additive version-1 field, orthogonal to status — an endorsed-but-unread
// item exports as in_progress with the mark attached and stays out of
// Archive; a consumed AND endorsed item keeps both facts. (Exports
// written before this act existed simply omit the key; the format
// comment in index.html pins that ingest reads a missing key as null.)
{
  const e=makeEnvironment();
  e.run("render(["+
    "{id:'exp-useful',origin:'user_initiated',title:'Endorsed, unread',date:'2026-11-10',source:'Anthropic',blocks:[{type:'paragraph',text:'E'}]},"+
    "{id:'exp-both',origin:'user_initiated',title:'Read and endorsed',date:'2026-11-10',source:'OpenAI',blocks:[{type:'paragraph',text:'F'}]}"+
  "],'')");
  e.run("markUseful('exp-useful')");
  e.run("markUseful('exp-both')");
  e.run("markDone('exp-both','article')");
  const summary=JSON.parse(e.run('JSON.stringify(buildReadingSummary())'));
  assert.equal(summary.version,1,'the useful field does not bump the format version');
  const byId={};for(const item of summary.items)byId[item.content_id]=item;
  assert.equal(byId['exp-useful'].status,'in_progress','an endorsed-only entry is neither consumed nor dismissed');
  assert.equal(byId['exp-useful'].archived,false,'an endorsed item stays in the feed, out of Archive');
  assert.equal(byId['exp-useful'].useful.source,'Anthropic','the endorsement keeps its source attribution');
  assert.ok(Number.isFinite(Date.parse(byId['exp-useful'].useful.at)));
  assert.equal(byId['exp-both'].status,'consumed');
  assert.ok(byId['exp-both'].useful&&byId['exp-both'].useful.source==='OpenAI','consumption and endorsement travel together');
  console.log('Focu reader wave-6 (Learning Phase 2): useful act and export field passed');
}

// Wave-7 (PM sweep F1): the export carries a compilation's covered unit
// ids so ingest can fan a briefing mark out to the covered sources —
// without them, a mark on the daily briefing (the owner's main surface)
// could never be attributed, since a compilation id is not a unit id.
// The field is additive within version 1 and present ONLY on items that
// actually cover units; every other item's export is byte-for-byte the
// shape waves 5 and 6 pinned (the wave-5 exact key set above stands).
{
  const e=makeEnvironment();
  e.run("render(["+
    "{id:'exp-brief',origin:'daily_compilation',title:'Compiled briefing',date:'2026-11-10',source:'Focu',audio_url:'assets/b.mp3',audio_duration:900,covered_content_ids:['unit-a','unit-b','unit-c'],blocks:[{type:'paragraph',text:'G'}]},"+
    "{id:'exp-plain',origin:'registered_source',title:'Standalone piece',date:'2026-11-10',source:'Anthropic',blocks:[{type:'paragraph',text:'H'}]}"+
  "],'')");
  e.run("markNotForMe('exp-brief')");
  e.run("markUseful('exp-plain')");
  const summary=JSON.parse(e.run('JSON.stringify(buildReadingSummary())'));
  assert.equal(summary.version,1,'covered ids do not bump the format version');
  const byId={};for(const item of summary.items)byId[item.content_id]=item;
  assert.deepEqual(byId['exp-brief'].covered_content_ids,['unit-a','unit-b','unit-c'],'a compilation exports the units it covered');
  assert.equal(byId['exp-brief'].status,'not_for_me','the mark itself travels as before');
  assert.ok(!('covered_content_ids' in byId['exp-plain']),'a non-compilation item omits the key — its export is unchanged');
  console.log('Focu reader wave-7 (F1): compilation covered ids in the export passed');
}

// Wave-8 (PM sweep F4): the ladder's top rung. Every lower rung is served
// by the reader — gist, summary, clean article — but the original itself
// was unreachable: normalize dropped the origin URL and no surface linked
// out. Now publish passes the delivery's source_url through as
// original_url, normalize carries it, and the ARTICLE VIEW shows exactly
// one quiet "Original" door when the item's data carries one. Cards gain
// nothing — the door lives at the point of the full read, not in triage.
(async()=>{
  assert.match(html, /<a id="readeroriginal" class="card-action"[^>]*>Original<\/a>/,'the toolbar carries exactly one Original door, labelled as such');
  const e=makeEnvironment();
  e.get('embedded-episodes').textContent=JSON.stringify({items:[
    {content_id:'orig-1',title:'Source piece',origin:'registered_source',date:'2026-11-10',source:'OpenAI',original_url:'https://example.org/the-original',article_blocks:[{type:'paragraph',text:'Body'}]},
    {content_id:'orig-2',title:'Research piece',origin:'user_initiated',date:'2026-11-10',source:'Your research',article_blocks:[{type:'paragraph',text:'Body'}]}
  ]});
  await e.run('load()');
  assert.equal(e.run("allItems.find(x=>x.id==='orig-1').original_url"),'https://example.org/the-original','normalize carries the origin URL through');
  assert.equal(e.run("allItems.find(x=>x.id==='orig-2').original_url"),'','a payload without the field normalizes to empty');
  e.run("openItem('orig-1')");
  const door=e.get('readeroriginal');
  assert.equal(door.hidden,false,'the article view shows the Original door when the item carries a URL');
  assert.equal(door.href,'https://example.org/the-original','the door points at the item origin URL');
  e.run("openItem('orig-2')");
  assert.equal(e.get('readeroriginal').hidden,true,'no door for an item whose data carries no origin URL');
  console.log('Focu reader wave-8 (F4): the original door in the article view passed');
})().catch(err=>{console.error(err);process.exit(1)});
// Wave-8 (F4): cards are unchanged — an item carrying an origin URL gets
// no new triage control — while a research item whose data carries one
// still gets the door in the article view (the field follows the data,
// not the item class).
{
  const e=makeEnvironment();
  e.run("render([{id:'orig-card',origin:'user_initiated',title:'Research with a source link',summary:'',date:'2026-11-10',source:'Your research',audio_url:'',original_url:'https://example.org/source-thread',blocks:[{type:'paragraph',text:'Evidence'}],reading_minutes:3}],'')");
  e.run("setView('research')");
  const card=e.get('grid').children[0];
  const texts=[];(function walk(n){if(!n||typeof n!=='object')return;if(typeof n.textContent==='string'&&n.textContent)texts.push(n.textContent);(n.children||[]).forEach(walk)})(card);
  assert.ok(!texts.includes('Original'),'no Original control appears on a card');
  assert.deepEqual(card.children[1].children.map(n=>n.textContent),['Archive','Not for me','Useful'],'card actions are exactly the pre-existing three');
  e.run("openItem('orig-card')");
  assert.equal(e.get('readeroriginal').hidden,false,'a research item with a data-carried URL gets the door');
  assert.equal(e.get('readeroriginal').href,'https://example.org/source-thread');
  console.log('Focu reader wave-8 (F4): cards unchanged, data-driven door passed');
}

// Wave-9 (PM sweep N1): a compilation card says what the briefing
// contains at the glance layer. The publisher extracts the gist from
// the agenda (pinned in test_publish), and the card itself renders the
// covered count from covered_content_ids — data the payload already
// carried but no surface showed. Non-compilation cards gain no line.
{
  const e=makeEnvironment();
  e.run("render(["+
    "{id:'daily-n1',origin:'daily_compilation',title:'Daily briefing',summary:'',gist:'Two items today: Pando releases a memory architecture…',date:'2026-11-16',source:'Focu',audio_url:'',covered_content_ids:['unit-a','unit-b'],blocks:[{type:'paragraph',text:'Compiled'}],reading_minutes:5},"+
    "{id:'solo-n1',origin:'daily_compilation',title:'Single-item briefing',summary:'',date:'2026-11-15',source:'Focu',audio_url:'',covered_content_ids:['unit-c'],blocks:[{type:'paragraph',text:'Compiled'}],reading_minutes:2}"+
  "],'')");
  const first=e.get('grid').children[0].children[0].children[0];
  const count=first.children.find(n=>n.className==='cardmeta coveredcount');
  assert.ok(count,'compilation card carries a covered-count line');
  assert.equal(count.textContent,'2 items','the count comes from covered_content_ids');
  const second=e.get('grid').children[1].children[0].children[0];
  assert.equal(second.children.find(n=>n.className==='cardmeta coveredcount').textContent,'1 item','a single covered item reads as 1 item');
  const e2=makeEnvironment();
  e2.run("render([{id:'plain-n1',origin:'user_initiated',title:'Standalone report',summary:'',date:'2026-11-16',source:'Your research',audio_url:'',blocks:[{type:'paragraph',text:'Evidence'}],reading_minutes:2}],'')");
  e2.run("setView('research')");
  const body=e2.get('grid').children[0].children[0].children[0];
  assert.equal(body.children.find(n=>n.className==='cardmeta coveredcount'),undefined,'no covered-count line on a non-compilation card');
  console.log('Focu reader wave-9 (N1): compilation cards state their covered count passed');
}
// Wave-9 (PM sweep N2): the recorded source name reaches the triage
// surface. publish passes a delivery's content.json source_name through
// as the item's source (pinned in test_publish); normalize already
// carried x.source, so this proves the name lands on an uncovered
// card's meta line and on the opened item's byline — the reader needed
// no change, and the test is the proof.
(async()=>{
  const e=makeEnvironment();
  e.get('embedded-episodes').textContent=JSON.stringify({items:[
    {content_id:'named-1',title:'Uncovered source piece',origin:'registered_source',date:'2026-11-16',source:'OpenAI Official',article_blocks:[{type:'paragraph',text:'Body'}]}
  ]});
  await e.run('load()');
  assert.equal(e.run("allItems.find(x=>x.id==='named-1').source"),'OpenAI Official','normalize passes the recorded source name through');
  const toggle=e.get('grid').children.find(n=>n.className==='sourcestoggle');
  assert.ok(toggle,'the uncovered item rests behind the collapsed row');
  toggle.onclick();
  const card=e.get('grid').children.find(n=>n.className==='feedcard');
  assert.ok(card,'expanding the row reveals the source card');
  assert.match(card.children[0].children[0].children[0].textContent,/OpenAI Official/,'the card meta line names the real source');
  e.run("openItem('named-1')");
  assert.match(e.get('readerbyline').textContent,/OpenAI Official/,'the opened item byline names the real source');
  console.log('Focu reader wave-9 (N2): the recorded source name reaches cards and byline passed');
})().catch(err=>{console.error(err);process.exit(1)});
// Wave-9 (PM sweep N3): the reading-summary export — the learning
// loop's only transport — no longer sits at the bottom of an unbounded
// Archive. The control now precedes the archive grid in DOM order; its
// styling, its Archive-only visibility, and the exported payload are
// unchanged (the wave-5 export tests above stand unmodified).
{
  const footAt=html.indexOf('id="archivefoot"'),gridAt=html.indexOf('id="grid"');
  assert.ok(footAt>-1&&gridAt>-1&&footAt<gridAt,'the export control precedes the first archive card in DOM order');
  const e=makeEnvironment();
  e.run('render(['+article('n3-item')+'],"")');
  e.run("markDone('n3-item','manual')");
  e.run("setView('archive')");
  assert.equal(e.get('archivefoot').hidden,false,'the control is visible at the top of Archive');
  assert.equal(e.get('grid').children.length,1,'archived cards still render in the grid below it');
  e.run("setView('briefing')");
  assert.equal(e.get('archivefoot').hidden,true,'no export control appears outside Archive');
  console.log('Focu reader wave-9 (N3): export control above the archive grid passed');
}

// Wave-10 (PM plan-3 wave 27, F8 residual): the reader's audio-failure
// path joins the card path. When cached audio fails for the item open
// in the reader, device narration starts by itself — the owner is never
// handed a second button and an instruction — and the state line states
// the fact in plain language. Exactly one primary listen control
// remains: the narration's own pause button. (The harness's fake speech
// completes synchronously, so this block holds narration in flight to
// observe the failure moment itself.)
{
  assert.equal(html.includes('Try device read-aloud'),false,'no instruction to operate a second control survives anywhere in the reader');
  const e=makeEnvironment();
  e.run("render([{id:'fail-1',origin:'daily_compilation',title:'Briefing with broken audio',summary:'',date:'2026-11-17',source:'Focu',audio_url:'assets/broken.mp3',audio_duration:600,covered_content_ids:[],blocks:[{type:'paragraph',text:'The evidence in this briefing matters.'}],reading_minutes:2}],'')");
  e.run("openItem('fail-1')");
  assert.equal(e.get('listen').hidden,false,'Listen is the one control before any failure');
  assert.equal(e.get('readaloud').hidden,true,'no second engine is offered alongside it');
  e.run("speechSynthesis.speak=function(u){speechSynthesis.spoken.push(u.text)}");
  e.get('listen').onclick();
  assert.equal(e.run('playingId'),'fail-1');
  e.get('player').events.error();
  assert.equal(e.run('failedAudioId'),'fail-1','the failure is recorded against the item');
  assert.equal(e.speech.spoken.length,1,'device narration starts on its own — no second tap');
  assert.match(e.speech.spoken[0],/evidence in this briefing/, 'the narration is the article itself');
  assert.equal(e.run('speechRunning'),true,'narration is in flight');
  assert.equal(e.run('speechId'),'fail-1');
  assert.equal(e.run("isDone('fail-1')"),false,'a narration still in flight has not archived anything');
  assert.equal(e.get('readerstate').textContent,'Playing with device voice — the recorded audio could not load.','the state line states the fact, with no instruction');
  const visible=[e.get('listen'),e.get('readaloud')].filter(n=>!n.hidden);
  assert.equal(visible.length,1,'exactly one primary listen control remains after the failure');
  assert.equal(visible[0],e.get('readaloud'),'the remaining control is the narration control');
  assert.equal(e.get('readaloud').textContent,'Ⅱ Pause reading','the remaining control pauses the narration that started itself');
  assert.equal(e.get('playerbar').hidden,true,'the dead player bar leaves the screen');
  console.log('Focu reader wave-10 (F8): audio failure falls back to device voice on its own passed');
}
// Wave-10 (PM plan-3 wave 27): Archive cards say which kind of done
// they are. The label rides the card's existing meta line, from the
// predicates render() already evaluates — no new state, no store
// change — and appears in no other view.
{
  const e=makeEnvironment();
  e.run("render(["+
    "{id:'arc-done',origin:'user_initiated',title:'Finished piece',summary:'',date:'2026-11-16',source:'Your research',audio_url:'',blocks:[{type:'paragraph',text:'Read'}],reading_minutes:2},"+
    "{id:'arc-nfm',origin:'registered_source',title:'Dismissed piece',summary:'',date:'2026-11-16',source:'Anthropic',audio_url:'',blocks:[{type:'paragraph',text:'Skipped'}],reading_minutes:2}"+
  "],'')");
  e.run("markDone('arc-done','article')");
  e.run("markNotForMe('arc-nfm')");
  e.run("setView('archive')");
  const cards=e.get('grid').children;
  assert.equal(cards.length,2,'both kinds of done rest in Archive');
  const metaByTitle={};
  for(const card of cards){const body=card.children[0].children[0];metaByTitle[body.children[1].textContent]=body.children[0].textContent}
  assert.match(metaByTitle['Finished piece'],/·  Finished$/,'a consumed card is labelled Finished in its meta line');
  assert.match(metaByTitle['Dismissed piece'],/·  Not for me$/,'a dismissed card is labelled Not for me in its meta line');
  const live=makeEnvironment();
  live.run('render(['+article('arc-live')+'],"")');
  const liveMeta=live.get('grid').children[0].children[0].children[0].children[0].textContent;
  assert.doesNotMatch(liveMeta,/Finished|Not for me/,'no archive state label appears on a live feed card');
  console.log('Focu reader wave-10: archive cards name their kind of done passed');
}
// Wave-10 (PM plan-3 wave 27): the card-level Archive action takes the
// same borderless quiet styling as its Not-for-me and Useful neighbours
// (audit §2.3's unimplemented line) — styling only; Archive and Restore
// do exactly what they did.
{
  const e=makeEnvironment();
  e.run('render(['+article('quiet-1')+'],"")');
  const controls=e.get('grid').children[0].children[1].children;
  assert.deepEqual(controls.map(n=>n.textContent),['Archive','Not for me','Useful']);
  assert.ok(controls.every(n=>n.className==='quiet-action'),'every card act shares the quiet register — Archive included');
  e.run("markDone('quiet-1','manual')");
  e.run("setView('archive')");
  const restore=e.get('grid').children[0].children[1].children[0];
  assert.equal(restore.textContent,'Restore');
  assert.equal(restore.className,'quiet-action','Restore carries the same quiet styling in Archive');
  restore.onclick();
  assert.equal(e.run("isDone('quiet-1')"),false,'Restore still restores — only its styling changed');
  console.log('Focu reader wave-10: the archive action is as quiet as its neighbours passed');
}

// Wave-11 (run wave 28): a bullet-shaped digest item — the LinkedIn
// feed shape, whose body is a list of entries rather than prose — now
// reaches the reader carrying a publisher gist extracted from its
// first entry, and the card renders it through the same .feedgist
// glance path as every other gist. No reader change was needed: this
// pins the payload end of the publisher fix, in the Briefing tab's
// collapsed source row where uncovered digests actually rest.
{
  const e=makeEnvironment();
  e.run("render(["+
    "{id:'daily-1',origin:'daily_compilation',title:'Today briefing',date:'2026-11-14',source:'Focu',covered_content_ids:[],blocks:[{type:'paragraph',text:'Compiled'}]},"+
    "{id:'li-1',origin:'registered_source',title:'LinkedIn Feed — Friday, November 14, 2026',summary:'',gist:'Jane Doe — shipped a mapping tool for geothermal surveys',date:'2026-11-14',source:'LinkedIn Feed',blocks:[{type:'bullet',text:'Jane Doe — shipped a mapping tool for geothermal surveys'}],reading_minutes:2}"+
  "],'')");
  const kids=e.get('grid').children;
  assert.equal(kids.length,2,'briefing card plus the collapsed source row');
  kids[1].onclick();
  const open=e.get('grid').children;
  assert.equal(open.length,3,'expanding reveals the digest card in place');
  const body=open[2].children[0].children[0];
  const gist=body.children.find(n=>n.className==='feedgist');
  assert.ok(gist,'digest card renders the glance line');
  assert.equal(gist.textContent,'Jane Doe — shipped a mapping tool for geothermal surveys');
  assert.equal(body.children.find(n=>n.className==='feedsummary'),undefined,'no clamped summary stands in for the gist');
  console.log('Focu reader wave-11: bullet-digest gist renders on the card passed');
}

console.log('Focu reader behavior: article, local read-aloud, persistence and audio end passed');
console.log('Focu reader wave-2: one-tap play, cost chips and persisted resume passed');
console.log('Focu reader wave-3: contextual recovery, skip controls and briefing purity passed');
console.log('Focu reader wave-5: distinct negative act and owner-carried export passed');
console.log('Focu reader wave-6: the useful act — the one promotion signal — passed');
console.log('Focu reader wave-7: compilation covered ids — briefing marks can be attributed — passed');
console.log('Focu reader wave-8: the original door — the ladder top rung is reachable — passed');
console.log('Focu reader wave-9: agenda-contents cards, real source names, export above the archive passed');
console.log('Focu reader wave-10: automatic voice fallback, archive state labels, quiet archive action passed');
console.log('Focu reader wave-11: bullet-digest gist — the glance layer covers the digest shape passed');
