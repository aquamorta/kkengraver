import {Component, OnInit, Input, Output, EventEmitter} from '@angular/core';

@Component({
    selector: 'size-input',
    templateUrl: './size-input.component.html',
    styleUrls: ['./size-input.component.css']
})
export class SizeInputComponent implements OnInit {

    @Input()
    label: string = "Size";

    _value: number = 0;

    @Input()
    pxPerMm: number = 500. / 25.4;

    input: string = "";

    @Input()
    lineBreak: boolean = false;

    @Output()
    valueChange = new EventEmitter<number>();

    info: string = "";

    private mmRegexp: RegExp = new RegExp("^([0-9]+(.[0-9]*)?)( )*mm$");

    private pxRegexp: RegExp = new RegExp("^([0-9]+)( )*(px)?$");

    updateValue() {
        var res = this.mmRegexp.exec(this.input);
        if (res) {
            this.value = Math.round((+res[1] * this.pxPerMm));
        } else {
            res = this.pxRegexp.exec(this.input);
            if (res) {
                this.value = +res[1];
            }
        }
        if (res) {
            this.valueChange.emit(this.value);
            let v = (this.value / this.pxPerMm).toFixed(1);
            this.info = `${v} mm`;
        }
    }

    @Input()
    get value(): number {
        return this._value;
    }

    set value(v: number) {
        this.input= ""+v;
        this._value = v;
    }


    constructor() {}

    ngOnInit() {
        this.updateValue();
    }

}
