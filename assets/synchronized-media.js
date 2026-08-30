/**
 * Keep the page-level sign-language video paired with read-aloud narration.
 * This runs before the ADT runtime so its mutually exclusive media ownership
 * does not stop either half of the synchronized pair.
 */
(() => {
  "use strict";

  const NativeAudio = window.Audio;
  const nativePlay = HTMLMediaElement.prototype.play;
  const nativePause = HTMLMediaElement.prototype.pause;
  const FINAL_TRACK_GRACE_MS = 250;

  let narration = null;
  let narrationPlaying = false;
  let sessionStarted = false;
  let finalTrackTimer = null;

  const isSignVideo = (media) => {
    if (!(media instanceof HTMLVideoElement)) return false;
    const source = media.currentSrc || media.getAttribute("src") || "";
    return source.includes("/content/i18n/") && source.includes("/video/");
  };

  const signVideo = () =>
    Array.from(document.querySelectorAll("video")).find(isSignVideo) || null;

  const isNarrationAudio = (media) => {
    if (!(media instanceof HTMLAudioElement)) return false;
    const source = media.currentSrc || media.getAttribute("src") || media.src || "";
    return source.includes("/content/i18n/") && source.includes("/audio/");
  };

  const muteSignVideo = (video) => {
    if (!video) return;
    video.defaultMuted = true;
    video.muted = true;
    video.volume = 0;
  };

  const clearFinalTrackTimer = () => {
    if (finalTrackTimer !== null) {
      window.clearTimeout(finalTrackTimer);
      finalTrackTimer = null;
    }
  };

  const pauseVideo = ({ reset = false } = {}) => {
    const video = signVideo();
    if (!video) return;
    muteSignVideo(video);
    nativePause.call(video);
    if (reset) {
      try {
        video.currentTime = 0;
      } catch (_) {}
    }
  };

  const playTogether = (audio) => {
    if (!isNarrationAudio(audio)) return;

    clearFinalTrackTimer();
    narration = audio;
    narrationPlaying = true;

    const video = signVideo();
    if (!video) return;

    muteSignVideo(video);
    if (!sessionStarted || video.ended) {
      try {
        video.currentTime = 0;
      } catch (_) {}
      sessionStarted = true;
    }
    video.playbackRate = audio.playbackRate || 1;
    const playback = nativePlay.call(video);
    if (playback && typeof playback.catch === "function") playback.catch(() => {});
  };

  const scheduleCompletedSession = (audio) => {
    clearFinalTrackTimer();
    finalTrackTimer = window.setTimeout(() => {
      finalTrackTimer = null;
      if (audio !== narration || !audio.ended) return;
      narrationPlaying = false;
      sessionStarted = false;
      pauseVideo();
    }, FINAL_TRACK_GRACE_MS);
  };

  const pauseTogether = (audio) => {
    if (audio !== narration) return;
    if (audio.ended) {
      scheduleCompletedSession(audio);
      return;
    }
    clearFinalTrackTimer();
    narrationPlaying = false;
    pauseVideo();
  };

  const stopTogether = (audio) => {
    if (audio !== narration || audio.hasAttribute("src")) return;
    clearFinalTrackTimer();
    narrationPlaying = false;
    sessionStarted = false;
    pauseVideo({ reset: true });
    narration = null;
  };

  const bindNarrationEvents = (audio) => {
    audio.addEventListener("play", () => playTogether(audio));
    audio.addEventListener("pause", () => pauseTogether(audio));
    audio.addEventListener("ended", () => scheduleCompletedSession(audio));
    audio.addEventListener("emptied", () => stopTogether(audio));
    audio.addEventListener("ratechange", () => {
      const video = signVideo();
      if (video && audio === narration) video.playbackRate = audio.playbackRate || 1;
    });
  };

  function SynchronizedAudio(...args) {
    const audio = new NativeAudio(...args);
    bindNarrationEvents(audio);
    return audio;
  }

  Object.setPrototypeOf(SynchronizedAudio, NativeAudio);
  SynchronizedAudio.prototype = NativeAudio.prototype;
  window.Audio = SynchronizedAudio;

  // The stock runtime pauses the sign video when narration takes ownership.
  // Ignore only that video pause while the paired narration is playing.
  HTMLMediaElement.prototype.pause = function synchronizedPause() {
    if (
      isSignVideo(this) &&
      narrationPlaying &&
      narration &&
      !narration.paused
    ) {
      return;
    }
    return nativePause.call(this);
  };

  // Prevent the sign-video play event from switching the runtime into its
  // video-only ownership state, which would otherwise stop narration.
  window.addEventListener(
    "play",
    (event) => {
      if (!isSignVideo(event.target)) return;
      muteSignVideo(event.target);
      event.stopImmediatePropagation();
    },
    true,
  );

  // Reassert muting if native controls or another script changes it.
  window.addEventListener(
    "volumechange",
    (event) => {
      if (!isSignVideo(event.target)) return;
      if (!event.target.muted || event.target.volume !== 0) {
        muteSignVideo(event.target);
      }
    },
    true,
  );

  const prepareDynamicVideo = () => {
    const video = signVideo();
    if (!video) return;
    muteSignVideo(video);
    if (narrationPlaying && narration) playTogether(narration);
  };

  // The runtime creates the sign video only after its control is enabled.
  new MutationObserver(prepareDynamicVideo).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });

  window.__adtSynchronizedMedia = {
    version: "49",
    getState: () => {
      const video = signVideo();
      return {
        narrationDetected: Boolean(narration),
        narrationPlaying,
        sessionStarted,
        videoDetected: Boolean(video),
        videoMuted: video ? video.muted && video.volume === 0 : null,
        videoPaused: video ? video.paused : null,
      };
    },
  };

  window.addEventListener("pagehide", () => {
    clearFinalTrackTimer();
    narrationPlaying = false;
    sessionStarted = false;
    narration = null;
  });
})();
