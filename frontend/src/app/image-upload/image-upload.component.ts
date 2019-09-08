import {Component, OnInit, Input, Output, EventEmitter} from '@angular/core';

@Component({
    selector: 'image-upload',
    templateUrl: './image-upload.component.html',
    styleUrls: ['./image-upload.component.css']
})
export class ImageUploadComponent implements OnInit {

    @Input()
    uploadURL: string;

    @Input()
    disabled=false;

    @Output()
    completed = new EventEmitter<XMLHttpRequest>();

    constructor() {}

    ngOnInit() {
    }

    onFileSelect(event: Event) {
        let file: File = (<HTMLInputElement> event.target).files[0];

        console.log(file);
        let xhr = new XMLHttpRequest();
        let formData = new FormData();
        formData.append("file", file);

        xhr.onreadystatechange = evnt => {
            console.log("onready");
            if (xhr.readyState === 4) {
                if (xhr.status !== 200 && xhr.status !== 201) {
                    console.log("error:", xhr.status, xhr.responseText);
                }
                this.completed.emit(xhr);
            }
        };

        xhr.open("POST", this.uploadURL, true);
        xhr.send(formData);
    }


}
