#!/usr/bin/env python3
########################################################################
# Copyright 2019 Bernd Breitenbach
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>
#
########################################################################

import serial
import argparse
import sys
import time
import re
import os
from PIL import Image,ImageDraw,ImageFont

VER = sys.version_info
if VER[0]<3:
    raise Exception("at least python version 3 is needed")

########################################################################

STDOUT=sys.stdout
STDERR=sys.stderr

def _StdAsk(question):
    sys.stdout.write(question)
    sys.stdout.write(" (Y/n)\n")
    sys.stdout.flush()
    return sys.stdin.readline()[0].lower()!='n'

Ask=_StdAsk

class Logger(object):
    LEVELS={"FATAL":-3,"ERROR":-2,"WARN":-1,"INFO":0,"DEBUG":1}
    LOGGER=None
    
    def __init__(self,verbosity="WARN"):
        self.verbosity=verbosity


    def fatal(self,fmt,*args):
        self.log("FATAL",fmt,*args)
        sys.exit(-1)
        
    def error(self,fmt,*args):
        self.log("ERROR",fmt,*args)

    def warn(self,fmt,*args):
        self.log("WARN",fmt,*args)

    def debug(self,fmt,*args):
        self.log("DEBUG",fmt,*args)
            
    def info(self,fmt,*args):
        self.log("INFO",fmt,*args)
            
    def log(self,severity,fmt,*args):
        lev=self.LEVELS.get(severity,99)
        if self.verbosity>=lev:
            if lev!=0:
                STDERR.write("[%s]: "%severity)
                STDERR.write(fmt % args)
            else:
                STDOUT.write(fmt % args)
                STDOUT.flush()

    def logging(self,severity):
        return self.LEVELS.get(severity,99)<=self.verbosity

    @classmethod
    def set(cls,logger):
        cls.LOGGER=logger

########################################################################

class Base(object):
    def __init__(self,args):
        self.lim=args.lim
        self.info=Logger.LOGGER.info
        self.debug=Logger.LOGGER.debug
        self.fatal=Logger.LOGGER.fatal
        self.error=Logger.LOGGER.error
        self.warn=Logger.LOGGER.warn        
        self.logging=Logger.LOGGER.logging

    ACK=bytes([0x9])

    def limit(self,val,high=99999,low=-99999):
        high=min(high,self.lim)
        low=max(low,-self.lim)
        if val>high:
            self.warn("value %d to high; setting to %d\n",val,high)
            val=high
        elif val<low:
            self.warn("value %d to low; setting to %d\n",val,low)
            val=low
        if val<0:
            val+=65536
        return val

    def setValue(self,data,idx,val):
        val=self.limit(val)
        data[idx]=val>>8
        data[idx+1]=val&0xff
        
