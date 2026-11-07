"""Build the printable guide and editable Markdown from vector CAD projections.
Requirements: reportlab, fontTools and the Rubik font in the repository. Run from any directory; no CAD runtime needed for rebuild.
"""
from pathlib import Path
import json, math, shutil, html, re
from io import BytesIO
from fontTools.ttLib import TTFont as SourceFont
from fontTools.varLib.instancer import instantiateVariableFont
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
ROOT=Path(__file__).resolve().parents[1]; REPO=ROOT.parents[1]
# ReportLab embeds static TrueType faces. Pin each weight of the project font.
font_path = REPO / 'src/round-desktop/fonts/Rubik.ttf'
with SourceFont(font_path) as variable_font:
    for face, weight in [('Rubik', 400), ('Rubik-Bold', 700)]:
        static_font = instantiateVariableFont(variable_font, {'wght': weight}, updateFontNames=True)
        font_bytes = BytesIO()
        static_font.save(font_bytes)
        font_bytes.seek(0)
        pdfmetrics.registerFont(TTFont(face, font_bytes))
pdfmetrics.registerFontFamily('Rubik', normal='Rubik', bold='Rubik-Bold')

DATA=json.loads((ROOT/'source/content.json').read_text()); CAD=json.loads((ROOT/'source/cad-lines.json').read_text())
W,H=595.276,841.89; M=42; INK=HexColor('#18231b'); TEAL=HexColor('#a3f66a'); GRAY=HexColor('#59645b'); PALE=HexColor('#eff9e9'); RULE=HexColor('#ced8c8')
OUT=REPO/'output/pdf/aroundos-assembly-manual.pdf';OUT.parent.mkdir(parents=True,exist_ok=True)
c=canvas.Canvas(str(OUT),pagesize=(W,H),pageCompression=1,invariant=1,initialFontName="Rubik")
c.setTitle(DATA['title']);c.setAuthor('AroundOS project; enclosure design by JN-Husch');c.setSubject('V4R2 illustrated display enclosure and screen-mounted Raspberry Pi assembly guide')
PAGE=0

def title_case(text):
 small={'a','an','and','as','at','but','by','for','in','nor','of','on','or','per','the','to','via','vs'}
 keep={'aroundos':'AroundOS','pi':'Pi','hdmi':'HDMI','hdmi0':'HDMI0','usb':'USB','usb-a':'USB-A','usb-c':'USB-C','micro-hdmi':'Micro-HDMI','cad':'CAD','pcb':'PCB','step':'STEP','stl':'STL','readme':'README'}
 chunks=re.split(r'(<[^>]+>|\s+)',text);words=[i for i,t in enumerate(chunks) if t and not t.isspace() and not t.startswith('<')]
 for pos,i in enumerate(words):
  w=chunks[i];low=w.lower()
  chunks[i]=keep.get(low,low if low in small and pos not in (0,len(words)-1) else low.capitalize())
 return ''.join(chunks)


def label(x,y,text,size=10,font='Rubik',color=INK):
 c.setFillColor(INK if color==TEAL else color);c.setFont(font,size);c.drawString(x,y,title_case(text) if font=='Rubik-Bold' else text)
def para(text,x,y,width,size=11,leading=15,color=INK,bold=False):
 style=ParagraphStyle('p',fontName='Rubik-Bold' if bold else 'Rubik',fontSize=size,leading=leading,textColor=INK if color==TEAL else color)
 p=Paragraph(title_case(text) if bold else text,style);_,h=p.wrap(width,800);p.drawOn(c,x,y-h);return y-h

def line(x1,y1,x2,y2,color=RULE,width=.6,dash=None):
 c.saveState();c.setStrokeColor(color);c.setLineWidth(width)
 if dash:c.setDash(*dash)
 c.line(x1,y1,x2,y2);c.restoreState()
