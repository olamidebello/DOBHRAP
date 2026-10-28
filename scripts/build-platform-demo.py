"""Render an illustrated product walkthrough with sample data, not customer footage."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import subprocess,tempfile,textwrap
ROOT=Path(__file__).resolve().parents[1]
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def font(size,bold=False):return ImageFont.truetype(BOLD if bold else FONT,size)
SCENES=[('01','DISCOVER','Find your next opportunity.','Search government notices using your criteria.',['Opportunity search','Technology support services','Facilities support opportunity','Professional services opportunity'],'Search -> Details'),('02','UNDERSTAND','Read beyond the headline.','Follow retrieval. Review every available source.',['Contract details','Notice and response deadline','Description and attachments','Source completeness checks'],'Verify sources first'),('03','REVIEW','Turn source material into clarity.','Approve the price. Review the facts and gaps.',['Summary & recommendations','Requirements and evidence','Profile fit and missing facts','Provisional bid recommendation'],'Your review matters'),('04','CONNECT','Find a complementary capability.','Explore company listings and invite a discussion.',['Bid partners & networking','Published company capabilities','Open partnership opportunity','Private discussion after acceptance'],'You choose what to share'),('05','PREPARE','Build your response. Keep control.','Edit the proposal. Verify it. Approve the next step.',['Proposal workspace','Recommended approach and evidence','Staffing, gaps and reviewed pricing','Human review before external submission'],'Review -> Edit -> Approve')]
def render(scene,t):
 num,label,title,subtitle,rows,action=scene
 im=Image.new('RGB',(1280,720),'#102d31');d=ImageDraw.Draw(im)
 d.rounded_rectangle((30,30,1250,690),radius=26,fill='#f7f6ee')
 d.text((65,55),'OLAMIDE  /  BUSINESS SUITE',font=font(15,True),fill='#102d31')
 d.text((935,58),'ILLUSTRATED WORKFLOW',font=font(11),fill='#536965')
 d.text((65,125),num+' / '+label,font=font(15,True),fill='#26786a')
 # Keep each title on two short editorial lines.
 words=title.split();line='';lines=[]
 for word in words:
  if len(line+' '+word)>23:lines.append(line);line=word
  else:line=(line+' '+word).strip()
 lines.append(line)
 for i,line in enumerate(lines):d.text((65,170+i*54),line,font=font(40,True),fill='#102d31')
 for i,line in enumerate(textwrap.wrap(subtitle,width=43)):d.text((65,340+i*26),line,font=font(17),fill='#536965')
 d.rounded_rectangle((65,453,525,510),radius=24,fill='#d5f57e');d.text((85,469),action,font=font(16,True),fill='#102d31')
 d.text((65,570),'Sample data. Not a live contract or customer account.',font=font(12),fill='#536965')
 d.rounded_rectangle((595,115,1205,580),radius=22,fill='white',outline='#dce3d8',width=2)
 d.text((622,140),rows[0],font=font(20,True),fill='#102d31')
 for i,row in enumerate(rows[1:]):
  y=200+i*100;active=min(2,int(t*3))==i
  d.rounded_rectangle((620,y,1180,y+80),radius=12,fill='#edf4e7' if active else '#fafbf8',outline='#a7c892' if active else '#dce3d8',width=2)
  d.text((640,y+18),row,font=font(16,True),fill='#102d31');d.text((640,y+47),'Sample workflow  /  review details',font=font(12),fill='#536965')
 d.rounded_rectangle((65,642,1215,648),radius=3,fill='#dce3d8')
 progress=(int(num)-1+t)/5;d.rounded_rectangle((65,642,65+int(1150*progress),648),radius=3,fill='#26786a')
 d.text((65,664),'DISCOVER    /    UNDERSTAND    /    REVIEW    /    CONNECT    /    PREPARE',font=font(11),fill='#536965')
 return im
if __name__=='__main__':
 assets=ROOT/'assets';assets.mkdir(exist_ok=True)
 render(SCENES[0],.5).save(assets/'platform-demo-poster.png',optimize=True)
 with tempfile.TemporaryDirectory() as directory:
  for scene_index,scene in enumerate(SCENES):
   for frame in range(30):render(scene,frame/29).save(Path(directory)/f'{scene_index*30+frame:04d}.png')
  subprocess.run(['ffmpeg','-v','error','-y','-framerate','6','-i',directory+'/%04d.png','-c:v','libx264','-preset','slow','-crf','25','-pix_fmt','yuv420p','-movflags','+faststart','-r','24',str(assets/'platform-demo.mp4')],check=True)
 captions='WEBVTT\n\n'
 for i,scene in enumerate(SCENES):captions+=f'{i+1}\n00:{i*5:02d}.000 --> 00:{(i+1)*5:02d}.000\n'+scene[2]+' '+scene[3]+'\n\n'
 (assets/'platform-demo.vtt').write_text(captions)
