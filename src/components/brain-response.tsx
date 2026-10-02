"use client";
import Image from "next/image";
import { ReportSheet } from "@/components/report-sheet";
import { MicrophoneRecorder } from "@/components/microphone-recorder";
import { useEffect, useMemo, useState } from "react";
import { AudioLines, FileText, Video, Upload, ArrowRight, Download, Activity, LoaderCircle, X, Play, Pause, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
type Point={start_seconds:number;duration_seconds:number;mean_response:number;rms_response:number};
type Job={id:string;status:string;phase?:string;error?:string;result?:{shape:number[];note:string;timeline:Point[]}};
async function api(path:string,init?:RequestInit){const r=await fetch(`/api/tribe/${path}`,init);const d=await r.json();if(!r.ok)throw new Error(d.detail||d.error||"Request failed");return d;}
export function BrainResponse(){
 const [playing,setPlaying]=useState(false);
 const [speed,setSpeed]=useState(1);
 const [loop,setLoop]=useState(false);
 const [recording,setRecording]=useState(false);
 const [example,setExample]=useState<"video"|"audio">("video");
 const [kind,setKind]=useState("text");const [text,setText]=useState("");const [file,setFile]=useState<File>();const [preview,setPreview]=useState("");const [job,setJob]=useState<Job>();const [error,setError]=useState("");const [busy,setBusy]=useState(false);const [selected,setSelected]=useState(0);
 useEffect(()=>{const id=sessionStorage.getItem("vinicaya-tribe-job");let alive=true;if(id&&/^[a-f0-9]{32}$/.test(id))api(`v1/jobs/${id}`).then(data=>{if(alive){setJob(data);setSelected(0);setPlaying(data.status==="completed"&&(data.result?.timeline.length||0)>1);}}).catch(()=>{});return()=>{alive=false;};},[]);
 useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview);},[preview]);
 useEffect(()=>{if(!job||!["queued","running"].includes(job.status))return;let alive=true;const timer=setTimeout(()=>{api(`v1/jobs/${job.id}`).then(d=>{if(alive){setJob(d);if(d.status==="completed"){setSelected(0);setPlaying((d.result?.timeline.length||0)>1);}}}).catch(e=>{if(alive){setError(e.message);setJob({...job,status:"unavailable"});}});},2500);return()=>{alive=false;clearTimeout(timer);};},[job]);
 const running=recording||busy||!!job&&["queued","running"].includes(job.status);
 function changeKind(value:string){setKind(value);setFile(undefined);setPreview("");setError("");}
 async function submit(){setBusy(true);setError("");setJob(undefined);setSelected(0);try{const body=new FormData();if(kind!=="text"&&file)body.set("file",file);else body.set("text",text);const created=await api("v1/jobs",{method:"POST",body});sessionStorage.setItem("vinicaya-tribe-job",created.id);setJob(created);}catch(e){setError(e instanceof Error?e.message:"Request failed");}finally{setBusy(false);}}
 const points=useMemo(()=>job?.result?.timeline||[],[job?.result?.timeline]);const max=Math.max(.00001,...points.map(p=>p.rms_response));const first=points[0]?.start_seconds||0;const end=points.at(-1)?.start_seconds||first;const current=points[selected]||points[0];
 useEffect(()=>{
  if(!playing||!points.length)return;
  if(selected>=points.length-1){
   if(!loop)return;
   const timer=setTimeout(()=>setSelected(0),Math.max(100,(points[selected].duration_seconds*1000)/speed));
   return()=>clearTimeout(timer);
  }
  const delay=Math.max(100,((points[selected+1].start_seconds-points[selected].start_seconds)*1000)/speed);
  const timer=setTimeout(()=>{setSelected(selected+1);if(selected+1>=points.length-1&&!loop)setPlaying(false);},delay);
  return()=>clearTimeout(timer);
 },[playing,selected,speed,points,loop]);
 useEffect(()=>{
  if(job?.status!=="completed")return;
  for(const step of [selected,selected+1,selected+2]){
   if(step>=points.length)continue;
   const image=new window.Image();image.src=`/api/tribe/v1/jobs/${job.id}/frames/${step}`;
  }
 },[job?.id,job?.status,selected,points.length]);
 return <section className="brain-response brain-response-panel">
  <header><div className="brain-title"><Activity size={20}/><div><h2>Brain response</h2><p>How the cortex may respond to a stimulus</p></div></div><span className="brain-model">TRIBE v2 · Research</span></header>
  <details className="brain-examples"><summary>View example brain-response timelines</summary><div className="brain-example-tabs" role="group" aria-label="Example timeline"><button aria-pressed={example==="video"} onClick={()=>setExample("video")}><Video size={14}/>Video + audio + text</button><button aria-pressed={example==="audio"} onClick={()=>setExample("audio")}><AudioLines size={14}/>Audio + text</button></div><figure><a href={`/samples/tribe-${example}-timeline.png`} target="_blank" rel="noreferrer" aria-label="Open full-size example timeline"><Image src={`/samples/tribe-${example}-timeline.png`} alt={example==="video"?"Example video frames, audio waveform, words and cortical response maps across 15 seconds":"Example audio waveform, spoken words and cortical response maps across 15 seconds"} width={2957} height={example==="video"?386:278} unoptimized/></a><figcaption>Illustrative reference supplied by you · not a prediction generated in this session. Click to view full size.</figcaption></figure></details>
  <div className="brain-mode-tabs" role="group" aria-label="Stimulus type">{[{id:"text",label:"Text",Icon:FileText},{id:"audio",label:"Audio",Icon:AudioLines},{id:"video",label:"Video",Icon:Video}].map(({id,label,Icon})=><button key={id} aria-pressed={kind===id} disabled={running} onClick={()=>changeKind(id)}><Icon size={16}/>{label}</button>)}</div>
  {kind==="audio"&&<MicrophoneRecorder disabled={running&&!recording} onBusyChange={setRecording} onRecorded={recorded=>{setFile(recorded);setPreview(URL.createObjectURL(recorded));setError("");}}/>}
  {kind==="text"?<Textarea aria-label="Text stimulus" value={text} maxLength={5000} disabled={running} onChange={e=>setText(e.target.value)} placeholder="Enter the text presented to the subject…" className="brain-stimulus-text"/>:<div className="brain-upload-area">{file?<><div className="brain-file-name"><span>{file.name}</span><Button variant="ghost" size="icon" disabled={running} aria-label="Remove stimulus" onClick={()=>{setFile(undefined);setPreview("");}}><X size={16}/></Button></div>{kind==="audio"?<audio src={preview} controls/>:<video src={preview} controls preload="metadata"/>}</>:<label><Upload size={25}/><strong>Choose {kind} stimulus</strong><span>Up to 25 MB · 120 seconds</span><input type="file" disabled={running} accept={kind==="audio"?".wav,.mp3,.flac,.ogg":".mp4,.avi,.mkv,.mov,.webm"} onChange={e=>{const f=e.target.files?.[0];if(f&&f.size>25*1024*1024){setError("Use a file under 25 MB");e.target.value="";return;}setFile(f);setPreview(f?URL.createObjectURL(f):"");setError("");}}/></label>}</div>}
  <div className="brain-run-row"><small>{kind==="text"?`${text.length.toLocaleString()} / 5,000 characters`:"One stimulus per prediction"}</small><Button className="brain-predict-button" disabled={running||(kind==="text"?!text.trim():!file)} onClick={()=>void submit()}>{running?<LoaderCircle size={15} className="animate-spin"/>:<ArrowRight size={15}/>} <span>{recording?"Recording voice…":running?"Processing stimulus…":"Predict response"}</span></Button></div>
  {running&&<div className="brain-progress" role="status"><LoaderCircle size={17} className="animate-spin"/><div><strong>{job?.status==="queued"?"Waiting for the model":job?.phase||"Generating cortical responses"}</strong><p>The first run may take longer while models and stimulus features load.</p></div></div>}
  {(error||job?.error)&&<p className="medical-error" role="alert">{error||job?.error}</p>}{job?.status==="unavailable"&&<Button variant="outline" onClick={()=>{setError("");setJob({...job,status:"running"});}}>Check job again</Button>}
  {!!points.length&&<div className="brain-result"><header><h3>Predicted response timeline</h3><ReportSheet key={job?.id} jobId={job!.id} brain/><a href={`/api/tribe/v1/jobs/${job?.id}/predictions`} download><Download size={14}/>Raw sequence</a></header><div className="brain-cortex"><Image key={`${job?.id}-${selected}`} src={`/api/tribe/v1/jobs/${job?.id}/frames/${selected}`} alt={`Predicted left and right cortical activity at time step ${selected+1}`} width={1200} height={420} unoptimized/><small>Predicted cortical activity · {current?.start_seconds.toFixed(2)} s · fixed color scale across time</small></div><div className="brain-result-stats"><div><strong>{points.length}</strong><span>Time steps</span></div><div><strong>{job?.result?.shape[1].toLocaleString()}</strong><span>Cortical vertices</span></div><div><strong>fsaverage5</strong><span>Cortical surface</span></div></div><svg viewBox="0 0 700 170" role="img" aria-label="Response RMS over stimulus time">{[30,70,110,150].map(y=><line key={y} x1="20" x2="680" y1={y} y2={y} stroke="#eeeeee"/>)}<polyline fill="none" stroke="#c99715" strokeWidth="2.5" points={points.map(p=>`${20+(p.start_seconds-first)*660/Math.max(1,end-first)},${150-p.rms_response/max*125}`).join(" ")}/>{points.map((p,i)=><circle key={i} cx={20+(p.start_seconds-first)*660/Math.max(1,end-first)} cy={150-p.rms_response/max*125} r={selected===i?6:4} fill={selected===i?"#b18412":"#fcd34d"}/>)}</svg><div className="brain-time-labels"><span>{first.toFixed(1)} s</span><span>RMS response · model units</span><span>{end.toFixed(1)} s</span></div><div className="brain-playback"><Button variant="outline" size="sm" disabled={points.length<2} onClick={()=>{if(selected>=points.length-1)setSelected(0);setPlaying(!playing);}}>{playing?<Pause size={15}/>:<Play size={15}/>}<span>{playing?"Pause":"Play"}</span></Button><Button variant="ghost" size="icon-sm" aria-label="Restart brain playback" onClick={()=>{setSelected(0);setPlaying(true);}}><RotateCcw size={15}/></Button><select aria-label="Brain playback speed" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={0.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option></select><label className="brain-loop"><input type="checkbox" checked={loop} onChange={e=>setLoop(e.target.checked)}/>Loop</label><small>Frame {selected+1} / {points.length}</small></div><label className="brain-timestep">Inspect time step<input aria-label="Time step" type="range" min="0" max={points.length-1} value={selected} onChange={e=>{setPlaying(false);setSelected(Number(e.target.value));}}/></label>{current&&<div className="brain-selected-values"><span>Time <strong>{current.start_seconds.toFixed(2)} s</strong></span><span>Mean <strong>{current.mean_response.toFixed(4)}</strong></span><span>RMS <strong>{current.rms_response.toFixed(4)}</strong></span></div>}<details><summary>Prediction method and limitations</summary><p>{job?.result?.note}</p></details></div>}
  <p className="brain-research-note">Average-subject predictions, not measured patient brain activity or a diagnosis. Text uses local English speech synthesis.</p>
 </section>;
}