def arrow(x1,y1,x2,y2):
 line(x1,y1,x2,y2,INK,2.6);line(x1,y1,x2,y2,TEAL,1.7);a=math.atan2(y2-y1,x2-x1);c.setFillColor(TEAL)
 p=c.beginPath();p.moveTo(x2,y2);p.lineTo(x2-7*math.cos(a-.4),y2-7*math.sin(a-.4));p.lineTo(x2-7*math.cos(a+.4),y2-7*math.sin(a+.4));p.close();c.drawPath(p,stroke=0,fill=1)
def bubble(x,y,text):
 c.setFillColor(TEAL);c.circle(x,y,10,fill=1,stroke=0);c.setFillColor(INK);c.setFont('Rubik-Bold',10);c.drawCentredString(x,y-3.5,text)
def cad(key,view,x,y,width,height,hidden=False):
 v=CAD[key]['views'][view];allp=[p for path in v['visible'] for p in path];lo=[min(p[i] for p in allp) for i in range(2)];hi=[max(p[i] for p in allp) for i in range(2)];scale=min(width/(hi[0]-lo[0]),height/(hi[1]-lo[1]));cx=(lo[0]+hi[0])/2;cy=(lo[1]+hi[1])/2
 c.saveState();c.setLineJoin(1);c.setLineCap(1)
 for group,col,weight in ([('hidden',HexColor('#b8c6c8'),.32)] if hidden else [])+[('visible',INK,.65)]:
  c.setStrokeColor(col);c.setLineWidth(weight);c.setDash(2,2) if group=='hidden' else c.setDash()
  for pts in v[group]:
   p=c.beginPath();p.moveTo(x+(pts[0][0]-cx)*scale,y+(pts[0][1]-cy)*scale)
   for xx,yy in pts[1:]:p.lineTo(x+(xx-cx)*scale,y+(yy-cy)*scale)
   c.drawPath(p)
 c.restoreState()
 return lambda xx,yy:(x+(xx-cx)*scale,y+(yy-cy)*scale)
def page(kicker,title,subtitle=None):
 global PAGE
 if PAGE:c.showPage()
 PAGE+=1
 c.setFillColor(TEAL);c.rect(M,H-45,511,2,fill=1,stroke=0)
 label(M,H-35,'AROUNDOS  /  BUILD GUIDE',9,'Rubik-Bold',TEAL)
 label(M,H-63,title_case(kicker),9,'Rubik',GRAY)
 title=title_case(title)
 title_size=min(26,26*(W-2*M)/pdfmetrics.stringWidth(title,'Rubik-Bold',26))
 para(title,M,H-79,W-2*M,title_size,29,bold=True)
 if subtitle:para(subtitle,M,H-117,W-2*M,10.5,14,GRAY)
 line(M,49,W-M,49)
 label(M,32,'V4R2  |  CAD-based assembly guide  |  07 NOV 2026',8,color=GRAY)
 c.setFont('Rubik-Bold',9);c.drawRightString(W-M,32,f'{PAGE:02d} / 14')
def checkpoint(text):
 c.setFillColor(PALE);c.roundRect(M,96,W-2*M,46,6,fill=1,stroke=0)
 c.setFillColor(TEAL);c.rect(M,96,4,46,fill=1,stroke=0)
 label(M+12,126,'CHECK BEFORE CONTINUING',8,'Rubik-Bold',TEAL)
 para(text,M+12,118,W-2*M-24,9.5,12)
def actions(items,top=397):
 y=top
 for i,t in enumerate(items,1):
  bubble(M+9,y-8,str(i));y=para(t,M+29,y,W-2*M-29,10.6,14.2)-12
 if y<151:raise RuntimeError(f'Page {PAGE} actions exceed layout: {y}')
def caption(text,y=423):para(text,M,y,W-2*M,8.5,11,GRAY)
def step(idx,figure):
 s=DATA['steps'][idx];page(f'Assembly {idx+1:02d}',s['title'],s['intro']);figure();actions(s['actions']);checkpoint(s['check']);para(s['note'],M,83,W-2*M,8.5,11,GRAY)

