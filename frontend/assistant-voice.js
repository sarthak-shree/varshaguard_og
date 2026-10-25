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
    } = options;

    if (!button || !status || !language || !getContext || !appendMessage) return null;

    let recorder = null;
    let stream = null;
    let chunks = [];
    let stopTimer = null;
    let starting = false;
    let busy = false;
    let discardRecording = false;

    function setStatus(message) {
      status.textContent = message;
    }

    function releaseMicrophone() {
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
      setStatus("Listening to your question…");

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
          setStatus("Answer ready. Use the player to listen again.");
          audio.play().catch(() => {
            setStatus("Answer ready. Tap Play to hear it.");
          });
        } else {
          setStatus("Answer received, but speech audio was not returned.");
        }
      } catch (error) {
        setStatus(error.message || "Voice assistant could not answer. Try again.");
        appendMessage(error.message || "Voice assistant could not answer.", "error");
      } finally {
        setBusy(false);
      }
    }

    button.addEventListener("click", async () => {
      if (busy || starting) return;
      if (recorder && recorder.state === "recording") {
        discardRecording = false;
        setStatus("Preparing your question…");
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
            setStatus("Recording canceled.");
            return;
          }
          await sendRecording(recording);
        });

        recorder.start();
        button.classList.add("is-recording");
        button.setAttribute("aria-pressed", "true");
        button.textContent = "■ Stop";
        setStatus("Listening… tap Stop when you finish. Max 20 seconds.");
        stopTimer = window.setTimeout(() => {
          if (recorder?.state === "recording") {
            setStatus("20-second limit reached. Sending your question…");
            recorder.stop();
          }
        }, MAX_RECORDING_MS);
      } catch (error) {
        releaseMicrophone();
        setStatus(error.name === "NotAllowedError"
          ? "Allow microphone access in your browser, then try again."
          : "Microphone unavailable. You can type your question instead.");
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
    };
  }

  window.VarshaGuardVoice = { bind: bindVoiceAssistant };
})();
