import { isSignedIn } from "@/lib/session";
async function proxy(request: Request, context: {params: Promise<{path: string[]}>}) {
 if (!(await isSignedIn())) return Response.json({error:"Please sign in again."},{status:401});
 const target=(await context.params).path.join("/");
 if (!/^(health|v1\/jobs|v1\/jobs\/[a-f0-9]{32}(\/predictions|\/report|\/frames\/\d{1,3})?)$/.test(target)) return Response.json({error:"Unknown endpoint"},{status:404});
 if(request.method==="POST") {
  const origin=request.headers.get("origin");
  try {if(origin && new URL(origin).host!==request.headers.get("host"))return Response.json({error:"Invalid origin"},{status:403});}
  catch {return Response.json({error:"Invalid origin"},{status:403});}
 }
 if(!process.env.TRIBE_API_URL || !process.env.TRIBE_API_TOKEN) return Response.json({error:"Brain-response service is not configured."},{status:503});
 try {
  const response=await fetch(`${process.env.TRIBE_API_URL}/${target}${new URL(request.url).search}`,{method:request.method,headers:{Authorization:`Bearer ${process.env.TRIBE_API_TOKEN}`,...(request.headers.get("content-type")?{"Content-Type":request.headers.get("content-type")!}:{})},body:request.method==="POST"?request.body:undefined,...({duplex:"half"} as Record<string,string>),signal:AbortSignal.any([request.signal,AbortSignal.timeout(60000)]),cache:"no-store"});
  if(!response.ok && !(response.headers.get("content-type")||"").includes("application/json"))return Response.json({error:"Brain-response API is restarting or unavailable. Please retry."},{status:response.status});
  return new Response(response.body,{status:response.status,headers:{"Content-Type":response.headers.get("content-type")||"application/json","Cache-Control":"no-store",...(response.headers.get("content-disposition")?{"Content-Disposition":response.headers.get("content-disposition")!}:{})}});
 } catch {return Response.json({error:"Brain-response API is unavailable."},{status:503});}
}
export const GET=proxy;
export const POST=proxy;