# 01 / exploded assembly overview
page('Assembly Manual','Build Your AroundOS Computer')
para('Five printed parts. One round display. A Raspberry Pi desktop.',M,719,485,13,17,GRAY)
# Separated component views: indicative explosion, not a fitted assembly simulation.
for key,x,y in [('A',90,427),('B',194,458),('C',402,520),('D',506,551)]:
 cad(key,'front',x,y,91,145)
 bubble(x-34,y+80,key)
cad('H','iso',298,489,92,81);bubble(264,569,'P')
for x1,y1,x2,y2 in [(137,443,146,446),(241,474,250,477),(345,505,354,508),(449,536,458,539)]:arrow(x2,y2,x1,y1)
line(497,470,497,397,TEAL,.8,(3,3));cad('E','front',477,359,76,74);bubble(426,370,'E');cad('F','front',477,265,125,78);bubble(399,265,'F');arrow(477,311,477,323)
para('FRONT',54,334,90,9,12,TEAL,True);para('REAR',470,665,80,9,12,TEAL,True)
para('A  Front Case<br/>B  Display Module<br/>P  Raspberry Pi 4<br/>C  Holder Plate',M,292,215,11,20)
para('D  Rear Plate<br/>E  Stand Connector<br/>F  Desk Base',235,292,150,11,20)
para('Read before building',M,192,460,13,17,bold=True)
para('This guide follows the supplied V4R2 enclosure and SKU 24369 screen CAD. The Pi mounts to the screen using its supplied spacers and screws. Drawings show component geometry; separated positions and arrows explain the sequence and are not fit measurements.',M,168,511,10.5,14)
para('Physical fit, latch engagement and stand stability still require a build check. No assembly or powered hardware test was performed for this guide.',M,99,511,9,12,GRAY)

# 02 / inventory
page('Parts + equipment','Lay out the build','Match the letters throughout the guide. Print A, C, D, E and F; purchase B as a complete module.')
positions=[(42,684),(307,684),(42,508),(307,508),(42,332),(307,332)]
for (key,name,filename,qty,desc),(x,y) in zip(DATA['parts'],positions):
 line(x,y-168,x+246,y-168)
 bubble(x+10,y-13,key);label(x+28,y-17,name,11,'Rubik-Bold');label(x+215,y-17,'x1',10,color=GRAY)
 cad('J' if key=='B' else key,'iso' if key=='B' else ('rear' if key in 'CD' else 'front'),x+119,y-84,160,105)
 para(desc,x,y-143,246,8.6,11,GRAY)
para('Also gather',M,147,510,12,16,bold=True)
para('Raspberry Pi 4 Model B; four supplied spacers and matching screws; microSD card; Pi USB-C supply; short micro-HDMI to HDMI lead; USB-A to USB-C data cable; keyboard; small screwdriver; clean soft cloth. Choose a cooling arrangement that clears the rear cover.',M,124,511,10,13)

# 03 / Pi identification: two views plus numbered port legend.
page('Hardware / Raspberry Pi 4','Know your Raspberry Pi','A wire-style board illustration shows the connections used in this build. Match the socket shapes on your board.')
cad('H','iso',197,552,273,216)
pi=cad('H','top',449,554,150,112)
label(81,425,'Perspective View',9,color=GRAY);label(393,630,'Top View',9,color=GRAY)
for point,bx,by,num in [((11.2,-1),380,453,'1'),((26,-1),431,433,'2'),((87,9),544,483,'3')]:
 px,py=pi(*point);line(px,py,bx,by,INK,.7);bubble(bx,by,num)
for yy,num,title,body in [(380,'1','USB-C power input','Connect the Pi power supply here. Power enters the computer at the Raspberry Pi.'),(306,'2','Micro-HDMI 0','Use the HDMI socket nearest the USB-C power input. Connect it to the screen HDMI port.'),(232,'3','USB-A for touch','Connect a USB-A data port to the screen USB-C Touch socket. HDMI alone does not carry touch.')]:
 bubble(53,yy-8,num);label(75,yy-10,title,12,'Rubik-Bold');para(body,75,yy-25,471,10.5,14)
