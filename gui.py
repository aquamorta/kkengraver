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

import sys
import os
import json
import hashlib
import base64
import struct
import traceback
import codecs
import threading
import queue
import argparse
import cgi
import webbrowser
import socket
import time
import re
import ctypes

from select import select
from http.server import SimpleHTTPRequestHandler,HTTPServer
from PIL import Image,ImageDraw,ImageFont
from urllib.parse import parse_qs
from io import BytesIO

from engraver import Logger,Engraver,EngraverData,DESCRIPTION,unitValue,imageTrf,UI,contrastBrightnessValue

##############################################################################
FONTDIR='fonts'

STREAM = 0x0
TEXT = 0x1
BINARY = 0x2
CLOSE = 0x8
PING = 0x9
PONG = 0xA

HEADERB1 = 1
HEADERB2 = 3
LENGTHSHORT = 4
LENGTHLONG = 5
MASK = 6
PAYLOAD = 7

STATUS_CODES = [1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011, 3000, 3999, 4000, 4999]

# key value store
STORAGE={}

def StoreImage(fd):
    global args
    img=Image.open(fd)
    img.load()
    img=EngraverData.preprocessImage(img,args)
    STORAGE['image']=img
    

class Websocket(object):
    def __init__(self,socket,registry):
        self.socket=socket
        self.registry=registry
        self.fileno=socket.fileno
        self.fin = 0
        self.data = bytearray()
        self.opcode = 0
        self.hasmask = 0
        self.maskarray = None
        self.length = 0
        self.lengtharray = None
        self.index = 0
        self.request = None
        self.usingssl = False

        self.frag_start = False
        self.frag_type = BINARY
        self.frag_buffer = None
        self.frag_decoder = codecs.getincrementaldecoder('utf-8')(errors='strict')
        self.closed = False
        self.lastupdate=0;
        self.state = HEADERB1

        # restrict the size of header and payload for security reasons
        self.maxheader = 65536
        self.maxpayload = 33554432
        self.registry.Register(self)
    
    def DoRead(self):
        msg=os.read(self.fileno(),16384)
        if msg:
            for d in msg:
                self.DecodeMessage(d)
        else:
            self.DoClose()
                 
    def DoClose(self):
        print ('websocket closed',self.fileno())
        os.close(self.fileno())
        self.registry.Unregister(self)

        
    def DoWrite(self,data):
        if isinstance(data, str):
            opcode = TEXT
            data = data.encode('utf-8')
        else:
            opcode = BINARY
        payload = bytearray()

        b1 = 0x80|opcode

        length = len(data)
        payload.append(b1)

        if length <= 125:
           b2 = length
           payload.append(b2)

        elif length >= 126 and length <= 65535:
           b2 = 126
           payload.append(b2)
           payload.extend(struct.pack("!H", length))

        else:
           b2 = 127
           payload.append(b2)
           payload.extend(struct.pack("!Q", length))

        if length > 0:
           payload.extend(data)
        self.socket.send(payload)


    def HandlePacket(self):
      if self.opcode == CLOSE:
         status = 1000
         reason = u''
         length = len(self.data)

         if length == 0:
            pass
         elif length >= 2:
            status = struct.unpack_from('!H', self.data[:2])[0]
            reason = self.data[2:]

            if status not in STATUS_CODES:
                status = 1002

            if len(reason) > 0:
                try:
                    reason = reason.decode('utf8', errors='strict')
                except:
                    status = 1002
         else:
            status = 1002

         return

      elif self.fin == 0:
          if self.opcode != STREAM:
              if self.opcode == PING or self.opcode == PONG:
                  raise Exception('control messages can not be fragmented')

              self.frag_type = self.opcode
              self.frag_start = True
              self.frag_decoder.reset()

              if self.frag_type == TEXT:
                  self.frag_buffer = []
                  utf_str = self.frag_decoder.decode(self.data, final = False)
                  if utf_str:
                      self.frag_buffer.append(utf_str)
              else:
                  self.frag_buffer = bytearray()
                  self.frag_buffer.extend(self.data)

          else:
              if self.frag_start is False:
                  raise Exception('fragmentation protocol error')

              if self.frag_type == TEXT:
                  utf_str = self.frag_decoder.decode(self.data, final = False)
                  if utf_str:
                      self.frag_buffer.append(utf_str)
              else:
                  self.frag_buffer.extend(self.data)

      else:
          if self.opcode == STREAM:
              if self.frag_start is False:
                  raise Exception('fragmentation protocol error')

              if self.frag_type == TEXT:
                  utf_str = self.frag_decoder.decode(self.data, final = True)
                  self.frag_buffer.append(utf_str)
                  self.data = u''.join(self.frag_buffer)
              else:
                  self.frag_buffer.extend(self.data)
                  self.data = self.frag_buffer

              self.registry.Receive(self.data)

              self.frag_decoder.reset()
              self.frag_type = BINARY
              self.frag_start = False
              self.frag_buffer = None

          elif self.opcode == PING:
              self._sendMessage(False, PONG, self.data)

          elif self.opcode == PONG:
              pass

          else:
              if self.frag_start is True:
                  raise Exception('fragmentation protocol error')

              if self.opcode == TEXT:
                  try:
                      self.data = self.data.decode('utf8', errors='strict')
                  except Exception as exp:
                      raise Exception('invalid utf-8 payload')
                  
              self.registry.Receive(self.data)


    def DecodeMessage(self, byte):
      if self.state == HEADERB1:
         self.fin = byte & 0x80
         self.opcode = byte & 0x0F
         self.state = HEADERB2

         self.index = 0
         self.length = 0
         self.lengtharray = bytearray()
         self.data = bytearray()

         rsv = byte & 0x70
         if rsv != 0:
            raise Exception('RSV bit must be 0')

      elif self.state == HEADERB2:
         mask = byte & 0x80
         length = byte & 0x7F

         if self.opcode == PING and length > 125:
             raise Exception('ping packet is too large')

         if mask == 128:
            self.hasmask = True
         else:
            self.hasmask = False

         if length <= 125:
            self.length = length

            # if we have a mask we must read it
            if self.hasmask is True:
               self.maskarray = bytearray()
               self.state = MASK
            else:
               # if there is no mask and no payload we are done
               if self.length <= 0:
                  try:
                     self.HandlePacket()
                  finally:
                     self.state = HEADERB1
                     self.data = bytearray()

               # we have no mask and some payload
               else:
                  #self.index = 0
                  self.data = bytearray()
                  self.state = PAYLOAD

         elif length == 126:
            self.lengtharray = bytearray()
            self.state = LENGTHSHORT

         elif length == 127:
            self.lengtharray = bytearray()
            self.state = LENGTHLONG

      elif self.state == LENGTHSHORT:
         self.lengtharray.append(byte)

         if len(self.lengtharray) > 2:
            raise Exception('short length exceeded allowable size')

         if len(self.lengtharray) == 2:
            self.length = struct.unpack_from('!H', self.lengtharray)[0]

            if self.hasmask is True:
               self.maskarray = bytearray()
               self.state = MASK
            else:
               # if there is no mask and no payload we are done
               if self.length <= 0:
                   try:
                       self.HandlePacket()
                   finally:
                       self.state = HEADERB1
                       self.data = bytearray()

                    # we have no mask and some payload
               else:
                   #self.index = 0
                   self.data = bytearray()
                   self.state = PAYLOAD

      elif self.state == LENGTHLONG:
          self.lengtharray.append(byte)

          if len(self.lengtharray) > 8:
              raise Exception('long length exceeded allowable size')

          if len(self.lengtharray) == 8:
              self.length = struct.unpack_from('!Q', self.lengtharray)[0]

              if self.hasmask is True:
                  self.maskarray = bytearray()
                  self.state = MASK
              else:
                  # if there is no mask and no payload we are done
                  if self.length <= 0:
                      try:
                          self.HandlePacket()
                      finally:
                          self.state = HEADERB1
                          self.data = bytearray()

                  # we have no mask and some payload
                  else:
                      #self.index = 0
                      self.data = bytearray()
                      self.state = PAYLOAD

      # MASK STATE
      elif self.state == MASK:
          self.maskarray.append(byte)

          if len(self.maskarray) > 4:
              raise Exception('mask exceeded allowable size')

          if len(self.maskarray) == 4:
              # if there is no mask and no payload we are done
              if self.length <= 0:
                  try:
                      self.HandlePacket()
                  finally:
                      self.state = HEADERB1
                      self.data = bytearray()

              # we have no mask and some payload
              else:
                  #self.index = 0
                  self.data = bytearray()
                  self.state = PAYLOAD

      # PAYLOAD STATE
      elif self.state == PAYLOAD:
          if self.hasmask is True:
              self.data.append( byte ^ self.maskarray[self.index % 4] )
          else:
              self.data.append( byte )

          # if length exceeds allowable size then we except and remove the connection
          if len(self.data) >= self.maxpayload:
              raise Exception('payload exceeded allowable size')

          # check if we have processed length bytes; if so we are done
          if (self.index+1) == self.length:
              try:
                  self.HandlePacket()
              finally:
                  #self.index = 0
                  self.state = HEADERB1
                  self.data = bytearray()
          else:
              self.index += 1



