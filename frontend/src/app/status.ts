import {Generic} from './generic';

export class Status extends Generic{
    constructor(
        public connected=false,
        public busy=false,
        public fanOn=true,
        public success=true,
        public framing = false,
        public engraving = false,
        public useCenter=false,
        public centerAxis:string=undefined) {
        super('status');
    }
}
