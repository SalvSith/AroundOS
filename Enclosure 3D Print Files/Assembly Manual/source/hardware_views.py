"""Simplified Pi 4 line-art model and screen mounting views.
Pi outline/hole pattern follows official Pi 4 mechanical drawing; small components
and connector shells are illustrative, not a manufacturing model. Spacer height
and exploded distances are illustrative; supplied hardware must be measured.
"""
from pathlib import Path
import math,json,argparse
from OCP.STEPControl import STEPControl_Reader
from OCP.gp import gp_Trsf,gp_Ax1,gp_Ax2,gp_Pnt,gp_Dir,gp_Vec
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRep import BRep_Builder
from OCP.HLRBRep import HLRBRep_Algo,HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS,TopoDS_Compound
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--screen',required=True);args=parser.parse_args()
def box(x,y,z,dx,dy,dz):return BRepPrimAPI_MakeBox(gp_Pnt(x,y,z),dx,dy,dz).Shape()
def cyl(x,y,z,r,h):return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,y,z),gp_Dir(0,0,1)),r,h).Shape()
def move(s,x=0,y=0,z=0):
 t=gp_Trsf();t.SetTranslation(gp_Vec(x,y,z));return BRepBuilderAPI_Transform(s,t,True).Shape()
def compound(parts):
 b=BRep_Builder();s=TopoDS_Compound();b.MakeCompound(s)
 for part in parts:b.Add(s,part)
 return s
def curves(s):
 if s.IsNull():return []
 ex=TopExp_Explorer(s,TopAbs_EDGE);out=[]
 while ex.More():
  try:
   q=GCPnts_QuasiUniformDeflection(BRepAdaptor_Curve(TopoDS.Edge(ex.Current())),.16)
   pts=[[round(q.Value(i).X(),4),round(q.Value(i).Y(),4)] for i in range(1,q.NbPoints()+1)]
   if len(pts)>1:out.append(pts)
  except Exception:pass
  ex.Next()
 return out
# Standard board local frame: USB-A/Ethernet on right, power/HDMI along bottom.
board=box(0,0,0,85,56,1.6)
holes=[(3.5,3.5),(61.5,3.5),(3.5,52.5),(61.5,52.5)]
for x,y in holes:board=BRepAlgoAPI_Cut(board,cyl(x,y,-1,1.35,4)).Shape()
parts=[board]
# Socket centres taken from Pi 4 mechanical drawing; widths/details simplified.
ports=[(7.0,-1,8.4,5.6,3.2),(22.3,-1,7.4,5.5,3),(35.8,-1,7.4,5.5,3)]
for x,y,w,d,h in ports:
 outer=box(x,y,1.6,w,d,h);inner=box(x+.6,y-.1,2.2,w-1.2,d-1,h-1.1);parts.append(BRepAlgoAPI_Cut(outer,inner).Shape())
for yy in (9,27):
 outer=box(69,yy-7,1.6,18,14,16)
 for zz in (3.1,10.8):outer=BRepAlgoAPI_Cut(outer,box(83,yy-5.5,zz,5,11,5.1)).Shape()
 parts.append(outer)
parts.append(BRepAlgoAPI_Cut(box(66,38.75,1.6,21,14,13.5),box(82,40.5,3,6,10.5,9)).Shape())
parts += [box(24,18,1.6,15,15,2.4),box(43,21,1.6,11,10,1.6),box(4,24,1.6,10,10,1.2),box(7.1,49,1.6,50.8,5,2.5),box(19,4,1.6,1.5,13,5.5),box(1,12,1.6,1.5,13,5.5),box(49,0,1.6,8,12,6)]
for col in range(20):
 for yy in (50.2,52.74):parts.append(box(8.2+col*2.54,yy,4.1,.6,.6,6))
for xx,yy in [(16,30),(19,29),(15,37),(37,9),(42,12),(57,21),(59,33),(21,38),(26,40)]:parts.append(box(xx,yy,1.6,2.8,1.5,1.2))
pi=compound(parts)
r=STEPControl_Reader();r.ReadFile(args.screen);r.TransferRoots();screen=r.OneShape()
# CAD raw: X horizontal; Y rearward; -Z upwards for this view.
t=gp_Trsf();t.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(1,0,0)),math.pi/2)
screen=BRepBuilderAPI_Transform(screen,t,True).Shape()
# Normalized screen rear points are (-20.5,+/-24.5) and (37.5,+/-24.5).
# Surface level from STEP mount centres; 10 mm added gap is an illustrative spacer.
pi_mount=move(pi,-24,-28,24.5)
standoffs=[BRepAlgoAPI_Cut(cyl(x,y,14.5,2.7,10),cyl(x,y,14,1.2,11)).Shape() for x in (-20.5,37.5) for y in (-24.5,24.5)]
screws=[compound([cyl(x,y,26.1,2.5,1.5),cyl(x,y,22.6,1.2,3.5)]) for x in (-20.5,37.5) for y in (-24.5,24.5)]
mounted=compound([screen,pi_mount]+standoffs+screws)
exploded=compound([screen,move(pi_mount,z=120)]+[move(s,z=70) for s in standoffs]+[move(s,z=150) for s in screws])
views={'top':((0,0,1),(1,0,0)),'iso':((1,-1,1.8),(1,1,0)),'side':((1,0,0),(0,0,-1))}
CAD=json.loads((ROOT/'source/cad-lines.json').read_text())
for key,shape,names in [('H',pi,['top','iso','side']),('J',screen,['top','iso','side']),('K',mounted,['top','iso','side']),('L',exploded,['iso','side'])]:
 CAD[key]={'source':'Pi 4 illustrative model + supplied screen geometry','views':{}}
 for name in names:
  direction,xdir=views[name]
  if key=='L' and name=='iso':direction=(1,-1,1)
  a=HLRBRep_Algo();a.Add(shape);a.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0,0,0),gp_Dir(*direction),gp_Dir(*xdir))));a.Update();a.Hide();h=HLRBRep_HLRToShape(a)
  lines=curves(h.VCompound())+curves(h.OutLineVCompound());hidden=curves(h.HCompound())+curves(h.OutLineHCompound());CAD[key]['views'][name]={'visible':lines,'hidden':hidden}
  points=[p for line in lines for p in line];xmin=min(p[0] for p in points)-3;xmax=max(p[0] for p in points)+3;ymin=min(p[1] for p in points)-3;ymax=max(p[1] for p in points)+3
  svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{xmin} {-ymax} {xmax-xmin} {ymax-ymin}"><title>{key} {name}: illustrative Raspberry Pi 4 mounting view</title><g fill="none" stroke="#18231b" stroke-width="0.22" stroke-linejoin="round">']
  for path in lines:svg.append('<polyline points="'+' '.join(f'{x},{-y}' for x,y in path)+'"/>')
  svg.append('</g></svg>');(ROOT/'illustrations'/f'{key}-{name}.svg').write_text('\n'.join(svg));print(key,name,flush=True)
(ROOT/'source/cad-lines.json').write_text(json.dumps(CAD,separators=(',',':')))