para('Four board mounting holes align with the screen\'s Pi mounting points. Components, connector shells and pin details are simplified; this illustration is not a fabrication drawing.',M,127,511,9,12,GRAY)
# 04 / Screen port map, matching the numbered photo supplied by the user.
page('Hardware / Waveshare screen','Identify the screen connections','Rear view, oriented like your supplied Waveshare photo. Numbers 3, 4 and 5 match the labels in that reference.')
screen=cad('J','top',218,510,319,319)
for point,bx,by,num in [((9,29),236,685,'3'),((29.8,28),367,648,'4'),((-44,-20),48,455,'5')]:
 px,py=screen(*point);line(px,py,bx,by,INK,.7);bubble(bx,by,num)
for xx in (-20.5,37.5):
 for yy in (-24.5,24.5):
  px,py=screen(xx,yy);c.setStrokeColor(TEAL);c.setLineWidth(2.3);c.circle(px,py,7,fill=0,stroke=1)
line(*screen(37.5,-24.5),431,457,INK,.7)
para('FOUR PI<br/>MOUNTING POINTS',434,480,115,10,14,bold=True)
para('Highlighted rings.<br/>Use the supplied<br/>spacers here.',434,442,115,9,13,GRAY)
for yy,num,title,body in [(319,'3','HDMI input','Connect to Raspberry Pi micro-HDMI 0 for video.'),(258,'5','USB-C Touch','Connect to a Pi USB-A data port for touch and the USB supply path.'),(197,'4','Unused Port 4','Leave this socket unconnected. Connect the power supply only to the Raspberry Pi; use screen port 5 for USB touch.')]:
 bubble(53,yy-8,num);label(75,yy-10,title,12,'Rubik-Bold');para(body,75,yy-25,470,10.3,14)
para('Other photo labels: 1 backlight on/off; 2 earphone jack; 6 speaker header. The four separate bosses on the outer round plate are not the Pi mounting points.',M,105,511,9,12,GRAY)
# 03 / prep
def prep_figure():
 cad('A','rear',174,544,235,215,True);cad('C','rear',430,544,192,199,True)
 bubble(63,639,'A');bubble(329,639,'C')
 caption('Rear-facing CAD views. Prepare the prints with the connected electronics set aside.')

# 04 / wiring

def cable(points):
 # Heavy pale underlay separates cable crossings; no junctions are implied.
 c.saveState();c.setLineCap(1);c.setLineJoin(1)
 for color,width in [(white,6),(INK,3.4),(TEAL,2.1)]:
  c.setStrokeColor(color);c.setLineWidth(width);p=c.beginPath();p.moveTo(*points[0])
  for xy in points[1:]:p.lineTo(*xy)
  c.drawPath(p)
 c.restoreState()
def wiring():
 pi=cad('H','top',154,551,176,118)
 screen=cad('J','top',438,548,190,190)
 label(70,635,'RASPBERRY PI 4',10,'Rubik-Bold');label(372,660,'SCREEN REAR',10,'Rubik-Bold')
 pp=pi(11.2,-1);ph=pi(26,-1);pu=pi(87,9);sh=screen(9,29);su=screen(-44,-20)
 cable([ph,(ph[0],467),(305,467),(305,639),(sh[0],639),sh])
 cable([pu,(277,pu[1]),(277,su[1]),su])
 cable([(pp[0],439),pp])
 bubble(pp[0],431,'1');label(pp[0]+17,428,'POWER INTO PI',9,'Rubik-Bold')
 bubble(305,618,'2');label(224,675,'2  HDMI video',9,'Rubik-Bold')
 bubble(291,su[1],'3');label(245,su[1]+24,'3  USB touch',9,'Rubik-Bold')
 label(374,434,'Only the Pi Receives a Power Lead',8.5,color=GRAY)
 caption('Cable routing is schematic. 1: Pi power. 2: Pi HDMI0 to screen 3. 3: Pi USB-A to screen 5.',414)



