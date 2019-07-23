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
import time as otime
import hashlib
import base64
import struct
import traceback
import codecs

from select import select
from http.server import SimpleHTTPRequestHandler,HTTPServer

##############################################################################

def _print(d):
    sys.stderr.write("%s\n"%d)

##############################################################################

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

MAXHEADER = 65536
MAXPAYLOAD = 33554432

STATUS_CODES = [1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011, 3000, 3999, 4000, 4999]


class Websocket(object):

    def __init__(self,socket,master):
        self.socket=socket
        self.master=master
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
        self.maxheader = MAXHEADER
        self.maxpayload = MAXPAYLOAD
        self.Update()
        
    
    def DoRead(self,fd):
        msg=os.read(fd,16384)
        if msg:
            for d in msg:
                self.DecodeMessage(ord(d))
        else:
            os.close(fd)

        
    def HandleMessage(self):
        print ('data',self.data)
        
    def Send(self,data):
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

              self.HandleMessage()

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

              self.HandleMessage()


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
        

class GUIHandler(SimpleHTTPRequestHandler):

    def __init__(self,fd,addr,server):
        self.server=server
        self.master=server.Master()
        self.hand_over=False
        return SimpleHTTPServer.SimpleHTTPRequestHandler.__init__(self,fd,addr,server)
            
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

    
    def Files(self,args):
        self._JSONHeader()
        songs=[]
        albums={}
        self._BuildSongList([Object.Fetch(i) for i in args['p']],songs,albums)
        self.wfile.write(json.write({'songs':songs,'albums':albums}))
        

    def Command(self,args):
        player=self.master.Player()
        cmd=args['p'][0]
        cmd=self.cmdtable.get(cmd)
        if cmd:
            player.HandleCmd(cmd)
        self.StatusQuery(args)

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
            ws=Websocket(self.request,self.master)
            Monitor.Instance().Attach(ws)
            self.master.AttachScreen(ws)
        else:
            self.send_error(400,"illegal request")

    
    def do_GET(self):
        dict={}
        l=self.path.split('?')
        if len(l)>1: dict=parse_qs(l[1])
        f=self.pathtofunc.get(l[0])
        if not f:
            if self.path.startswith(CONFIG[sDATADIR]):
                path=self.path
                ctype = self.guess_type(path)
                try:
                    # Always read in binary mode. Opening files in text mode may cause
                    # newline translations, making the actual size of the content
                    # transmitted *less* than the content-length!
                    f = open(path, 'rb')
                except IOError:
                    self.send_error(404, "File not found")
                    return None
                try:
                    self.send_response(200)
                    self.send_header("Content-type", ctype)
                    fs = os.fstat(f.fileno())
                    self.send_header("Content-Length", str(fs[6]))
                    self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
                    self.end_headers()
                    try:
                        self.copyfile(f, self.wfile)
                    finally:
                        f.close()
                except:
                    f.close()
                    raise
            else:
                self.path='/files%s'%self.path
                if self.translate_path(self.path).startswith(os.getcwd()+os.sep+'files'):
                    SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)
                else:
                    self.send_error(404, "File not found")
        else:
            f(self,dict)
                

    pathtofunc={
        '/ws'               :CreateWS
        }
    

class Httpd(HTTPServer):

    allow_reuse_address = True
    
    def __init__(self,port=8008):
        HTTPServer.__init__(self,('',port), GUIHandler)
        self.msg=None
        self.do_close=True

        
    def DoRead(self,fd):
        self.handle_request()

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


class Registry(object):
    def __init__(self):
        self.listeners={}
        self.intervall=0.5
    
    def Register(self,client):
        self.listeners[client.fileno()]=client

    def Unregister(self,listener):
        del self.listeners[listener]

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
                    self.HandleClose(ready)
            for failed in xList:
                self.HandleClose(ready)
            
    
    
    
if __name__ == '__main__':

    httpd = Httpd()
    print (httpd,httpd.fileno(),type(httpd.fileno()))
    registry= Registry()
    registry.Register(httpd)
    registry.Loop()




