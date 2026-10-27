import {call, routerHook} from "@decky/api";
import {
  ButtonItem, Field, PanelSection, PanelSectionRow, SidebarNavigation,
  ToggleField, Navigation, afterPatch, createReactTreePatcher, findInReactTree,
  staticClasses,
} from "@decky/ui";
import {useCallback, useEffect, useRef, useState} from "react";
import {FaPuzzlePiece} from "react-icons/fa";

type Mod = {id:string; name:string; description:string; version:string; enabled:boolean; available:boolean; requires:string[]; detail:string};
type Environment = {healthy:boolean; can_repair:boolean; runtime_version:string; last_backup:string;
  checks:{id:string; label:string; healthy:boolean; detail:string; fixable:boolean}[];
  job:{state:string; message:string; backup:string}};
type Status = {ok:boolean; error?:string; running:boolean; game_path:string; last_backup:string; mods:Mod[]; environment?:Environment};
const ROUTE = "/mhr-mods";
const PROPERTY_ROUTE = "/app/:appid/properties";

function Manager({compact = false}: {compact?:boolean}) {
  const [status,setStatus] = useState<Status>();
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const repairing = status?.environment?.job.state === "running";
  const alive = useRef(true);
  const inFlight = useRef(false);
  const refresh = useCallback(async () => {
    if(inFlight.current) return;
    try {
      const result = await call<[],Status>("get_status");
      if(alive.current) {
        if(result.ok) {setStatus(result); setError("");}
        else setError(result.error || "读取 Mod 状态失败");
      }
    } catch(e) {if(alive.current) setError(String(e));}
  },[]);
  useEffect(()=>{
    alive.current=true;
    void refresh();
    const timer=setInterval(()=>void refresh(),5000);
    return ()=>{alive.current=false;clearInterval(timer);};
  },[refresh]);
  const mutate = async (action:()=>Promise<Status>) => {
    if(inFlight.current)return;
    inFlight.current=true;setBusy(true);setError("");
    try {
      const result=await action();
      if(alive.current) {
        if(result.ok)setStatus(result);
        else setError(result.error || "切换失败");
      }
    }catch(e){if(alive.current)setError(String(e));}
    finally{inFlight.current=false;if(alive.current)setBusy(false);}
  };
  const toggle = (mod:Mod,on:boolean) => mutate(()=>call<[string,boolean],Status>("set_enabled",mod.id,on));
  const repair = () => mutate(()=>call<[],Status>("repair_environment"));
  if(compact) return <PanelSection title="怪物猎人：崛起">
    <PanelSectionRow><Field label={status?.running?"MHR 正在运行":"MHR Mod 管理"} description={error || (repairing?"正在修复环境…":status?.environment?(status.environment.healthy?"运行环境检查正常":"运行环境有项目需要处理"):"游戏属性页也提供 Mods 管理入口")}/></PanelSectionRow>
    <PanelSectionRow><ButtonItem onClick={()=>{Navigation.CloseSideMenus();Navigation.Navigate(ROUTE);}}>打开 Mods 管理</ButtonItem></PanelSectionRow>
    <PanelSectionRow><ButtonItem onClick={()=>{Navigation.CloseSideMenus();Navigation.Navigate("/app/1446780/properties/general");}}>打开 MHR 游戏属性</ButtonItem></PanelSectionRow>
  </PanelSection>;
  return <div style={{padding:"12px 24px 40px"}}>
    <PanelSection title="本地 Mods">
      <PanelSectionRow><Field label={status?.running?"请退出 MHR 后切换":"切换后，下次启动游戏生效"}
        description="每次切换前自动备份。仅移动 Mod 文件，保留你的界面、字体和鬼火鸟设置。"/></PanelSectionRow>
      {error?<PanelSectionRow><Field label="操作未完成" description={error}/></PanelSectionRow>:null}
      {!status?<PanelSectionRow><Field label={error?"请刷新重试":"正在读取…"}/></PanelSectionRow>:null}
      {status?.mods.map(mod=><PanelSectionRow key={mod.id}><ToggleField
        label={`${mod.name} · ${mod.version}`}
        description={mod.detail || mod.description}
        checked={mod.enabled} disabled={busy || repairing || status.running || !mod.available}
        onChange={on=>void toggle(mod,on)}/></PanelSectionRow>)}
      <PanelSectionRow><ButtonItem disabled={busy} onClick={()=>void refresh()}>{busy?"正在处理…":"刷新状态"}</ButtonItem></PanelSectionRow>
    </PanelSection>
    {status?.environment?<PanelSection title="环境检查与修复">
      <PanelSectionRow><Field label={repairing?"正在修复…":status.environment.healthy?"运行条件检查正常":"有项目需要处理"}
        description="打开此页时自动检查；仅在点击修复后修改文件。保留 Steam 当前的 Proton 选择。"/></PanelSectionRow>
      {status.environment.checks.map(check=><PanelSectionRow key={check.id}><Field
        label={`${check.healthy?"✓":"!"} ${check.label}`} description={check.detail}/></PanelSectionRow>)}
      {status.environment.job.message?<PanelSectionRow><Field
        label={status.environment.job.state==="failed"?"修复未完成":"修复状态"} description={status.environment.job.message}/></PanelSectionRow>:null}
      <PanelSectionRow><ButtonItem disabled={busy || repairing || status.running || !status.environment.can_repair}
        onClick={()=>void repair()}>{repairing?"正在备份并修复…":status.running?"退出 MHR 后可修复":"备份并一键修复"}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><Field label="修复范围" description="备份 Mod、配置、Proton 环境及存档，按需修复运行库并开启 Direct2D。修复完成后再启动游戏；未知版本文件保留，检查正常时无需修复。"/></PanelSectionRow>
      {status.environment.job.backup || status.environment.last_backup?<PanelSectionRow><Field label="环境修复备份" description={status.environment.job.backup || status.environment.last_backup}/></PanelSectionRow>:null}
    </PanelSection>:null}
    {status?.last_backup?<PanelSection title="最近一次自动备份"><PanelSectionRow><Field label="已保存原文件与配置" description={status.last_backup}/></PanelSectionRow></PanelSection>:null}
  </div>;
}
function Page(){return <SidebarNavigation title="MHR Mods" showTitle pages={[{title:"Mods 管理",route:ROUTE,link:ROUTE,content:<Manager/>,icon:<FaPuzzlePiece/>}]}/>;}