##############################################################################

def parseTrf(trf):
    if trf:
        trf=[imageTrf(i) for i in trf.split(' ')]
    return trf

        
class GUIHandler(SimpleHTTPRequestHandler):

    def __init__(self,fd,addr,server):
        self.server=server
        self.hand_over=False
        return SimpleHTTPRequestHandler.__init__(self,fd,addr,server)
            
    def handle(self):
        self.close_connection = 1

        self.handle_one_request()
        while not self.close_connection and not self.hand_over:
            self.handle_one_request()

    def finish(self):
        if not self.wfile.closed:
            try:
                self.wfile.flush()
            except socket.error:
                # A final socket error may have occurred here, such as
                # the local error ECONNABORTED.
                pass
        if not self.hand_over:
            self.wfile.close()
            self.rfile.close()

    def _JSONHeader(self):
        self.send_response(200)
        self.send_header("Content-Type","application/json; charset=utf-8");
        self.end_headers()

    def log_message(self, format, *args):
        sys.stderr.write("%s - - [%s] %s\n" %
                         (self.client_address[0],
                          self.log_date_time_string(),
                          format%args))

    def GenSecAccept(self,key):
        UUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
        k = key.encode('ascii') + UUID.encode('ascii')
        k_s = base64.b64encode(hashlib.sha1(k).digest()).decode('ascii')
        return k_s
    
    def CreateWS(self,args):
        key=self.headers.get("Sec-WebSocket-Key")
        if key and self.headers.get("Upgrade","").lower().index("websocket")>=0:
            self.hand_over=True
            self.close_connection=0
            self.protocol_version = "HTTP/1.1"
            self.send_response(101)
            self.send_header("Access-Control-Allow-Credentials","true")
            self.send_header("Access-Control-Allow-Headers","content-type")
            self.send_header("Access-Control-Allow-Headers","authorization")
            self.send_header("Access-Control-Allow-Headers","x-websocket-extensions")
            self.send_header("Access-Control-Allow-Headers","x-websocket-version")
            self.send_header("Access-Control-Allow-Headers","x-websocket-protocol")
            self.send_header("Connection","Upgrade")
            self.send_header("Sec-WebSocket-Accept",self.GenSecAccept(key))
            self.send_header("Upgrade","websocket")
            self.end_headers()
            self.server.KeepOpen()
            ws=Websocket(self.request,self.server)
        else:
            self.send_error(400,"illegal request")

    def output(self,text,flush=False):
        self.wfile.write(bytes(text,'utf-8'))
        if flush:
            self.wfile.flush()

            
    def GetFonts(self,args):
        exp=re.compile("\.(ttf|pfb)$")
        fonts=list(filter(lambda f: exp.search(f,re.I)!=None,os.listdir(FONTDIR)))
        fonts.sort()
        digest=hashlib.sha1(bytes(str(fonts),'utf-8')).hexdigest()
        flist=[]
        if STORAGE.get('fonthash')!=digest:
            for f in fonts:
                try:
                    fname=ImageFont.truetype('%s/%s'%(FONTDIR,f)).getname()
                    fname="%s (%s)"%(fname[0],fname[1])
                    flist.append({'name':fname,'file':f})
                except:
                    Logger.LOGGER.error("cannot load font from file '%s'\n",f)
            STORAGE['fonts']=flist
            STORAGE['fonthash']=digest
        self._JSONHeader()
        self.output(json.dumps(STORAGE['fonts']))

    def SendImage(self,img):
        self.send_response(200)
        self.send_header("Pragma-directive","no-cache")
        self.send_header("Cache-directive","no-cache")
        self.send_header("Cache-Control","no-store, no-cache, must-revalidate")
        self.send_header("Content-Type","image/png");
        self.end_headers()
        fd = BytesIO()
        img.save(fd, "png")
        self.wfile.write(fd.getvalue())
        self.wfile.flush()

    
    def RenderImageFromText(self,dict):
        for p in ['text','font','width','height']:
            if  p not in dict:
                self.send_error(404, "parameter '%s' is missing"%p)
                return
        hsh=hashlib.sha1()
        global args 
        args.text=dict['text'][0]
        hsh.update(bytes(args.text,'utf-8'))
        args.size=(unitValue(dict['width'][0]),unitValue(dict['height'][0]))
        hsh.update(bytes(str(args.size),'utf-8'))
        args.font="%s/%s"%(FONTDIR,dict['font'][0])
        hsh.update(bytes(args.font,'utf-8'))

        digest=hsh.hexdigest()
        if STORAGE.get('imagehash')==digest:
            img=STORAGE['textimage']
        else:
            STORAGE['imagehash']=digest
            img=EngraverData.imageFromText(args)
            STORAGE['textimage']=img
        args.trf=parseTrf(dict.get('trf',[None])[0])
        self.SendImage(EngraverData._trfImage(img.copy(),args))

    def _getEnhanceValue(self,dict,key):
        res=None
        val=dict.get(key)
        if val and abs(float(val[0]))>0.001:
            res=contrastBrightnessValue(val[0])
        return res
        
    def RenderImage(self,dict):
        for p in ['width','height']:
            if  p not in dict:
                self.send_error(404, "parameter '%s' is missing"%p)
                return
        global args 
        args.size=(unitValue(dict['width'][0]),unitValue(dict['height'][0]))
        args.trf=parseTrf(dict.get('trf',[None])[0])
        args.contrast=self._getEnhanceValue(dict,'contrast')
        args.brightness=self._getEnhanceValue(dict,'brightness')
        img=EngraverData.processImage(STORAGE['image'].copy(),args)
        self.SendImage(img)
        
    
    def do_GET(self):
        dict={}
        l=self.path.split('?')
        if len(l)>1: dict=parse_qs(l[1])
        f=self.pathtofunc.get(l[0])
        if not f:
            self.path='%sweb%s'%(os.sep,self.path)
            if self.translate_path(self.path).startswith(os.getcwd()+os.sep+'web'):
                SimpleHTTPRequestHandler.do_GET(self)
            else:
                self.send_error(404, "File not found")
        else:
            f(self,dict)

     
    def do_POST(self):
        l=self.path.split('?')
        f=self.ppathtofunc.get(l[0])
        if not f:
            self.send_error(404, "File not found")
        else:
            f(self)

    
    def SaveImage(self):
        global args
        content_length = int(self.headers['Content-Length'])
        ctype, pdict = cgi.parse_header(self.headers['Content-Type'])
        if ctype == 'multipart/form-data':
            encoding='utf-8'
            errors='replace'
            boundary = pdict['boundary']
            ctype = self.headers['Content-Type']
            headers = cgi.Message()
            headers.set_type(ctype)
            headers['Content-Length'] = self.headers['Content-Length']
            fs = cgi.FieldStorage(self.rfile, headers=headers, encoding=encoding, errors=errors,
                              environ={'REQUEST_METHOD': 'POST'})
            try:
                image=fs['file']
                data=fs.getlist('file')[0]
            except:
                image=None
            if image!=None:
                fd=BytesIO(data)
                StoreImage(fd)
                self.send_response(200)
                self.end_headers()
            else: 
                self.send_error(400,"content dispostion `file0` expected\n",'utf-8')
        else:
            self.send_error(400,"content type `multipart/form-data` expected\n",'utf-8')

    pathtofunc={
        '/ws':CreateWS,
        '/fonts':GetFonts,
        '/textimage':RenderImageFromText,
        '/image':RenderImage
        }
    
    ppathtofunc={
        '/image':SaveImage
        }
    

