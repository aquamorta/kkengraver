import {Component, OnInit, Input, ViewChild, ElementRef, AfterViewInit} from '@angular/core';

@Component({
    selector: 'image-display',
    templateUrl: './image-display.component.html',
    styleUrls: ['./image-display.component.css']
})
export class ImageDisplayComponent implements OnInit, AfterViewInit {

    @ViewChild('canvas', {static: false}) canvas: ElementRef;

    @ViewChild('image', {static: false}) image: ElementRef;

    @Input()
    margin = 16;

    @Input()
    minDist = 5;

    @Input()
    reserved = 640;

    @Input()
    widthFactor = 0.8;

    @Input()
    pxPerMm = 500. / 25.4

    private _center = false;

    constructor() {}

    ngOnInit() {

    }

    ngAfterViewInit(): void {
    }

    set center(value: boolean) {
        if (value != this._center) {
            this._center = value;
            this.displayImage();
        }
    }

    @Input()
    get center() {
        return this._center;
    }

    private drawRulers(width: number, height: number, ctx: CanvasRenderingContext2D, scaleDown: number) {

        let widthMm = Math.trunc(width / this.pxPerMm);
        let heightMm = Math.trunc(height / this.pxPerMm);

        let pxPerMm = this.pxPerMm * scaleDown;
        ctx.fillStyle = "black";
        ctx.lineWidth = 1;
        ctx.strokeStyle = "black";
        ctx.font = "8px Helvetica";
        ctx.beginPath();
        for (var i = 1; i <= widthMm; i++) {
            var s = this.margin / 2;
            switch (i % 10) {
                case 0:
                    if (Math.round(i * pxPerMm) != Math.round(width * scaleDown)) {
                        ctx.fillText(i.toFixed(), i * pxPerMm + this.margin + 2, this.margin / 3.);
                    }
                    s = 0
                    break;
                case 5:
                    s = this.margin / 4;
                    break;
            }
            ctx.moveTo(i * pxPerMm + this.margin, s);
            ctx.lineTo(i * pxPerMm + this.margin, this.margin);
            if (i + 1 > widthMm) {
                ctx.fillText((width / this.pxPerMm).toFixed(1) + " mm", width * scaleDown + this.margin + 2, this.margin );
            }
        }
        ctx.stroke();
        ctx.beginPath();
        for (var i = 1; i <= heightMm; i++) {
            var s = this.margin / 2;
            switch (i % 10) {
                case 0:
                    if (Math.round(i * pxPerMm) != Math.round(height * scaleDown)) {
                        ctx.fillText(i.toFixed(), 0, i * pxPerMm + this.margin + 8);
                    }
                    s = 0
                    break;
                case 5:
                    s = this.margin / 4;
                    break;
            }
            ctx.moveTo(s, i * pxPerMm + this.margin);
            ctx.lineTo(this.margin, i * pxPerMm + this.margin);
            if (i + 1 > heightMm) {
                ctx.fillText((height / this.pxPerMm).toFixed(1) + " mm", 0, height * scaleDown + this.margin + 8);
            }
        }
        ctx.stroke();

    }

    displayImage() {
        let img = <HTMLImageElement> this.image.nativeElement;
        let canvas = <HTMLCanvasElement> this.canvas.nativeElement;
        canvas.width = window.innerWidth * this.widthFactor;
        canvas.height = window.innerHeight - this.reserved;
        var ctx = canvas.getContext('2d');
        var f = 1;
        while (img.width / f > canvas.width || img.height / f > canvas.height) {
            f += 1;
        }
        f = 1. / f

        ctx.clearRect(0, 0, canvas.width + this.margin, canvas.height + this.margin);
        this.drawRulers(img.width, img.height, ctx, f);
        ctx.drawImage(img, 0, 0, img.width, img.height, this.margin, this.margin, f * img.width, f * img.height);
        var offX = this.margin;
        var offY = this.margin;
        if (this.center) {
            offX += f * img.width / 2.
            offY += f * img.height / 2.
        }
        ctx.globalAlpha = 0.8;
        ctx.strokeStyle = "#0000ff";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(offX - this.margin / 2, offY);
        ctx.lineTo(offX + this.margin / 2, offY)
        ctx.moveTo(offX, offY - this.margin / 2);
        ctx.lineTo(offX, offY + this.margin / 2)
        ctx.stroke();

        ctx.font = "12px Helvetica";
        ctx.fillText(img.height.toFixed(), f*img.width + this.margin + 8, f*(img.height + this.margin) / 2. + 8);
        ctx.fillText(img.width.toFixed(), f*(img.width + this.margin) / 2, f*img.height + this.margin + 16);

    }

    loadImage(src: string) {
        (<HTMLImageElement> this.image.nativeElement).src = src;
    }

}
