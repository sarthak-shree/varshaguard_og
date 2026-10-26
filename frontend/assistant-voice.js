(() => {
  "use strict";

  const MAX_RECORDING_MS = 20_000;

  function bindVoiceAssistant(options) {
    const {
      button,
      status,
      language,
      input,
      sendButton,
      getContext,
      appendMessage,
      onStateChange,
    } = options;

    if (!button || !status || !language || !getContext || !appendMessage) return null;

    let recorder = null;
    let stream = null;
    let chunks = [];
    let stopTimer = null;
    let starting = false;
    let busy = false;
    let discardRecording = false;
    let audioContext = null;
    let audioSource = null;
    let audioMeterFrame = 0;

    function stopAudioMeter() {
      if (audioMeterFrame) window.cancelAnimationFrame(audioMeterFrame);
      audioMeterFrame = 0;
      try { audioSource?.disconnect(); } catch { }
      audioSource = null;
      const previousContext = audioContext;
      audioContext = null;
      if (previousContext && previousContext.state !== "closed") {
        previousContext.close().catch(() => {});
      }
      window.VarshaGuardOrb?.setAudioLevel(0);
    }

    async function startAudioMeter(mediaStream) {
      stopAudioMeter();
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return;

      try {
        const context = new AudioContextClass();
        const analyser = context.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = .72;
        const source = context.createMediaStreamSource(mediaStream);
        source.connect(analyser);
        audioContext = context;
        audioSource = source;
        if (context.state === "suspended") await context.resume();

        const samples = new Uint8Array(analyser.fftSize);
        const readVolume = () => {
          if (audioContext !== context || !stream || recorder?.state !== "recording") return;
          analyser.getByteTimeDomainData(samples);
          let sumSquares = 0;
          for (let index = 0; index < samples.length; index += 1) {
            const amplitude = (samples[index] - 128) / 128;
            sumSquares += amplitude * amplitude;
          }
          const rms = Math.sqrt(sumSquares / samples.length);
          const level = Math.max(0, Math.min(1, (rms - .012) * 9));
          window.VarshaGuardOrb?.setAudioLevel(level);
          audioMeterFrame = window.requestAnimationFrame(readVolume);
        };
        readVolume();
      } catch {
        stopAudioMeter();
      }
    }

    function setStatus(message, state) {
      const currentState = state || "idle";
      status.textContent = message;
      if (typeof onStateChange === "function") onStateChange(currentState, message);
      document.dispatchEvent(new CustomEvent("varshaguard:assistant-state", {
        detail: { state: currentState, global: true }
      }));
      const dialog = document.getElementById("assistantModal");
      if (dialog) dialog.dataset.assistantState = currentState;
      const stateLabel = document.getElementById("assistantOrbState");
      if (stateLabel) {
        stateLabel.textContent = ({
          idle: "Ready to listen",
          listening: "Listening to you",
          thinking: "Preparing your answer",
          speaking: "Speaking response"
        })[currentState] || "Ready to help";
      }
    }

    function releaseMicrophone() {
      stopAudioMeter();
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
        stream = null;
      }
      if (stopTimer) {
        window.clearTimeout(stopTimer);
        stopTimer = null;
      }
      button.classList.remove("is-recording");
      button.setAttribute("aria-pressed", "false");
      button.textContent = "🎙 Speak";
    }

    function setBusy(value) {
      busy = value;
      button.disabled = value;
      if (input) input.disabled = value;
      if (sendButton) sendButton.disabled = value;
    }

    async function sendRecording(blob) {
      if (!blob.size) {
        setStatus("No speech was recorded. Tap Speak and try again.");
        return;
      }

      setBusy(true);
      setStatus("Transcribing and preparing your answer…", "thinking");

      try {
        const extension = blob.type.includes("ogg") ? "ogg"
          : blob.type.includes("mp4") ? "mp4"
            : blob.type.includes("wav") ? "wav" : "webm";
        const formData = new FormData();
        formData.append("audio", blob, "varshaguard-question." + extension);
        formData.append("context", JSON.stringify(getContext()));
        formData.append("reply_language", language.value === "hi" ? "hi" : "en");

        const response = await fetch("/api/assistant/voice", {
          method: "POST",
          body: formData,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
          throw new Error(data.error || "Voice assistant could not answer.");
        }

        appendMessage(data.transcript || "Spoken question", "user");
        const answerMessage = appendMessage(data.answer || "No answer returned.");
        if (data.audio_base64 && answerMessage) {
          const binary = window.atob(data.audio_base64);
          const bytes = new Uint8Array(binary.length);
          for (let index = 0; index < binary.length; index += 1) {
            bytes[index] = binary.charCodeAt(index);
          }
          const audio = document.createElement("audio");
          audio.className = "assistant-audio";
          audio.controls = true;
          audio.preload = "none";
          audio.setAttribute("aria-label", "Play VarshaGuard's spoken answer");
          audio.src = URL.createObjectURL(new Blob([bytes], {
            type: data.audio_mime_type || "audio/mpeg",
          }));
          answerMessage.appendChild(audio);
          setStatus("Speaking your answer…", "speaking");
          audio.addEventListener("ended", () => setStatus("Answer ready. You can ask another question.", "idle"), { once: true });
          audio.play().catch(() => {
            setStatus("Answer ready. Tap Play to hear it.", "idle");
          });
        } else {
          setStatus("Answer received, but speech audio was not returned.", "idle");
        }
      } catch (error) {
        setStatus(error.message || "Voice assistant could not answer. Try again.", "error");
        appendMessage(error.message || "Voice assistant could not answer.", "error");
      } finally {
        setBusy(false);
      }
    }

    button.addEventListener("click", async () => {
      if (busy || starting) return;
      if (recorder && recorder.state === "recording") {
        discardRecording = false;
        setStatus("Preparing your question…", "thinking");
        recorder.stop();
        return;
      }

      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        setStatus("This browser cannot record audio. You can type your question instead.");
        return;
      }

      starting = true;
      setStatus("Requesting microphone access…");
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        chunks = [];
        discardRecording = false;
        const preferredType = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus"]
          .find((type) => MediaRecorder.isTypeSupported(type));
        recorder = preferredType
          ? new MediaRecorder(stream, { mimeType: preferredType })
          : new MediaRecorder(stream);

        recorder.addEventListener("dataavailable", (event) => {
          if (event.data?.size) chunks.push(event.data);
        });
        recorder.addEventListener("error", () => {
          releaseMicrophone();
          setStatus("Recording stopped unexpectedly. Please try again.");
        });
        recorder.addEventListener("stop", async () => {
          const wasDiscarded = discardRecording;
          const recording = new Blob(chunks, {
            type: recorder.mimeType || chunks[0]?.type || "audio/webm",
          });
          chunks = [];
          releaseMicrophone();
          if (wasDiscarded) {
            setStatus("Recording canceled.", "idle");
            return;
          }
          await sendRecording(recording);
        });

        recorder.start();
        void startAudioMeter(stream);
        button.classList.add("is-recording");
        button.setAttribute("aria-pressed", "true");
        button.textContent = "■ Stop";
        setStatus("Listening… tap the orb again to send your question. Max 20 seconds.", "listening");
        stopTimer = window.setTimeout(() => {
          if (recorder?.state === "recording") {
            setStatus("20-second limit reached. Sending your question…", "thinking");
            recorder.stop();
          }
        }, MAX_RECORDING_MS);
      } catch (error) {
        releaseMicrophone();
        setStatus(error.name === "NotAllowedError"
          ? "Allow microphone access in your browser, then try again."
          : "Microphone unavailable. You can type your question instead.", "error");
      } finally {
        starting = false;
      }
    });

    return {
      cancel() {
        if (recorder && recorder.state === "recording") {
          discardRecording = true;
          recorder.stop();
        } else {
          releaseMicrophone();
        }
      },
      toggle() { button.click(); },
    };
  }

  window.VarshaGuardVoice = { bind: bindVoiceAssistant };
})();