class Httpd(HTTPServer):

    allow_reuse_address = True
    
    def __init__(self,bind,port):
        HTTPServer.__init__(self,(bind,port), GUIHandler)
        self.listeners={}
        self.intervall=0.5
        self.msg=None
        self.do_close=True
        self.messageHandler=lambda p: None
        self.Register(self)
        self.lock=threading.Lock()
        
    def DoRead(self):
        self.handle_request()

    def DoWrite(self,msg):
        pass
    
    def DoClose(self):
        os.close(self.fileno())
    
    def KeepOpen(self):
        self.do_close=False
        
    def shutdown_request(self, request):
        if self.do_close:
            HTTPServer.shutdown_request(self,request)
        else:
            print ("keep open",self.do_close,request.fileno())
        self.do_close=True


    def Register(self,client):
        self.listeners[client.fileno()]=client

    def Unregister(self,listener):
        if type(listener)!=int:
            listener=listener.fileno()
        try:
            del self.listeners[listener]
        except:
            pass

    def SetMessageHandler(self,handler):
        self.messageHandler=handler

    def HandleRead(self,fd):
        self.listeners[fd].DoRead()

    def HandleClose(self,fd):
        client=self.listeners[fd]
        client.DoClose()
        self.Unregister(client)

    
    def Loop(self):
        while self.listeners:
            fds=self.listeners.keys()
            rList, dummy, xList = select(fds, [], fds, self.intervall)
            for ready in rList:
                if ready not in fds:
                    continue
                try:
                    self.HandleRead(ready)
                except Exception as n:
                    print(n)
                    self.HandleClose(ready)
            for failed in xList:
                self.HandleClose(ready)

    def Send(self,obj):
        self.lock.acquire()
        msg=json.dumps(obj)
        for client in self.listeners.values():
            client.DoWrite(msg)
        self.lock.release()

    def Receive(self,msg):
        obj=json.loads(msg)
        self.messageHandler.receive(obj)

