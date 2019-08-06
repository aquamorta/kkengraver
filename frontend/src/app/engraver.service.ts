import {Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {webSocket, WebSocketSubject} from "rxjs/webSocket";
import { map, tap, retryWhen } from 'rxjs/operators';
import {Message, Status, Generic, Command,Font} from '.';

@Injectable({
    providedIn: 'root'
})
export class EngraverService {

    private socket: WebSocketSubject<Generic|Command> = webSocket(`ws://${location.hostname}:${location.port}/ws`);
    
    constructor(public http: HttpClient) {
        
    }
    
    receive(msgFunc:(msg:Message)=>void,statusFunc:(msg:Status)=>void,cmdFunc:(cmd:Command)=>void) {
        this.socket.pipe(
            retryWhen(error => error.pipe(tap(e => console.log("retry:" + JSON.stringify(e)))))
        ).subscribe( 
            (obj) => {
                if ((<Generic>obj).type==='message') {
                    msgFunc(Object.assign(new Message(),<Message>obj));
                } else if ((<Generic>obj).type==='status') {
                    statusFunc(Object.assign(new Status(),<Status>obj));                    
                } else if ((<Generic>obj).type==='command') {
                    cmdFunc(Object.assign(new Command(),<Command>obj));                    
                } else {
                    console.log("error: received unknow object type:"+ JSON.stringify(obj))
                }
            },
            (err) => console.log(`error:${err}`),
            () => console.log("completed")
        );
    }
    
    send(cmd: Command) {
        this.socket.next(cmd);
    }
    
    fonts():  Promise<Font[]> {
        return this.http.get('/fonts').toPromise().then(f => <Font[]>f);
    }
}
