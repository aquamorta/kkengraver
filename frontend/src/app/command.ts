import {Generic} from './generic';

export class Command extends Generic {
    constructor(
        public cmd?: string,
        public args?: any) {
        super('command');
    }
}