class StdoutClient(object):
    def DoWrite(self,msg):
        print(msg)

    def DoRead(self):
        os.read(1,16384)

    def fileno(self): 
        return 1

class ExternalLogger(Logger):
    def __init__(self,verbosity,channel):
        Logger.__init__(self,verbosity)
        self.success=True
        self.channel=channel

    def fatal(self,fmt,*args):
        self.log("FATAL",fmt,*args)

    def log(self,severity,fmt,*args):
        lev=self.LEVELS.get(severity,99)
        if lev<self.LEVELS["WARN"]:
            self.success=False
        if self.verbosity>=lev:
            self.channel.Send({'type':'message','severity':severity,'content':fmt%args})

    def resetError(self):
        res=self.success
        self.success=True
        return res


class Worker(threading.Thread):
    def __init__(self,engraver,channel):
        self.engraver=engraver
        self.channel=channel
        self.doStop=False
        self.busy=False
        self.engraving=False
        self.framing=False
        self.centerAxis=None
        self.useCenter=False
        self.burner=None
        self.queue=queue.Queue(1)
        self.commands={
            'connect':self.connect,
            'disconnect':self.disconnect,
            'fan':Engraver.fan,
            'home':Engraver.home,
            'nop':lambda e: None,
            'move':Engraver.move,
            'status':lambda e: None,
            'frameStart':self.frameStart,
            'frameStop':self.frameStop,
            'engrave':self.engrave,
            'stopEngraving':self.stopEngraving
            }
        threading.Thread.__init__(self)
        self.setDaemon(True)

    def connect(self,engraver):
        engraver.open()
        if engraver.isOpened():
            engraver.connect()
            engraver.fan(True)
            
    def disconnect(self,engraver):
        engraver.close()
    
    def status(self,engraver):
        return {'type':'status',
               'connected':engraver.isOpened(),
               'engraving':self.engraving,
               'framing':self.framing,
               'fanOn':engraver.isFanOn(),
               'success':Logger.LOGGER.resetError(),
               'centerAxis':self.centerAxis,
               'useCenter':self.useCenter
               }

    def frameStart(self,engraver,fx,fy,useCenter,centerAxis):
        self.centerAxis=centerAxis
        self.useCenter=useCenter
        self.framing=True
        engraver.frameStart(fx,fy,useCenter,centerAxis)

    def frameStop(self,engraver,fx,fy,useCenter,centerAxis):
        self.framing=False
        engraver.frameStop(fx,fy,useCenter,centerAxis)

    def engrave(self,engraver,mode,useCenter,trf,width,height,power,depth):
        global args
        if mode=='image':
            img=STORAGE['image'].copy()
        else:
            img=STORAGE['textimage'].copy()
        args.size=(width,height)
        args.trf=parseTrf(trf)
        args.power=power
        args.depth=depth
        data=EngraverData._imageToData(img,args)
        self.burner=BurnThread(self,engraver,data,useCenter)
        self.burner.start()
        self.engraving=True

    def stopEngraving(self,engraver):
        if self.burner:
            self.burner.pause()
            
    def run(self):
        while not self.doStop:
            msg=self.queue.get()
            self.busy=True
            cmd=self.commands.get(msg.get('cmd'))
            if cmd:
                res=cmd(self.engraver,**msg.get('args',{}))
                if res!=None:
                    self.channel.Send(res)
            else:
                Logger.LOGGER.error("unknown command: %s\n",msg.get('cmd'))
            self.channel.Send(self.status(self.engraver))
            self.busy=False

    def stop(self):
        self.doStop=True
        self.receive({"cmd":"nop"})


    def receive(self,obj):
        self.queue.put(obj)

    def engravingDone(self):
        self.engraving=False
        self.burner=None
        self.receive({"cmd":"nop"})
        
