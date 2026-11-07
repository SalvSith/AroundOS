"""Generate hidden-line vector illustrations from supplied STEP files (cadquery-ocp 8)."""
from pathlib import Path
import math,json,argparse
from OCP.STEPControl import STEPControl_Reader
from OCP.gp import gp_Trsf,gp_Ax1,gp_Ax2,gp_Pnt,gp_Dir,gp_Vec
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.HLRBRep import HLRBRep_Algo,HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
ROOT=Path(__file__).resolve().parents[1]; ENC=ROOT.parent
parser=argparse.ArgumentParser();parser.add_argument('--screen',type=Path,required=True);args=parser.parse_args()
files={'A':ENC/'STEP FILES/front-case-v4r2.step','B':args.screen,'C':ENC/'STEP FILES/holder-plate-v4r2.step','D':ENC/'STEP FILES/Rear Plate V4R2.step','E':ENC/'STEP FILES/Desk Mount Connector V4R2.step','F':ENC/'STEP FILES/Desk Mount Base V4R2.step'}
def bounds(s):
 b=Bnd_Box();BRepBndLib.Add_s(s,b);lo=b.CornerMin();hi=b.CornerMax();return [lo.X(),lo.Y(),lo.Z(),hi.X(),hi.Y(),hi.Z()]
def rot(s,angle):
 t=gp_Trsf();t.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(1,0,0)),math.radians(angle));return BRepBuilderAPI_Transform(s,t,True).Shape()
def curves(s):
 if s.IsNull():return []
 ex=TopExp_Explorer(s,TopAbs_EDGE);out=[]
 while ex.More():
  e=TopoDS.Edge(ex.Current());c=BRepAdaptor_Curve(e)
  try:
   q=GCPnts_QuasiUniformDeflection(c,0.12)
   pts=[[round(q.Value(i).X(),4),round(q.Value(i).Y(),4)] for i in range(1,q.NbPoints()+1)]
   if len(pts)>1:out.append(pts)
  except Exception:pass
  ex.Next()
 return out
result={}
for key,path in files.items():
 r=STEPControl_Reader();r.ReadFile(str(path));r.TransferRoots();s=r.OneShape();original=bounds(s)
 if key=='B':s=rot(s,-90)
 if key=='D':s=rot(s,15)
 b=bounds(s);t=gp_Trsf();t.SetTranslation(gp_Vec(*[-(b[i]+b[i+3])/2 for i in range(3)]));s=BRepBuilderAPI_Transform(s,t,True).Shape()
 result[key]={'source':path.name,'source_bounds_mm':original,'normalized_bounds_mm':bounds(s),'views':{}}
 views={'front':(1,-0.45,1.6),'rear':(-1,0.65,-1.6),'straight':(0,0,1)}
 if key in 'EF':views={'front':(1,0.8,1.4),'rear':(-1,0.8,-1.4),'straight':(0,1,0.001)}
 for view,d in views.items():
  print(key,view,flush=True);a=HLRBRep_Algo();a.Add(s);a.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0,0,0),gp_Dir(*d),gp_Dir(d[2],0,-d[0]))));a.Update();a.Hide();h=HLRBRep_HLRToShape(a)
  lines=curves(h.VCompound())+curves(h.OutLineVCompound());hidden=curves(h.HCompound())+curves(h.OutLineHCompound())
  result[key]['views'][view]={'visible':lines,'hidden':hidden}
  pts=[p for line in lines+hidden for p in line];xmin=min(p[0] for p in pts)-2;ymin=min(p[1] for p in pts)-2;xmax=max(p[0] for p in pts)+2;ymax=max(p[1] for p in pts)+2
  svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{xmin} {-ymax} {xmax-xmin} {ymax-ymin}"><title>Part {key}: {path.stem}, {view} CAD view</title><g fill="none" stroke-linecap="round" stroke-linejoin="round">']
  for group,color,width,dash in [(hidden,'#b8c3c7',.12,' stroke-dasharray="1.2 1.2"'),(lines,'#16353b',.25,'')]:
   for line in group:svg.append(f'<polyline stroke="{color}" stroke-width="{width}"{dash} points="'+ ' '.join(f'{x},{-y}' for x,y in line)+'"/>')
  svg.append('</g></svg>');(ROOT/'illustrations'/f'{key}-{view}.svg').write_text('\n'.join(svg))
 (ROOT/'source/cad-lines.json').write_text(json.dumps(result,separators=(',',':')))
print('Done',flush=True)

# Front screen seating for the overview: inferred alignment to the case lip.
from OCP.TopoDS import TopoDS_Compound
from OCP.BRep import BRep_Builder
parts=[]
for key in ['A','B']:
 r=STEPControl_Reader();r.ReadFile(str(files[key]));r.TransferRoots();s=r.OneShape()
 if key=='B':
  s=rot(s,-90);t=gp_Trsf();t.SetTranslation(gp_Vec(0,0,-.2));s=BRepBuilderAPI_Transform(s,t,True).Shape()
 parts.append(s)
b=BRep_Builder();comp=TopoDS_Compound();b.MakeCompound(comp)
for s in parts:b.Add(comp,s)
a=HLRBRep_Algo();a.Add(comp);d=(1,-.45,1.6);a.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0,0,0),gp_Dir(*d),gp_Dir(d[2],0,-d[0]))));a.Update();a.Hide();h=HLRBRep_HLRToShape(a)
lines=curves(h.VCompound())+curves(h.OutLineVCompound())
result=json.loads((ROOT/'source/cad-lines.json').read_text());result['G']={'source':'A+B visual seating at front lip; inferred placement','views':{'front':{'visible':lines,'hidden':[]}}};(ROOT/'source/cad-lines.json').write_text(json.dumps(result,separators=(',',':')))
print('Combined display view added')