########################################################################

    
class EngraverData(Base):
    X_IDX=7
    Y_IDX=9
    DEPTH_IDX=14
    POW_IDX=11
    EXT1_IDX=3
    EXT2_IDX=5
    #        CMD             ?    ?     ?    ?   XH   XL   YH   YL    POWER    ?  DEPTH
    HEADER=[0x23,0x00,0x0f,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x03,0xe8,0x00,0x1] 
    HEADER_ACK=bytes([0xff,0xff,0xff,0xfe])
    
    #     CMD  SZH  SZL   DATA...                                                         CHECKBYTE
    #ROW=[0x22,0x00,0x11,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x0f,0x00] #

    EPILOG1=[0x0a,0x00,0x04,0x00]
    EPILOG2=[0x24,0x00,0x04,0x00,0x24,0x00,0x04,0x00]
    
    def __init__(self,sizex,sizey,args):
        Base.__init__(self,args)        
        self.header=self.HEADER[:]
        self._size=(sizex,sizey)
        self.setValue(self.header,self.X_IDX,sizex)
        self.setValue(self.header,self.Y_IDX,sizey)
        self.header[self.DEPTH_IDX]=self.limit(args.depth,100,0)
        self.setValue(self.header,self.POW_IDX,self.limit(args.power,100,0)*10)
        #self.setValue(self.header,self.EXT1_IDX,self.limit(args.ext,2048,0))
        #self.setValue(self.header,self.EXT2_IDX,self.limit(args.ext,2048,0))
        self.rows=[]

    def size(self):
        return self._size
    
    def addRow(self,data):
        row=[0x22,0,0]+data
        self.setValue(row,1,len(row)+1)
        cbyte=sum(row)
        if cbyte>256:
            cbyte=(0x100-(cbyte&0xff))&0xff
        row.append(cbyte) #checkbyte
        if self.logging("DEBUG"):
            ldata=row[:3]+[format(r,"#010b")[2:] for r in row[3:-1]]+row[-1:]
            self.debug("rowdata: %s\n",ldata)
        self.rows.append(row)
        
    def sendData(self,engraver):
        self.info("waiting for engraver\n")
        engraver.send(self.header,self.HEADER_ACK)
        total=len(self.rows)
        self.info("sending data (%d rows) ...\n"%total)
        per=0
        ri=0
        for row in self.rows:
            engraver.send(row)
            ri+=100
            cper=ri//total
            if per!=cper:
                per=cper
                self.info("\r%02d%% done",per)
        self.info("\n")
                
        engraver.send(self.EPILOG1)
        engraver.send(self.EPILOG2,None)

    #
    #######
    #

    @staticmethod
    def _trfImage(im,args):
        if args.trf:
            for t in args.trf:
                Logger.LOGGER.debug("transforming image:%s\n",t[0])
                im=im.transpose(t[1])
        return im

    @staticmethod
    def _removeAlpha(img):
        for i,px in enumerate(img.getdata()):
            width,height=img.size
            if px[3]<255:
                y=i/width
                w1=(255-px[3])
                w2=px[3]/255.
                img.putpixel((i%width,i//width),(int(px[0]*w2)+w1,int(px[1]*w2)+w1,int(px[2]*w2)+w1,255))

    @staticmethod
    def _imageToData(im,args):
        data=True
        if args.size and args.size!=im.size:
            im.thumbnail(args.size)
            Logger.LOGGER.info("image resized to width:%s height:%s\n",formatUnit(im.width),formatUnit(im.height))
        Logger.LOGGER.info("preparing image data width:%s height:%s\n",formatUnit(im.width),formatUnit(im.height))
        im=im.convert('1',dither=Image.FLOYDSTEINBERG) # to black and white        
        im=EngraverData._trfImage(im,args)
        if args.dummy:
            if args.dummy!=".":
                im.save(args.dummy)
        else:
            data=EngraverData(im.width,im.height,args)
            inv=args.invert
            bytesInRow=(im.width+7)>>3
            for i in range(im.height):
                row=bytesInRow*[0xff]
                for j in range(im.width):
                    bitno=7-(j&7)
                    bitval=inv ^ (im.getpixel((j,i))!=0)
                    idx=j>>3
                    row[idx]=(row[idx]&~(1<<bitno))|(bitval<<bitno)
                data.addRow(row)
        return data

    @staticmethod
    def _crop(img):
        bbox=(img.width-1,img.height-1,0,0)
        for i,px in enumerate(img.getdata()):
            if px!=(255,255,255):
                x=i%img.width
                y=i//img.width
                bbox=(min(bbox[0],x-1),min(bbox[1],y-1),max(bbox[2],x+1),max(bbox[3],y+1))
        return img.crop(bbox)

    @staticmethod
    def imageFrame(args):
        im=Image.open(args.image)
        im.load()
        if args.size:
            im.thumbnail(args.size)
        im=EngraverData._trfImage(im,args)
        return im.size
    
    @staticmethod
    def checkerboard(args):
        size=args.checker[0]
        number=args.checker[1]
        inv=args.invert
        tsize=size*number
        data=EngraverData(tsize,tsize,args)
        bytesInRow=(tsize+7)>>3
        for i in range(tsize): #rows
            row=bytesInRow*[0xff]
            for j in range(tsize):
                bitno=7-(j&7)
                bitval=inv ^ (((i//size)+(j//size))&1)
                idx=j>>3
                row[idx]=(row[idx]&~(1<<bitno))|(bitval<<bitno)
            data.addRow(row)
        return data

    
    @staticmethod
    def processImage(im,args):
        if args.size:
            im.thumbnail(args.size)
        im=im.convert('1',dither=Image.FLOYDSTEINBERG) # to black and white        
        im=EngraverData._trfImage(im,args)
        return im

    @staticmethod
    def preprocessImage(im):
        if im.mode=='P': # convert file with color palette (e.g. gif with transparency)
            im=im.convert('RGBA')
        if im.mode=='RGBA': # replace transparent pixels with white
            EngraverData._removeAlpha(im)
        return im

    @staticmethod
    def fromImage(args):
        im=Image.open(args.image)
        im.load()
        im=EngraverData.preprocessImage(im)
        return EngraverData._imageToData(im,args)

    @staticmethod
    def imageFromText(args):
        size=tuple(max(s,args.lim) if s==0 else s for s in args.size or (args.lim,args.lim))
        mside=max(size)
        maxw=min(mside*2,3072)
        maxh=min(mside*2,2048)
        im=Image.new("RGB",(maxw,maxh),(255,255,255))
        fsz=12
        text="  %s  "%args.text
        while True:
            nfsz=(fsz*12)//10
            font=ImageFont.truetype(args.font,nfsz)
            sz=font.getsize(text)
            if sz[0]>maxw or sz[1]>(maxh//2):
                font=ImageFont.truetype(args.font,fsz)
                Logger.LOGGER.info("using font:%s\n",font.getname())
                sz=font.getsize(text)
                pos=((maxw-sz[0])//2,(maxh-sz[1])//2)
                break
            fsz=nfsz
        draw=ImageDraw.Draw(im)
        draw.text(pos,text,(0,0,0),font)
        im=EngraverData._crop(im)
        im.thumbnail(size)
        Logger.LOGGER.info("text image resized to width:%s height:%s\n",formatUnit(im.width),formatUnit(im.height))
        return im
    
                
    @staticmethod
    def fromText(args):
        return EngraverData._imageToData(imageFromText(args),args)
    

########################################################################

class Engraver(Base):
    FAN_ON=[0x4,0x0,0x4,0x0]
    FAN_OFF=[0x5,0x0,0x4,0x0]
    CONNECT=[0xa,0x0,0x4,0x0,0xff,0x0,0x4,0x0]
    HOME=[0x17,0x0,0x4,0x0]
    FRAME_STOP=[0x21,0x00,0x04,0x00]
    PAUSE=[0x18,0x0,0x4,0x0]
    CONT=[0x19,0x0,0x4,0x0]
    STOP=[0x27,0x0,0x4,0x0]
    
    X_IDX=3
    Y_IDX=5
    MOVE_XY=[0x01,0x00,0x07,0x00,0x00,0x00,0x00]

    FX_IDX=3
    FY_IDX=5
    MX_IDX=7
    MY_IDX=9
    FRAME_XY=[0x20,0x00,0x0b,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
    
    CONNECTED=bytes([0x2,0x1,0x4])
    COMPLETED=bytes([0xff,0xff,0xff,0xff])

    def __init__(self,args):
        Base.__init__(self,args)
        self.device=args.device
        self.speed=args.speed
        self.ser=None
        self.opened=False
        self.connected=False
        self.fanOn=True
        
    def open(self):
        self.debug("opening device %s\n",self.device)
        if self.opened:
            self.error("cannot open device %s more than once!\n",self.device)
            return
        try:
            self.ser=serial.Serial(self.device, self.speed,timeout=30)
            self.opened=True
        except Exception as ex:
            self.fatal("%s\n",ex)

    def isOpened(self):
        return self.opened

    def isConnected(self):
        return self.connected
    
    def close(self):
        if self.opened:
            self.ser.close()
            self.opened=False
        else:
            self.warn("could not close device; %s iss not open\n",self.device)

    def _check(self):
        if not self.connected:
            self.fatal("connection failed! Could not detect engraver!")
        
    def send(self,data,exp=Base.ACK):
        self.debug("sending:%s\n",data)
        self.ser.write(bytes(data))
        if exp!=None:
            ack=self.ser.read(len(exp))
            if ack==exp:
                self.debug("got acknowledge\n")
            else:
                self.fatal("didn't got acknowledge; got:%s\n",ack)
        else:
            self.debug("no acknowledge expected!\n")

    def fan(self,on):
        if on!=None:
            self._check()
            if on:
                self.debug("switching fan on\n")
                self.send(self.FAN_ON)
                self.fanOn=True
            else:
                self.debug("switching fan off\n")
                self.send(self.FAN_OFF)
                self.fanOn=False

    def isFanOn(self):
        return self.fanOn
    
    def connect(self):
        self.debug("connecting...\n")
        self.send(self.CONNECT)
        resp=self.ser.read(3)
        self.connected=(resp==self.CONNECTED)
        self._check()
        self.debug("...connected\n")

    def home(self):
        self.send(self.HOME)

    def pause(self):
        self.send(self.PAUSE)
        
    def cont(self):
        self.send(self.CONT)
        
    def stop(self):
        self.send(self.STOP)
        
    def move(self,dx,dy):
        self.debug("start moving delta_x=%s delta_y=%s\n",formatUnit(dx),formatUnit(dy))
        data=self.MOVE_XY[:]
        self.setValue(data,self.X_IDX,dx)
        self.setValue(data,self.Y_IDX,dy)
        self.send(data)
        self.debug("move finished\n")
        self.info("laser moved x:%s y:%s\n",formatUnit(dx),formatUnit(dy))
        
    def calcFrame(self,fx,fy,useCenter,centerAxis):
        if useCenter:
            if centerAxis=='x':
                m=(1,fy,0,-fy//2)
            elif centerAxis=='y':
                m=(fx,1,-fx//2,0)
            else:
                m=(fx,fy,-fx//2,-fy//2)
        else:
            if centerAxis=='x':
                m=(1,fy,fx//2,0)
            elif centerAxis=='y':
                m=(fx,1,0,fy//2)
            else:
                m=(fx,fy,0,0)
        return m
    
    def frameStart(self,fx,fy,useCenter,centerAxis):
        m=self.calcFrame(fx,fy,useCenter,centerAxis)
        self.move(m[2],m[3])
        self.info("showing frame x:%s y:%s\n",formatUnit(m[0]),formatUnit(m[1]))
        data=self.FRAME_XY[:]
        self.setValue(data,self.FX_IDX,m[0])
        self.setValue(data,self.FY_IDX,m[1])
        #self.setValue(data,self.MX_IDX,mx) # don't work with negative values
        #self.setValue(data,self.MY_IDX,my)
        self.send(data)

    def frameStop(self,fx,fy,useCenter,centerAxis):
        self.debug("stop showing frame\n")
        self.send(self.FRAME_STOP)
        m=self.calcFrame(fx,fy,useCenter,centerAxis)
        self.move(-m[2],-m[3])

    def frame(self,fx,fy,useCenter,centerAxis):
        try:
            self.frameStart(fx,fy,useCenter,centerAxis)
            sys.stdout.write("press return to finish\n")
            sys.stdout.flush()
            sys.stdin.readline()
        finally:
            engraver.frameStop(fx,fy,useCenter,centerAxis)
    
    def burn(self,data,useCenter):
        try:
            if useCenter:
                dx,dy=data.size()
                self.move(-dx//2,-dy//2)
            data.sendData(self)
            msg="\rcompleted!\n"
            self.info("engraving...\n")
            if self.logging("DEBUG"):
                start=time.time()
            while True:
                try:
                    resp=self.ser.read(4)
                    if resp==self.COMPLETED:
                        break
                    self.info("\r%02d%% done",resp[3])
                except KeyboardInterrupt:
                    self.pause()
                    if Ask("Paused! Do you want to cancel the process?"):
                        self.stop()
                        msg="\rcanceled!\n"
                        break
                    self.cont()
            if self.logging("DEBUG"):
                self.debug("engraving time: %.1f secs\n",time.time()-start)
            self.info(msg)
        finally:
            if useCenter:
                self.move(dx//2,dy//2)



########################################################################
STEPS_PER_MM=500./25.4 # 500 DPI
        
def valuePair(para):
    vals=para.lstrip().split(":")
    if len(vals)==1:
        vals+=['']
    return tuple(unitValue(p) for p in vals)

def unitValue(para):
    m=re.match("([-+]?[0-9]+(.[0-9]*)?)mm",para)
    if m:
        return int(float(m.group(1))*STEPS_PER_MM)
    return int(para or '0')

def formatUnit(val):
    return "%dpx (%.1fmm)"%(val,val/STEPS_PER_MM)

def imageTrf(para):
    trf={'cw':Image.ROTATE_270,
     'ccw':Image.ROTATE_90,
     'turn':Image.ROTATE_180,
     'tb':Image.FLIP_TOP_BOTTOM,
     'lr':Image.FLIP_LEFT_RIGHT}.get(para)
    if trf==None:
        raise ValueError
    return (para,trf)

########################################################################

    
    
    

DESCRIPTION="""
Engraver program for using a KKMoon laser engraver
V0.9.1 (c) 2019 by Bernd Breitenbach
This program comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it
under certain conditions; See COPYING for details.
"""

if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description=DESCRIPTION,
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                     epilog='''All distances and sizes can be specified in steps or millimeter by just adding mm to a given number.
                                               The KKMoon engraver has a resolution of 500 steps/inch (19.685.. steps/mm)''')
    parser.add_argument('-d', '--device',metavar="device",help='the serial device',default="/dev/ttyUSB0")
    parser.add_argument('-s', '--speed',metavar="speed",help='the speed of the serial device',type=int,default=115200)
    parser.add_argument('-v', '--verbosity',help='increase verbosity level ',action='count',default=0)
    parser.add_argument('--fan',help='switch fan on',dest='fan',action='store_true',default=None)
    parser.add_argument('--no-fan',help='switch fan off',dest='fan',action='store_false',default=None)
    parser.add_argument('-m',help='move the laser x/y steps',metavar='x:y',dest='move',type=valuePair,default=None)
    parser.add_argument('-f',help='draw a moving frame ',metavar='x:y',dest='frame',type=valuePair,default=None)
    parser.add_argument('-F','--image-frame',metavar='imagefile',help='draw a moving frame as large as the given image')
    parser.add_argument('-c','--center-only',metavar='x|y',help='draw a center line only (x or y) with the other dimension taken from an image. Has an effect only when used with the -F option',
                        dest='center',choices=['x','y'])
    
    parser.add_argument('-H','--home',help='move the laser to pos 0/0',dest='home',default=False,action='store_true')
    parser.add_argument('-C','--center-reference',help='use the current laser postion as reference point for the center of the image or text to engrave; usually it will be the top-left of the image',dest='centerref',default=False,action='store_true')
    parser.add_argument('-D','--depth',metavar="depth",help='set the burn depth of the laser (0-100)',dest='depth',default=10,type=int)
    parser.add_argument('-P','--power',metavar="power",help='set the laser power (0-100)',dest='power',default=100,type=int)
    parser.add_argument('--checkerboard',help='engrave a quadratic checkerboard pattern of given tile size and number',
                        metavar=('tile_size','number'),type=unitValue,dest='checker',nargs=2,default=None)
    parser.add_argument('-i','--image',metavar='imagefile', help='the image file to engrave')
    parser.add_argument('-t','--text',metavar='text', help='the text to engrave; you also have to specify a font with the --font option')
    parser.add_argument('--font',metavar='font', help='the truetype/opentype font used to engrave text')
    parser.add_argument('-T','--transform',metavar='cw|ccw|turn|tb|lr', help='''transform the image after any other operation just before engraving.
                                                    The following transformations are possible:
                                                    cw - rotate 90 degrees clockwise;  ccw - rotate 90 degrees counterclockwise;
                                                    turn - rotate 180 degrees ; tb - flip top-bottom ; lr - flip left-right ''',type=imageTrf,dest='trf',nargs='+')
    parser.add_argument('-S','--maxsize',help='scale the image down to match maximal width and height; the aspect ratio is kept',
                        metavar='w:h',dest='size',type=valuePair,default=None)    
    parser.add_argument('--invert', help='invert the image/text before engraving',default=False,action='store_true')
    parser.add_argument('--limit', help='set maximum no. of steps in x/y direction',metavar=('steps'),dest='lim',type=int,default=1575)
    parser.add_argument('--dry-run', help='do not engrave anything; you can specify an optional file for saving engraving data'
                        ,metavar=('imagefile'),dest='dummy',const=".",default=None,nargs='?')
    
    #parser.add_argument('-X', help='extended parameter',dest='ext',type=int,default=0) 
    
    args = parser.parse_args()
    Logger.set(Logger(args.verbosity))
    engraver=Engraver(args)
    if not args.dummy:
        engraver.open()
        engraver.connect()
        engraver.fan(args.fan)
    data=None
    
    if args.home:
        engraver.home()
    if args.move:
        engraver.move(*args.move)
    if args.image_frame:
        args.image=args.image_frame
        args.frame=EngraverData.imageFrame(args)
    if args.frame:
        engraver.frame(*args.frame,args.center,args.centerref)
    elif args.checker:
        data=EngraverData.checkerboard(args)
    elif args.image:
        data=EngraverData.fromImage(args)
    elif args.text:
        if args.font:
            data=EngraverData.fromText(args)
        else:
            Logger.LOGGER.error("no font is given; please use --font to specify a truetype/opentype font\n\n")
    if not args.dummy:
        if data:
            if args.fan==None: # switch on while engraving
                engraver.fan(True)
            engraver.burn(data,args.centerref)
        engraver.close()
    if not (args.home or args.move or args.frame or data or args.verbosity or args.fan!=None or args.dummy):
        parser.print_help()