/** The Steam property route renders a wrapper, then the appId property view.
 * Keep matching by semantic props; never depend on minified export names. */
function injectPage(args:any[],ret:any){
  if(Number(args[0]?.appId)!==1446780)return ret;
  const nav=findInReactTree(ret,n=>Array.isArray(n?.props?.pages));
  if(nav&&!nav.props.pages.some((p:any)=>p.identifier==="mhrmods")){
    nav.props={...nav.props,pages:[...nav.props.pages,{title:"Mods 管理",identifier:"mhrmods",route:"/app/:appid/properties/mhrmods",link:"/app/1446780/properties/mhrmods",icon:<FaPuzzlePiece/>,content:<Manager/>}]};
  }
  return ret;
}
export default function(){
  let routePatch:any;
  const patches:any[]=[];
  routerHook.addRoute(ROUTE,Page,{exact:true});
  try{
    routePatch=routerHook.addPatch(PROPERTY_ROUTE,(route:any)=>{
      const handler=createReactTreePatcher([
        tree=>tree,
        tree=>findInReactTree(tree,n=>n?.props?.appId!==undefined),
      ],injectPage,"MHRMods properties");
      patches.push(afterPatch(route.children,"type",handler));
      return route;
    });
  }catch(e){console.error("[MHRMods] Properties integration unavailable",e);}
  return {
    title:<div className={staticClasses.Title}>MHR Mods</div>,
    content:<Manager compact/>,icon:<FaPuzzlePiece/>,
    onDismount(){routerHook.removeRoute(ROUTE);if(routePatch)routerHook.removePatch(PROPERTY_ROUTE,routePatch);for(const p of patches.reverse())if(!p.hasUnpatched)p.unpatch();},
  };
}
