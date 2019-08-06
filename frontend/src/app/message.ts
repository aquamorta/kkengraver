import {Generic} from './generic';

export class Message extends Generic {
    constructor(
        public severity?: string,
        public content?:string) {
        super('message');
    }
}
