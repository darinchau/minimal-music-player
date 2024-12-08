class AudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.port.onmessage = (event) => {
            if (event.data.audioBuffer) {
                this.enqueue(event.data.audioBuffer);
            }
        };
    }

    process(inputs, outputs) {
        const output = outputs[0];
        output.forEach(channel => {
            channel.set(this.dequeue() || new Float32Array(channel.length));
        });
        return true;
    }

    enqueue(audioBuffer) {
        this.audioBufferQueue = this.audioBufferQueue || [];
        this.audioBufferQueue.push(audioBuffer);
    }

    dequeue() {
        if (this.audioBufferQueue && this.audioBufferQueue.length) {
            return this.audioBufferQueue.shift();
        }
        return null;
    }
}

registerProcessor('audio-processor', AudioProcessor);