# 05 / screen seating

def seat():
 cad('A','rear',166,548,223,198,True);cad('K','iso',432,553,195,198)
 bubble(60,640,'A');bubble(330,640,'B');arrow(312,550,283,550)
 label(80,431,'Open Rear of Front Case',9,color=GRAY);label(331,431,'Pi Already Attached and Connected',9,color=GRAY)
 caption('Lower the connected screen/Pi unit into A. HDMI and USB touch leads are omitted from this view for clarity.',414)


# 06 / retaining and cabling

def retaining():
 cad('C','rear',169,547,225,209,True);cad('D','rear',429,547,207,211,True)
 bubble(60,641,'C');bubble(329,641,'D');label(77,430,'Holder Clears the Mounted Pi',9,color=GRAY);label(348,430,'Route the Pi Power Lead',9,color=GRAY)
 caption('Fit the holder around the mounted Pi and connected leads. The wiring map is on page 6.',414)


# 09 / Pi mechanical attachment.
def mounting_figure():
 cad('L','iso',204,548,294,239)
 cad('L','side',453,548,165,222)
 label(48,672,'4 screws / Pi / 4 spacers / screen',9,'Rubik-Bold')
 label(385,672,'Side alignment',9,'Rubik-Bold')
 caption('Exploded views: all four Pi holes align with the four spacers. Separation is exaggerated.',414)


# 10 / Mounted rear and side view.
def clearance_figure():
 cad('K','top',187,550,233,233)
 cad('K','side',451,550,125,211)
 label(91,427,'Mounted Rear View',9,color=GRAY)
 label(385,427,'Board Separation',8.5,color=GRAY)
 caption('Connected screen/Pi unit before case assembly. HDMI and USB touch leads are omitted for clarity.',415)


# 07 / stand

def stand():
 cad('D','rear',174,543,212,208,True);bubble(60,641,'D');cad('E','front',443,597,99,88,True);bubble(366,628,'E');cad('F','front',443,477,147,77,True);bubble(350,481,'F');arrow(443,536,443,550)
 line(304,563,365,585,TEAL,.9,(3,3));caption('Separate CAD views of the rear cover and stand. Mate the shaped interfaces on the actual parts.',414)


# Sequential build: attach and connect the Pi before every enclosure step.
step(0,mounting_figure)
step(1,wiring)
step(2,clearance_figure)
step(3,prep_figure)
step(4,seat)
step(5,retaining)
step(6,stand)

# 08 / first boot
s=DATA['steps'][7];page('Assembly 08',s['title'],s['intro'])
cad('K','iso',200,566,243,170)
cad('K','side',460,566,112,170)
label(88,474,'Pi Mounted Behind the Screen',9,color=GRAY)
label(418,474,'Side View',9,color=GRAY)
c.setFillColor(PALE);c.roundRect(M,423,511,43,5,stroke=0,fill=1)
label(M+12,449,'FROM THE REPOSITORY ON THE PI',8,'Rubik-Bold',TEAL)
label(M+12,433,'python3 scripts/round-desktop.py install',11,'Rubik')
actions(s['actions']);checkpoint(s['check']);para(s['note'],M,83,511,8.5,11,GRAY)

# 09 / verification and recovery
page('Finish + fault finding','Check the complete build','A successful build has a retained screen, clear cable paths, a stable stand and a working desktop.')
checks=['Screen sits evenly; glass and electronics are not under pressure.','Holder and rear cover are fully engaged with no cracked clips.','No cable is caught in a seam or pulled tight against a connector.','Both stand joints hold and the base stays flat during touch use.','HDMI image and USB touch work after the cover is closed.','Pi is secure on four spacers; its cooler and airflow remain clear.']
y=676
for t in checks:
 c.setStrokeColor(TEAL);c.rect(M,y-11,10,10,stroke=1,fill=0);y=para(t,M+23,y,488,10.6,14)-15
