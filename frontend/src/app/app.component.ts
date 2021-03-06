import {Component, OnInit, ViewChild, ElementRef, AfterViewInit, Input} from '@angular/core';
import {EngraverService} from './engraver.service';
import {Message, Command, Status, Font} from '.';
import {MatBottomSheet} from '@angular/material/bottom-sheet';
import {Subject} from 'rxjs';
import {debounceTime, distinctUntilChanged} from 'rxjs/operators';
import {ImageDisplayComponent} from './image-display/image-display.component';

@Component({
    selector: 'app-root',
    templateUrl: './app.component.html',
    styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit, AfterViewInit {

    version:string="";

    locked: boolean = false;

    disabled: boolean = true;

    totalDisabled: boolean = true;

    status: Status = new Status();

    log: string[] = [];

    moveDistance: number = 1;

    power: number = 100;

    depth: number = 10;

    contrast: number=0;
    
    brightness: number=0;
    
    mode: string = "image";

    text: string = "Hello world!";

    useCenter: boolean = false;

    xyCenter: string[] = [];

    xyCenterSaved: string = "";

    widthUpdate = new Subject<string>();

    heightUpdate = new Subject<string>();

    textUpdate = new Subject<string>();

    contrastUpdate = new Subject<string>();

    brightnessUpdate = new Subject<string>();

    private rotationArray = ["", "ccw", "turn", "cw"];

    private rotation = 0;

    private mirrorArray = ["", "tb", "lr", "tb lr"];

    private mirror = 0;

    private fonts: Font[] = [];

    private selectedFont: string = "";

    private progressPat = /^\r(sending:)? *(1?[0-9]?[0-9])% done$/;

    pxPerMm: number = 500. / 25.4;

    @Input()
    debounceTime = 750;

    width: number = 250;

    height: number = 250;

    @ViewChild('scrolllog', {static: false}) scrollFrame: ElementRef;

    @ViewChild(ImageDisplayComponent, {static: false}) imageDisplay: ImageDisplayComponent;

    private scrollContainer: HTMLDivElement;

    constructor(private service: EngraverService, private bottomSheet: MatBottomSheet) {

    }

    ngAfterViewInit(): void {
        this.widthUpdate.pipe(debounceTime(this.debounceTime), distinctUntilChanged()).subscribe(e => this.updateImage());
        this.heightUpdate.pipe(debounceTime(this.debounceTime), distinctUntilChanged()).subscribe(e => this.updateImage());
        this.textUpdate.pipe(debounceTime(this.debounceTime), distinctUntilChanged()).subscribe(e => this.updateImage());
        this.contrastUpdate.pipe(debounceTime(this.debounceTime), distinctUntilChanged()).subscribe(e => this.updateImage());
        this.brightnessUpdate.pipe(debounceTime(this.debounceTime), distinctUntilChanged()).subscribe(e => this.updateImage());
        this.scrollContainer = <HTMLDivElement> this.scrollFrame.nativeElement;
        this.updateImage();
        this.connect();
    }

    private scrollToBottom(): void {
        this.scrollContainer.scroll({
            top: this.scrollContainer.scrollHeight,
            left: 0,
            behavior: 'smooth'
        });
    }

    updateFontList(fontList: Font[]) {
        if (this.selectedFont == "" && fontList.length > 0) {
            this.selectedFont = fontList[0].file;
        }
        this.fonts = fontList;
    }

    ngOnInit(): void {
        this.mode = "image";
        this.service.receive(
            (obj) => this.messageHandler(obj),
            (obj) => this.statusHandler(obj),
            (obj) => this.commandHandler(obj));
        this.retrieveStatus();
        this.service.fonts().then(flist => this.updateFontList(flist));

    }

    commandHandler(cmd: Command) {
    }

    statusHandler(status: Status) {
        this.version = status.version;
        this.locked = false;
        this.status = status;
        this.disabled = status.engraving || status.framing;
        this.totalDisabled = !status.connected || this.disabled;
        if (!this.disabled) {
            this.imageDisplay.displayProgress(null, null);
        }
    }

    messageHandler(msg: Message) {
        let match = this.progressPat.exec(msg.content);
        if (match) {
            var mode;
            if (match[1]) {
                mode = 'transfer';
            } else {
                mode = 'engrave';
            }
            this.imageDisplay.displayProgress((+match[2]) / 100., mode);
        } else {
            this.log.push(`[${msg.severity}] ${msg.content}`);
            setTimeout(() => this.scrollToBottom(), 10);
        }
    }

    send(msg: Command) {
        this.locked = true;
        this.disabled = true;
        this.service.send(msg);
    }

    textSelected() {
        this.updateImage();
    }

    imageSelected() {
        this.updateImage();
    }

    updateImage() {
        var src;
        if (this.mode == 'image') {
            src = `/image?width=${this.width}&height=${this.height}&trf=${this.transformation()}&contrast=${this.contrast}&brightness=${this.brightness}`;
        } else {
            let txt = encodeURIComponent(this.text);
            src = `/textimage?text=${txt}&width=${this.width}&height=${this.height}&font=${this.selectedFont}&trf=${this.transformation()}`;
        }
        console.log("src=" + src)
        this.imageDisplay.loadImage(src);
    }

    fontChanged() {
        this.updateImage();
    }

    transformation() {
        return `${this.rotationArray[this.rotation]} ${this.mirrorArray[this.mirror]}`.trim();
    }

    rotateClicked(dir: number) {
        this.rotation = (this.rotation + dir + 4) % 4;
        this.updateImage();
    }

    mirrorClicked(v: number) {
        this.mirror ^= v;
        this.updateImage();
    }

    click(ev: Event) {
        console.log(ev);
    }


    /********************** engraver commands ********************************/

    retrieveStatus() {
        this.send({'cmd': 'status'})
    }

    fan(on: boolean) {
        this.send({'cmd': 'fan', 'args': {'on': on}});
    }

    home() {
        this.send({'cmd': 'home'});
    }

    connect() {
        this.send({'cmd': 'connect'});
    }

    disconnect() {
        this.send({'cmd': 'disconnect'});
    }


    moveRight() {
        this.send({'cmd': 'move', 'args': {'dx': Math.round(this.moveDistance * this.pxPerMm), 'dy': 0}});
    }

    moveLeft() {
        this.send({'cmd': 'move', 'args': {'dx': Math.round(-this.moveDistance * this.pxPerMm), 'dy': 0}});

    }

    moveDown() {
        this.send({'cmd': 'move', 'args': {'dx': 0, 'dy': Math.round(this.moveDistance * this.pxPerMm)}});
    }

    moveUp() {
        this.send({'cmd': 'move', 'args': {'dx': 0, 'dy': Math.round(-this.moveDistance * this.pxPerMm)}});
    }

    frame() {
        let args = {'fx': this.imageDisplay.imageWidth, 'fy': this.imageDisplay.imageHeight, 'useCenter': this.useCenter, 'centerAxis': this.xyCenterSaved};
        console.log(args);
        if (this.xyCenter[0] != undefined) {
            this.xyCenterSaved = this.xyCenter[0];
            this.send({'cmd': 'frameStart', 'args': args});
        } else {
            this.send({'cmd': 'frameStop', 'args': args});
            this.xyCenterSaved = null;
        }
    }

    startEngrave() {
        this.fan(true);
        let cmd = {
            'cmd': 'engrave', 'args': {
                'mode': this.mode,
                'useCenter': this.useCenter,
                'trf': this.transformation(),
                'width': this.width,
                'height': this.height,
                'power': this.power,
                'depth': this.depth
            }
        };
        this.send(cmd);
    }

    stopEngrave() {
        this.send({'cmd': 'stopEngraving', 'args': {}});
    }

}
