"use client";
import { useEffect, useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";

export function MicrophoneRecorder({disabled,onRecorded,onBusyChange}:{disabled:boolean;onRecorded:(file:File)=>void;onBusyChange:(busy:boolean)=>void}) {
 const [recording,setRecording]=useState(false);
 const [requesting,setRequesting]=useState(false);
 const [seconds,setSeconds]=useState(0);
 const [error,setError]=useState("");
 const recorder=useRef<MediaRecorder|null>(null);
 const stream=useRef<MediaStream|null>(null);
 const mounted=useRef(true);
 const timer=useRef<ReturnType<typeof setInterval>|null>(null);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;if(timer.current)clearInterval(timer.current);if(recorder.current?.state==="recording")recorder.current.stop();stream.current?.getTracks().forEach(track=>track.stop());};},[]);
 function stop(){if(recorder.current?.state==="recording")recorder.current.stop();}
 async function start(){
  setError("");setRequesting(true);onBusyChange(true);
  try {
   if(!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==="undefined")throw new Error("Microphone recording requires a supported browser and HTTPS or localhost.");
   const audio=await navigator.mediaDevices.getUserMedia({audio:true});
   if(!mounted.current){audio.getTracks().forEach(track=>track.stop());return;}
   stream.current=audio;
   const mime=["audio/webm;codecs=opus","audio/ogg;codecs=opus","audio/mp4"].find(type=>MediaRecorder.isTypeSupported(type));
   const session=new MediaRecorder(audio,mime?{mimeType:mime}:undefined);
   recorder.current=session;const chunks:Blob[]=[];let size=0;let elapsed=0;
   session.ondataavailable=e=>{if(e.data.size){chunks.push(e.data);size+=e.data.size;if(size>=24*1024*1024)stop();}};
   session.onerror=()=>{if(mounted.current)setError("Recording failed. Try again.");stop();};
   session.onstop=()=>{
    if(timer.current)clearInterval(timer.current);
    audio.getTracks().forEach(track=>track.stop());
    if(!mounted.current)return;
    setRecording(false);onBusyChange(false);
    const type=session.mimeType||mime||"audio/webm";
    const blob=new Blob(chunks,{type});
    if(!blob.size){setError("No audio recorded. Try again.");return;}
    const ext=type.includes("ogg")?"ogg":type.includes("mp4")?"mp4":"webm";
    onRecorded(new File([blob],`voice-recording.${ext}`,{type}));
   };
   session.start(250);setSeconds(0);setRecording(true);
   timer.current=setInterval(()=>{elapsed++;setSeconds(elapsed);if(elapsed>=119)stop();},1000);
  } catch(e){stream.current?.getTracks().forEach(track=>track.stop());setError(e instanceof DOMException&&e.name==="NotAllowedError"?"Allow microphone access to record your speech.":e instanceof Error?e.message:"Could not access the microphone.");}
  finally{if(mounted.current){setRequesting(false);if(recorder.current?.state!=="recording")onBusyChange(false);}}
 }
 return <div className="brain-microphone"><Button variant="outline" disabled={disabled||requesting} onClick={()=>recording?stop():void start()}>{recording?<Square size={15}/>:<Mic size={15}/>} {recording?`Stop recording · ${seconds}s`:requesting?"Requesting microphone…":"Record your voice"}</Button><small>{recording?"Recording · stops automatically after two minutes":"Record, preview, then predict the cortical response to your speech."}</small>{error&&<p role="alert" className="medical-error">{error}</p>}</div>;
}