label(M,464,'IF SOMETHING DOES NOT WORK',10,'Rubik-Bold',TEAL)
rows=[('No picture','Recheck Pi power, Pi boot, HDMI0 and the USB touch cable. Test with the rear cover open.'),('Picture, no touch','Use the screen Touch socket and a USB data cable. Confirm the Pi detects USB touch.'),('Flicker or resets','Check the Pi power supply and USB touch cable. Repeat the bench test before closing the cover. Power connects only to the Pi.'),('Screen or cover binds','Unplug power. Remove the affected part; inspect scale, print defects, alignment and cable clearance.'),('Desktop setup fails','Use the repository Getting started and troubleshooting sections. Check output name, resolution and scale.')]
y=442
rows=[(title_case(a),b) for a,b in rows]
for a,b in rows:
 label(M,y,a,10,'Rubik-Bold');end=para(b,198,y+2,355,10,13);line(M,end-12,W-M,end-12);y=end-29
para('To reopen',M,154,500,12,16,bold=True)
para('Shut down, disconnect power and support the display. Inspect which retaining feature releases before moving a cover or stand joint. Release it gently; avoid prying against the glass or pulling on cables.',M,132,511,10.5,14)
para('Record your physical fit checks before treating this guide as validated for repeat builds.',M,76,511,8.5,11,GRAY)

# 10 / provenance and engineering notes
page('References + CAD notes','What this guide is based on','Enclosure and screen views use supplied STEP geometry. The Pi and mounting hardware are simplified line illustrations.')
para('Model observations',M,681,511,13,17,bold=True)
para('The front case spans about 162 mm across and 49.3 mm in depth. The holder spans about 156.8 mm. The screen STEP assembly spans about 150 mm across and 18.1 mm including modelled rear components. These are CAD bounding extents, not manufacturing tolerances or fit certification.',M,656,511,10.5,14)
para('View conventions',M,582,511,13,17,bold=True)
para('Dark lines show visible edges; pale dashed lines show hidden edges. Neon green (#A3F66A) marks connections and actions. The Pi is a simplified illustration based on its mechanical outline, not supplied production CAD. Spacer height, exploded gaps and cable routes are illustrative. Check actual hardware and cover clearance.',M,557,511,10.5,14)
para('Sources and further instructions',M,481,511,13,17,bold=True)
refs=[('1  Enclosure design and original instructions','JN-Husch (@JNHusch), Case for round Waveshare 5in Display.','https://www.printables.com/model/847901-case-for-round-waveshare-5in-display'),('2  Screen connections and electrical information','Waveshare, 5inch 1080x1080 LCD wiki; SKU 24369.','https://www.waveshare.com/wiki/5inch_1080x1080_LCD'),('3  Raspberry Pi 4 board and mounting pattern','Raspberry Pi official mechanical drawing: 85 x 56 mm; 58 x 49 mm holes.','https://datasheets.raspberrypi.com/rpi4/raspberry-pi-4-mechanical-drawing.pdf'),('4  AroundOS installation and current limitations','Repository README and docs/round-desktop/README.md.','https://github.com/SalvSith/AroundOS')]
y=455
refs=[(title_case(t),d,u) for t,d,u in refs]
for title,description,url in refs:
 label(M,y,title,10,'Rubik-Bold');y=para(description,M,y-8,511,9.5,12)-5
 y=para(f'<link href="{html.escape(url)}" color="#315b20">{html.escape(url)}</link>',M,y,511,8,10)-17
