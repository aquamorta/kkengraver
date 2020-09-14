
import {BrowserModule} from '@angular/platform-browser';
import {BrowserAnimationsModule} from '@angular/platform-browser/animations';
import {HttpClientModule} from '@angular/common/http';
import {NgModule} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {AppComponent} from './app.component';
import {MAT_RIPPLE_GLOBAL_OPTIONS} from '@angular/material/core/';
import {MatButtonModule} from '@angular/material/button/';
import {MatButtonToggleModule} from '@angular/material/button-toggle/';
import {MatDividerModule} from '@angular/material/divider/';
import {MatCardModule} from '@angular/material/card/';
import {MatIconModule} from '@angular/material/icon/';
import {MatGridListModule} from '@angular/material/grid-list/';
import {MatSliderModule} from '@angular/material/slider';
import {MatInputModule} from '@angular/material/input/';
import {MatSelectModule} from '@angular/material/select/';
import {MatBottomSheetModule} from '@angular/material/bottom-sheet/';

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
