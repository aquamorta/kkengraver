
import {BrowserModule} from '@angular/platform-browser';
import {BrowserAnimationsModule} from '@angular/platform-browser/animations';
import {HttpClientModule} from '@angular/common/http';
import {NgModule} from '@angular/core';
import {FormsModule} from '@angular/forms';
import 'hammerjs';
import {AppComponent} from './app.component';

import {
    MatButtonModule,
    MatCardModule,
    MatDividerModule,
    MatIconModule,
    MatGridListModule,
    MatButtonToggleModule,
    MatSliderModule,
    MatInputModule,
    MatSelectModule,    
    MatBottomSheetModule,    
    MAT_RIPPLE_GLOBAL_OPTIONS
} from '@angular/material';
import {EngraverService} from './engraver.service';
import { SizeInputComponent } from './size-input/size-input.component';
import { ImageDisplayComponent } from './image-display/image-display.component';
import { ImageUploadComponent } from './image-upload/image-upload.component';

@NgModule({
    declarations: [
        AppComponent,
        SizeInputComponent,
        ImageDisplayComponent,
        ImageUploadComponent,
    ],
    imports: [
        BrowserModule,
        BrowserAnimationsModule,
        MatButtonModule,
        MatCardModule,
        MatDividerModule,
        MatGridListModule,
        MatIconModule,
        MatButtonToggleModule,
        MatSliderModule,
        MatInputModule,
        MatBottomSheetModule,
        FormsModule,
        MatSelectModule,
        HttpClientModule,
    ],
    providers: [EngraverService,{provide: MAT_RIPPLE_GLOBAL_OPTIONS, useValue: {disabled: true}}],
    entryComponents:[],
    bootstrap: [AppComponent]
})
export class AppModule {}