para('Attribution and review status',M,186,511,12,16,bold=True)
para('Enclosure design and derived enclosure illustrations: CC BY-NC-SA 4.0, credited to JN-Husch. Preserve the parent folder LICENSE.txt. New manual text is offered under CC BY-NC-SA 4.0. Waveshare screen geometry remains credited to Waveshare; no separate redistribution license was supplied for that model. No endorsement is implied.',M,163,511,9,12)
para('Guide authored 7 November 2026. The source enclosure page was unavailable during this pass; print/assembly notes use the attributed folder README and supplied exploded view. Port labels follow the supplied Waveshare details-17 photo. The user confirmed the supplied mounting hardware. Screen STEP read directly; EXE not executed. Physical fit and powered assembly remain unverified.',M,95,511,8,10)
c.save();shutil.copyfile(OUT,ROOT/'AroundOS Assembly Manual.pdf')

# Editable companion: same procedural content and all part filenames.
md=['# '+DATA['title'],'',DATA['revision'],'',DATA['scope'],'','[Printable illustrated manual](AroundOS%20Assembly%20Manual.pdf)','','> CAD-based guide: physical fit, latch engagement, cable clearance and stand stability need a build check. The Pi mounts on the screen with the supplied spacers and screws. Spacer height, cable clearance and cooling require a physical check.','','## Parts','', '| ID | Part | File | Qty |','| --- | --- | --- | --- |']
for key,name,filename,qty,desc in DATA['parts']:md.append(f'| {key} | {name} | `{filename}` | {qty} |')
md+=['','## Equipment','','Raspberry Pi 4 Model B; four supplied spacers and matching screws; microSD card; suitable Pi USB-C supply; short micro-HDMI-to-HDMI cable; USB-A-to-USB-C data cable; keyboard; small screwdriver; soft cloth; print cleanup tools. Check cooler and cover clearance.']
for i,s in enumerate(DATA['steps'],1):
 md+=['',f'## {i}. {s["title"]}','',s['intro'],'']
 md.extend(f'{j}. {t}' for j,t in enumerate(s['actions'],1));md+=['','**Check:** '+s['check'],'','**Note:** '+s['note']]
md+=['','Run the installer on the Pi from the repository, as the desktop user:','','```sh','python3 scripts/round-desktop.py install','```','','Read the [repository installation guide](../../README.md#getting-started) first.','','## Final Checks','']+[f'- [ ] {t}' for t in checks]
md+=['','## Troubleshooting','', '| Symptom | Action |','| --- | --- |']+[f'| {a} | {b} |' for a,b in rows]
md+=['','## Sources and Attribution','']+[f'- [{title}]({url}) - {desc}' for title,desc,url in refs]
md+=['','Enclosure design and derived enclosure illustrations: JN-Husch, CC BY-NC-SA 4.0. New manual text: CC BY-NC-SA 4.0. See [LICENSE.txt](../LICENSE.txt). Screen model and its derived illustration are credited to Waveshare; no separate redistribution license was supplied. Port identification also follows the supplied Waveshare details-17 photograph. The user confirmed use of the supplied spacers and screws. Pi geometry is simplified; spacer heights and screw lengths are illustrative. The screen STEP was read directly; the EXE was not executed. Source enclosure page was unavailable during this pass; source print/assembly notes came from the attributed folder README and exploded image.','','## Rebuilding','', '`source/content.json` is the editable procedural source. `source/build_manual.py` rebuilds this Markdown file and the PDF using ReportLab, fontTools and the checked-in CAD projections. The builder embeds regular and bold faces from the project font at `src/round-desktop/fonts/Rubik.ttf`. `source/export_cad.py --screen /path/to/5inch-1080x1080-lcd-sku24369.stp` regenerates the projections using cadquery-ocp 8.0.1.1.0. Run `source/hardware_views.py --screen /path/to/screen.stp` after the enclosure exporter to regenerate the Pi and mounting views. Pi details are schematic; the hole pattern is 58 x 49 mm. The screen model itself is not copied into the repository.','','SVGs under `illustrations/` are editable vector CAD views. All views are independently positioned/scaled. Do not use the drawing scale as a manufacturing measurement.','']
(ROOT/'Assembly Guide.md').write_text('\n'.join(md))
print(f'Created {OUT} ({PAGE} pages) and enclosure-folder copy')