class UrlOpener(threading.Thread):
    def __init__(self,bname,host,port):
        self.port=port
        self.host=host
        self.browser=None
        
        if not bname:
            self.browser=webbrowser.get()
        else:
            self.browser=webbrowser.get(bname)
        threading.Thread.__init__(self)
        self.setDaemon(True)

    def run(self):
        if not self.browser:
            Logger.LOGGER.error("could not find webbrowser '%s'",args.browser)
            return
        while True:
            time.sleep(0.1)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((self.host,self.port))
            if result == 0:
                sock.close()
                break
        self.browser.open_new_tab('http://%s:%s'%(self.host,self.port))

class BurnThread(threading.Thread):
    def __init__(self,worker, engraver,data,useCenter): 
        threading.Thread.__init__(self) 
        self.engraver=engraver
        self.useCenter=useCenter
        self.data=data
        self.worker=worker
              
    def run(self):
        self.thread_id=threading.current_thread().ident
        engraver.burn(self.data,self.useCenter)
        worker.engravingDone()
           
    def pause(self): 
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(self.thread_id),ctypes.py_object(KeyboardInterrupt))
        if res != 1: 
            print('Exception raise failure') 


UI.setAsk(lambda msg: True)

parser = argparse.ArgumentParser(description=DESCRIPTION,formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument('-d', '--device',metavar="device",help='the serial device',default="/dev/ttyUSB0")
parser.add_argument('-s', '--speed',metavar="speed",help='the speed of the serial device',type=int,default=115200)
parser.add_argument('-v', '--verbosity',help='increase verbosity level ',action='count',default=0)
parser.add_argument('--limit', help='set maximum no. of steps in x/y direction',metavar=('steps'),dest='lim',type=int,default=1575)
parser.add_argument('-b', '--browser',metavar="browser",help='use browser to open gui, set to - to not open the gui',default='')
parser.add_argument('-B', '--bind',metavar="bind",help='use the given address to bind to; use 0.0.0.0 for all interfaces',
                    default='127.0.0.1')

parser.add_argument('-P', '--port',metavar="port",help='use the given port',
                    default=8008)

parser.add_argument('-T','--transform', help=argparse.SUPPRESS,dest='trf')
parser.add_argument('--dry-run',dest='dummy', help=argparse.SUPPRESS)
parser.add_argument('--invert',dest='invert', help=argparse.SUPPRESS,default=False,action='store_true')
parser.add_argument('--brightness',dest='brightness', help=argparse.SUPPRESS,default=None)
parser.add_argument('--contrast',dest='contrast', help=argparse.SUPPRESS,default=None)

args = parser.parse_args()


if args.browser!='-':
    if args.bind not in ['0.0.0.0','127.0.0.1']:
        host=args.bind
    else:
        host='localhost'
    UrlOpener(args.browser,host,args.port).start()

httpd = Httpd(args.bind,args.port)
httpd.Register(StdoutClient())
Logger.set(ExternalLogger(args.verbosity,httpd))
engraver=Engraver(args)
worker=Worker(engraver,httpd)
httpd.SetMessageHandler(worker)
StoreImage('web/logo.png')
worker.start()
httpd.Loop()







